import logging
import queue

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

AIRBNB_LISTINFO_JSON_URL = "https://careers.airbnb.com/wp-admin/admin-ajax.php?action=fetch_greenhouse_jobs&which-board=airbnb&strip-empty=true"
AIRBNB_RECRUIT_PAGE_URL = "https://careers.airbnb.com/positions/{JOB_ID}/"

AIRBNB_NAME = "AIRBNB"

logger = logging.getLogger(config.LOGGER_NAME)


class Airbnb(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = AIRBNB_LISTINFO_JSON_URL
        self.recruit_page_url = AIRBNB_RECRUIT_PAGE_URL
        self.screenshot_width = 1000

    def init_context_entry(self):
        super().init_context(AIRBNB_NAME)

    def extract_job_list(self):
        allowed_departments = [
            {
                "id": 73249,
                "name": "Airbnb Capability Center",
                "jobCount": 19
            },
            {
                "id": "Data Science/Analytics",
                "name": "Data Science/Analytics",
                "jobCount": 10
            },
            {
                "id": "Engineering",
                "name": "Engineering",
                "jobCount": 61
            },
            {
                "id": 73703,
                "name": "Engineering & Technology",
                "jobCount": 1
            }
        ]

        resp = self.external_req_get(self.listinfo_json_url)
        assert util.check_response(resp, "application/json", 200)

        for job in resp.json()["jobs"]:
            job_id = job['id']
            title = job['title']

            full_url_path = self.recruit_page_url.format(JOB_ID=job_id)

            dept_name = job['deptId']

            if dept_name not in map(lambda x: x["id"], allowed_departments):
                continue

            if type(dept_name) is int:
                dept_name = next(filter(lambda x: x["id"] == dept_name, allowed_departments))["name"]
            hinted_title = self.to_position_hint_suffixed_title(title, dept_name)
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            if self.is_processed_hash(desc_hash):
                continue

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}

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

                department = AIRBNB_NAME

                target_xpath = "//main//div[@class='container']//div[@class='page-positions__overview active']"
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

                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
