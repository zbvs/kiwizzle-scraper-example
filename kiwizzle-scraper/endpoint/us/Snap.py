import base64
import logging
import os
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

SNAP_LISTINFO_JSON_URL = "https://snap.com/api/jobs"
SNAP_CODE_NAME = "SNAP"

logger = logging.getLogger(config.LOGGER_NAME)


class Snap(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = SNAP_LISTINFO_JSON_URL

    def init_context_entry(self):
        if not self.check_is_company_exist(SNAP_CODE_NAME):
            category_ids = list(
                map(lambda x: x["categoryId"], self.get_category_id_from_api_server(["PORTAL_MESSENGER"])))
            country_id = self.get_country_id_from_api_server("US")
            pattern = {
                "rolePattern": "What you’ll do",
                "requirePattern": "(Knowledge, Skills, Abilities|Minimum Requirements)",
                "preferredPattern": "Preferred qualifications",
                "endPattern": ""
            }

            path = os.getcwd()
            with open(path + "/img/" + self.__class__.__name__ + ".png", "rb") as f:
                logo = base64.b64encode(f.read()).decode("ascii")
            request = {"companyCode": SNAP_CODE_NAME, "publicNameEng": "Snap", "publicNameKor": "Snap",
                       "pattern": pattern, "logo": logo,
                       "detail": {"parent": None, "isGroup": False, "category": category_ids, "country": country_id}}
            self.create_company_from_api_server(request)
        super().init_context(SNAP_CODE_NAME)

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_json_url)
        assert util.check_response(resp, "application/json", 200)
        allowed_role = ["Data & Analytics", "Engineering"]
        jobs = resp.json()["data"]["Report_Entry"]

        for job in jobs:
            title = job['title']
            full_url_path = job["absolute_url"]
            if job["role"] not in allowed_role:
                continue
            hinted_title = self.to_position_hint_suffixed_title(title, job["departments"])
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

                department = SNAP_CODE_NAME
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                target_xpath = "//div[@id='richTextArea.jobPosting.jobDescription-input']"
                driver.get(full_url_path)

                timeout = 4
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
