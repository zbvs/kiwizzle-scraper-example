import logging
import queue
import re
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

GOOGLE_MAINPAGE_URL = "https://careers.google.com/jobs/results/?distance=50&page={PAGE}&q="
GOOGLE_LISTINFO_JSON_URL = "https://careers.google.com/api/v3/search/?page={PAGE}&distance=50&{CATEGORY_ARRAY}&q="
GOOGLE_RECRUIT_PAGE_URL = "https://careers.google.com/jobs/results/{JOB_URL}"

GOOGLE_NAME = "GOOGLE"
GOOGLE_PAGE_SIZE = 20
logger = logging.getLogger(config.LOGGER_NAME)


class Google(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.mainpage_url = GOOGLE_MAINPAGE_URL
        self.listinfo_json_url = GOOGLE_LISTINFO_JSON_URL
        self.recruit_page_url = GOOGLE_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(GOOGLE_NAME)

    def to_valid_datetime(self, date_data):
        if re.match(".*\.\d*Z$", date_data) is not None:
            return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%SZ")

    def get_max_page(self, resp):
        total_size = resp.json()["count"]
        return (total_size // GOOGLE_PAGE_SIZE) + (1 if total_size % GOOGLE_PAGE_SIZE != 0 else 0)

    def extract_job_list(self):
        google_all_categories = {'TECHNICAL_INFRASTRUCTURE_ENGINEERING', 'PRODUCT_SUPPORT', 'TECHNICAL_SOLUTIONS',
                                 'SOFTWARE_ENGINEERING', 'NETWORK_ENGINEERING', 'TECHNICAL_WRITING',
                                 'HARDWARE_ENGINEERING',
                                 'MANUFACTURING_SUPPLY_CHAIN', 'DATA_CENTER_OPERATIONS', 'ADMINISTRATIVE', 'FINANCE',
                                 'PROGRAM_MANAGEMENT', 'MARKETING', 'PEOPLEOPS', 'USER_EXPERIENCE', 'PARTNERSHIPS',
                                 'PRODUCT_MANAGEMENT', 'INFORMATION_TECHNOLOGY', 'REAL_ESTATE', 'BUSINESS_STRATEGY',
                                 'DEVELOPER_RELATIONS', 'LEGAL', 'SALES_OPERATIONS', 'SALES'}

        category_list = ["TECHNICAL_INFRASTRUCTURE_ENGINEERING", "SOFTWARE_ENGINEERING", "NETWORK_ENGINEERING",
                         "INFORMATION_TECHNOLOGY", "DEVELOPER_RELATIONS"]
        category_array = "&".join(map(lambda x: f"category={x}", category_list))

        resp = self.external_req_get(self.listinfo_json_url.format(PAGE=0, CATEGORY_ARRAY=category_array))
        assert util.check_response(resp, "application/json", 200)
        max_page = self.get_max_page(resp)

        for i in range(0, max_page):
            page = i + 1
            resp = self.external_req_get(self.listinfo_json_url.format(PAGE=page, CATEGORY_ARRAY=category_array))
            assert util.check_response(resp, "application/json", 200)
            jobs = resp.json()["jobs"]
            for job in jobs:
                title = job["title"]
                hinted_title = self.to_position_hint_suffixed_title(title, ",".join(job["categories"]))
                id = re.search('jobs/(\d+)', job["id"]).groups()[0]
                result = re.sub("-+", "-", re.sub("[^A-Za-z0-9]", "-", title))
                job_url = id + "-" + result
                full_url_path = self.recruit_page_url.format(JOB_URL=job_url)

                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                page_info["department"] = job["company_name"]
                if self.is_valid_datedata(job['publish_date']):
                    page_info["start_date"] = self.to_valid_datetime(job['publish_date'])
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

                department = page_info["department"]
                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()

                target_xpath = "//div[@id='jump-content']//div[@itemscope='itemscope']//div[@class='gc-card__content']"
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
                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
