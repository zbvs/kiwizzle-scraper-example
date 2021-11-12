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

NETFLIX_TEAM_DICT = {
    "Core Engineering": 55,
    "Creative Production": 42,
    "Legal and Public Policy": 30,
    "Finance": 29,
    "Content Legal": 19,
    "Talent and Recruiting": 19,
    "Creative Marketing Production": 18,
    "Post Production Management": 18,
    "Production Management": 17,
    "Security": 17,
    "Client and UI Engineering": 15,
    "Marketing": 15,
    "Data Science and Engineering": 14,
    "Production Services and Technology": 14,
    "Product Management": 13,
    "Netflix Technology Services": 12,
    "Publicity": 12,
    "Corporate Real Estate, Employee Health, Workplace, and Security": 11,
    "Strategy and Analysis": 11,
    "Design": 10,
    "Financial Planning and Analysis": 10,
    "Consumer Insights": 9,
    "Partnership": 9,
    "Content Acquisition": 8,
    "Editorial and Publishing": 7,
    "Studio Technologies": 7,
    "Customer Service": 5,
    "Legal": 5,
    "Communications": 4,
    "Regional Marketing": 4,
    "Human Resources": 3,
    "Video Encoding and Streaming": 3,
    "Consumer Products": 2,
    "Corporate Real Estate, Workplace, Safety and Security": 2,
    "Creative Content": 2,
    "Creative Services": 2,
    "Employee Technology": 2,
    "Post Production": 2,
    "VFX and Virtual Production": 2,
    "Brand and Editorial": 1,
    "Content Planning and Analysis": 1,
    "Editorial Creative": 1,
    "Facilities, Workplace Services and Real Estate": 1,
    "Marketing Operations": 1,
    "PR": 1,
    "Partner Marketing": 1,
    "Production": 1
}

NETFLIX_LISTINFO_JSON_URL = "https://jobs.netflix.com/api/search?team={TEAM_ARRAY}&page={PAGE}"
NETFLIX_RECRUIT_PAGE_URL = "https://jobs.netflix.com/jobs/{JOB_ID}"

NETFLIX_NAME = "NETFLIX"
logger = logging.getLogger(config.LOGGER_NAME)


class Netflix(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = NETFLIX_LISTINFO_JSON_URL
        self.recruit_page_url = NETFLIX_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(NETFLIX_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%SZ")

    def get_max_page(self, resp):
        return resp.json()["info"]["postings"]["num_pages"]

    def extract_job_list(self):
        team_list = ["Client and UI Engineering", "Core Engineering", "Data Science and Engineering",
                     "Studio Technologies", "VFX and Virtual Production", "Video Encoding and Streaming"]
        team_array = "~".join(team_list)

        resp = self.external_req_get(self.listinfo_json_url.format(PAGE=1, TEAM_ARRAY=team_array))
        assert util.check_response(resp, "application/json", 200)
        max_page = self.get_max_page(resp)

        for i in range(0, max_page):
            page = i + 1
            resp = self.external_req_get(self.listinfo_json_url.format(PAGE=page, TEAM_ARRAY=team_array))
            assert util.check_response(resp, "application/json", 200)
            jobs = resp.json()["records"]["postings"]
            for job in jobs:
                title = job["text"]
                full_url_path = self.recruit_page_url.format(JOB_ID=job["external_id"])

                if "subteam" in job:
                    team = ", ".join(job["subteam"])
                else:
                    team = ", ".join(job["team"])
                hinted_title = self.to_position_hint_suffixed_title(title, team)
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                if self.is_valid_datedata(job['created_at']):
                    page_info["start_date"] = self.to_valid_datetime(job['created_at'])
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

                department = NETFLIX_NAME
                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()
                target_xpath = "//section[@id='job-content']/div/div/div[2]/div[1]/div[2]"
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
