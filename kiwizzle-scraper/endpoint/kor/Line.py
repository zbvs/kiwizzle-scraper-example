import json
import logging
import queue
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

LINE_LISTINFO_JSON_URL = "https://careers.linecorp.com/page-data/ko/jobs/page-data.json"
LINE_RECURUIT_JSON_URL = "https://careers.linecorp.com/page-data/ko/jobs/{page_num}/page-data.json"
LINE_RECRUIT_PAGE_URL = "https://careers.linecorp.com/ko/jobs/{page_num}"

LINE_NAME = "LINE"

logger = logging.getLogger(config.LOGGER_NAME)


class Line(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = LINE_LISTINFO_JSON_URL
        self.recruit_json_url = LINE_RECURUIT_JSON_URL
        self.recruit_page_url = LINE_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_context(LINE_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%S.%fZ")

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_json_url)
        assert util.check_response(resp, "application/json")

        json_data = json.loads(resp.text)
        jobs = json_data['result']['data']['allStrapiJobs']
        totalCount = jobs['totalCount']
        node_array = jobs['edges']
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() totalCount:" + str(totalCount))

        assert len(node_array) == totalCount

        for info_object in node_array:
            def check_pageinfo(info_node):
                for jobunit_node in info_node["job_unit"]:
                    if jobunit_node["name"] == "Engineering":
                        return True
                return False

            def extract_title(info_node):
                hint = ""
                for jobfield_node in info_node["job_fields"]:
                    hint += jobfield_node["name"] + ", "
                if len(hint) > 0:
                    hint = hint[:-2]
                return self.to_position_hint_suffixed_title(info_node["title"], hint)

            info_node = info_object['node']
            json_url = self.recruit_json_url.format(page_num=info_node["strapiId"])
            full_url_path = self.recruit_page_url.format(page_num=info_node["strapiId"])
            title = info_node["title"]
            hinted_title = extract_title(info_node)
            if info_node["publish"] and check_pageinfo(info_node):
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["json_url"] = json_url
                self.page_queue.put(page_info)

    def extract_from_endpoint(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        try:
            while True:
                page_info = self.page_queue.get(timeout=0)
                self.page_queue.task_done()

                full_url_path = page_info["url"]
                title = page_info["title"]
                hinted_title = page_info["hinted_title"]
                desc_hash = page_info["hash"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                json_url = page_info["json_url"]
                resp = self.external_req_get(json_url)

                assert util.check_response(resp, "application/json")

                department = LINE_NAME

                target_xpath = "//section[@id='jobs-contents']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                section = self.get_element_by_xpath(target_xpath, driver)
                if section is None:
                    continue

                screenshot, section = self.get_screenshot(section, driver)
                if screenshot is None:
                    continue

                content = section.get_attribute('outerHTML')
                text_content = section.get_attribute("innerText")

                json_data = json.loads(resp.text)
                job_desc = json_data['result']['data']['strapiJobs']

                assert type(job_desc['start_date']) == str
                start_date = self.to_valid_datetime(job_desc['start_date'])

                if job_desc['end_date'] != None:
                    assert type(job_desc['end_date']) == str
                    end_date = self.to_valid_datetime(job_desc['end_date'])
                else:
                    end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
