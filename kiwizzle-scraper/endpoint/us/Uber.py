import logging
import queue
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

UBER_LISTINFO_JSON_URL = "https://www.uber.com/api/loadSearchJobsResults?localeCode=en"
UBER_RECRUIT_PAGE_URL = "https://www.uber.com/careers/list/{JOB_ID}/"

UBER_NAME = "UBER"

logger = logging.getLogger(config.LOGGER_NAME)


class Uber(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = UBER_LISTINFO_JSON_URL
        self.recruit_page_url = UBER_RECRUIT_PAGE_URL
        self.screenshot_width = 1000

    def init_context_entry(self):
        super().init_context(UBER_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%S.%fZ")

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        page_size = 100
        format = {"params": {"department": ["Data Science", "Engineering"]}, "limit": page_size, "page": 0}
        headers = {"x-csrf-token": "x"}
        resp = self.external_req_post(self.listinfo_json_url, headers=headers, json=format)
        assert util.check_response(resp, "application/json", 200)
        total_size = resp.json()["data"]["totalResults"]["low"]
        self.get_max_page(page_size, total_size)
        max_page = self.get_max_page(page_size, total_size)

        for i in range(0, max_page):
            format["page"] = i
            resp = self.external_req_post(self.listinfo_json_url, headers=headers, json=format)
            assert util.check_response(resp, "application/json", 200)

            for job in resp.json()["data"]["results"]:
                job_id = job['id']
                title = job['title']
                full_url_path = self.recruit_page_url.format(JOB_ID=job_id)
                hinted_title = self.to_position_hint_suffixed_title(title, job['team'])
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                if self.is_valid_datedata(job['creationDate']):
                    page_info["start_date"] = self.to_valid_datetime(job['creationDate'])
                else:
                    page_info["start_date"] = self.invalid_datetime()
                self.page_queue.put(page_info)

    def extract_from_endpoint(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.set_window_size(self.screenshot_width, self.screenshot_height)
        try:
            while True:
                page_info = self.page_queue.get(timeout=0)
                self.page_queue.task_done()
                remained_size = self.page_queue.unfinished_tasks
                if remained_size % 100 == 0:
                    logger.info("remained_size:" + str(remained_size))
                full_url_path = page_info["url"]
                title = page_info["title"]
                hinted_title = page_info["hinted_title"]
                desc_hash = page_info["hash"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                department = UBER_NAME
                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()

                target_xpath = "//main[@id='main']/div[2]/div/div/div[3]"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = self.get_element_by_xpath(target_xpath, driver, title=title)
                if div is None:
                    continue

                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue
                try:
                    content = div.get_attribute('outerHTML')
                    text_content = div.get_attribute("innerText")
                except StaleElementReferenceException as e:
                    logger.warning(
                        f"[{self.__class__.__name__}] uber.extract_from_endpoint() StaleElementReferenceException: {e}\n")
                    continue

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
