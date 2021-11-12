import json
import logging
import queue
import re

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

DAANGNMARKET_LISTINFO_PAGE_URL = "https://team.daangn.com/page-data/jobs/page-data.json"
DAANGNMARKET_RECRUIT_PAGE_URL = "https://team.daangn.com"
DAANGNMARKET_NAME = "DAANGN_MARKET"

logger = logging.getLogger(config.LOGGER_NAME)


class DaangnMarket(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = DAANGNMARKET_LISTINFO_PAGE_URL
        self.recruit_page_url = DAANGNMARKET_RECRUIT_PAGE_URL
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.chrome_options = options

    def init_context_entry(self):
        super().init_context(DAANGNMARKET_NAME)

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_json_url)
        assert util.check_response(resp, "application/json")

        json_data = json.loads(resp.text)
        nodes = json_data['result']['data']['currentJobPosts']["nodes"]
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(jobs):" + str(len(nodes)))

        for node in nodes:
            def check_position(job_group):
                rule = "^(개발|데이터).*"
                if re.match(rule, job_group):
                    return True
                return False

            external_url = node['externalUrl']
            if external_url is not None:
                is_notion = True
                full_url_path = external_url
            else:
                path = node['absoluteUrl']
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                is_notion = False
            title = node['title']
            job_group = node['chapter']

            if check_position(job_group):
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                hinted_title = self.to_position_hint_suffixed_title(title, job_group)
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["is_notion"] = is_notion
                self.page_queue.put(page_info)

    def extract_from_endpoint(self):
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

                driver.get(full_url_path)
                if page_info["is_notion"]:
                    target_xpath = "//div[@class='notion-scroller vertical horizontal']/div[@class='notion-page-content']"
                else:
                    target_xpath = "//main/div/div/article"

                timeout = 3
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue
                target_element = driver.find_element_by_xpath(target_xpath)
                screenshot, target_element = self.get_screenshot(target_element, driver)
                if screenshot is None:
                    continue

                department = DAANGNMARKET_NAME
                content = target_element.get_attribute('outerHTML')
                text_content = target_element.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
