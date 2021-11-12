import json
import logging
import queue
import re
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.EndPoint import EndPoint

TOSS_LISTINFO_JSON_URL = "https://static.toss.im/greenhouse/jobs/jobs.json"

TOSS_NAME = "TOSS"

logger = logging.getLogger(config.LOGGER_NAME)


class Toss(EndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = TOSS_LISTINFO_JSON_URL
        self.date_re_pattern = re.compile('(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')
        self.screenshot_width = 1080

    def init_context_entry(self):
        super().init_context(TOSS_NAME)

    def to_valid_datetime(self, date_data):
        matched = self.date_re_pattern.match(date_data)
        assert matched != None
        return datetime.strptime(matched.group(0), "%Y-%m-%dT%H:%M:%S")

    def check_metadata(self, metadata):
        check_list = {"is_pool": bool, "job_description": str, "department": str, "category": str}
        for key in check_list:
            if not key in metadata:
                raise Exception('check_metadata():  metadata doesn`t have valid keys')
            if not isinstance(metadata[key], check_list[key]):
                raise Exception('check_metadata():  metadata doesn`t have valid data type')
        return True

    def make_metadata(self, elements):
        metadata = {"is_pool": None, "job_description": None, "department": None, "category": None}
        for element in elements:
            # Talent_pool
            if element['id'] == 4161116003:
                metadata['is_pool'] = element['value']
            elif element['id'] == 4155730003:
                metadata['job_description'] = element['value']
            elif element['id'] == 4169410003:
                metadata['department'] = element['value']
            elif element['id'] == 4168924003:
                metadata['category'] = element['value']
        return metadata

    def check_category(self, metadata):
        CATEGORY = ["Core System", "Data", "Engineering (Platform)", "Engineering (Product)", "IT", "QA", "Infra",
                    "Security"]
        if metadata['category'] in CATEGORY:
            return True
        return False

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_json_url)

        assert util.check_response(resp, 'text/plain')

        json_data = json.loads(resp.text)
        for recruit_info in json_data:
            elements = recruit_info['metadata']
            metadata = self.make_metadata(elements)

            if metadata['is_pool'] == False and self.check_metadata(metadata) and self.check_category(metadata):
                full_url_path = recruit_info['absolute_url']
                title = recruit_info['title']
                hinted_title = self.to_position_hint_suffixed_title(title, metadata['category'])
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                page_info["md_content"] = metadata['job_description']
                page_info["start_date"] = self.to_valid_datetime(recruit_info['updated_at'])
                self.page_queue.put(page_info)

    def extract_from_endpoint(self):
        local_driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        try:
            driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
            while True:
                page_info = self.page_queue.get(timeout=0)
                self.page_queue.task_done()

                full_url_path = page_info["url"]
                title = page_info["title"]
                desc_hash = page_info["hash"]
                hinted_title = page_info["hinted_title"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                target_xpath = "//div[@class='css-gv536u']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = driver.find_element_by_xpath(target_xpath)
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue
                department = TOSS_NAME
                md_content = page_info['md_content']
                content = self.get_html_content_from_md(md_content)
                text_content = self.get_text_content_from_html(content, local_driver)
                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
        local_driver.quit()
