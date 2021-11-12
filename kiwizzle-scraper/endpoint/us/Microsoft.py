import logging
import queue
import time
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

MICROSOFT_MAINPAGE_URL = "https://careers.microsoft.com/us/en/search-results?from=80&s=1"
MICROSOFT_LISTINFO_JSON_URL = "https://careers.microsoft.com/widgets"
MICROSOFT_RECRUIT_PAGE_URL = "https://careers.microsoft.com/us/en/job/{JOB_ID}"

MICROSOFT_NAME = "MICROSOFT"

logger = logging.getLogger(config.LOGGER_NAME)


class Microsoft(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.main_page_url = MICROSOFT_MAINPAGE_URL
        self.listinfo_json_url = MICROSOFT_LISTINFO_JSON_URL
        self.recruit_page_url = MICROSOFT_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(MICROSOFT_NAME)
        self.headers = {}
        self.cookies = {}
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.main_page_url)
        test = driver.get_cookies()
        csrf_token = driver.find_element_by_xpath("//div[@id='csrfToken']").get_attribute("innerText")
        self.headers["x-csrf-token"] = csrf_token
        for set_cookie in test:
            name = set_cookie["name"]
            value = set_cookie["value"]
            self.cookies[name] = value
        driver.quit()

    def to_valid_datetime(self, date_data):
        return datetime.fromisoformat(date_data)

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        data_format = {
            "lang": "en_us",
            "deviceType": "desktop",
            "country": "us",
            "ddoKey": "refineSearch",
            "sortBy": "",
            "subsearch": "",
            "from": 0,
            "jobs": True,
            "counts": True,
            "all_fields": [
                "experience",
                "country",
                "state",
                "city",
                "category",
                "subCategory",
                "employmentType",
                "requisitionRoleType",
                "educationLevel"
            ],
            "pageName": "search-results",
            "size": 20,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": "page19",
            "siteType": "external",
            "isMostPopular": True,
            "keywords": "",
            "global": True,
            "selected_fields": {
                "subCategory": [
                    "Researcher",
                    "Cloud Network Engineering",
                    "Software Development",
                    "Site Reliability Engineering",
                    "Software Engineering",
                    "Data & Applied Sciences",
                    "IT Service Engineering",
                    "IT Software Development Engineering"
                ],
                "category": [
                    "Engineering"
                ]
            }
        }

        page_size = 100
        data_format["size"] = page_size
        resp = self.external_req_post(self.listinfo_json_url, json=data_format, headers=self.headers,
                                      cookies=self.cookies)
        assert util.check_response(resp, "application/json", 200)
        total_size = resp.json()["refineSearch"]["totalHits"]
        max_page = self.get_max_page(page_size, total_size)

        for i in range(0, max_page):
            page_from = page_size * i
            data_format["from"] = page_from
            resp = self.external_req_post(self.listinfo_json_url, json=data_format, headers=self.headers,
                                          cookies=self.cookies)
            for node in resp.json()["refineSearch"]["data"]["jobs"]:
                job_id = node['jobId']
                title = node['title']
                full_url_path = self.recruit_page_url.format(JOB_ID=job_id)
                hinted_title = self.to_position_hint_suffixed_title(title, node['subCategory'])
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                if self.is_valid_datedata(node['postedDate']):
                    page_info["start_date"] = self.to_valid_datetime(node['postedDate'])
                else:
                    page_info["start_date"] = self.invalid_datetime()
                self.page_queue.put(page_info)
            time.sleep(0.5)

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

                department = MICROSOFT_NAME

                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()

                image_xpath = "//div[@id='content-1']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, image_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = self.get_element_by_xpath(image_xpath, driver)
                if div is None:
                    continue

                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                content_xpath = "//div[@id='content-1']/div[@class='job-description']"
                div = self.get_element_by_xpath(content_xpath, driver)
                if div is None:
                    continue

                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
