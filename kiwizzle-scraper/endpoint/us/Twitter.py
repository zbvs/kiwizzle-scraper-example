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

TWITTER_LISTINFO_JSON_URL = "https://careers.twitter.com/content/careers-twitter/en/roles.careers.search.json?location=&offset={PAGE_FROM}&limit={PAGE_SIZE}&sortBy=modified&asc=false&{TEAM_ARRAY}"
TWITTER_BASE_URL = "https://careers.twitter.com"
TWITTER_NAME = "TWITTER"

logger = logging.getLogger(config.LOGGER_NAME)


class Twitter(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = TWITTER_LISTINFO_JSON_URL
        self.base_url = TWITTER_BASE_URL

    def init_context_entry(self):
        super().init_context(TWITTER_NAME)

    def to_valid_datetime(self, date_data):
        milliseconds = 1000000000000
        if date_data > milliseconds:
            date_data = date_data // 1000
        return datetime.fromtimestamp(date_data)

    def is_valid_datedata(self, date_data):
        if type(date_data) is not int:
            return False
        try:
            self.to_valid_datetime(date_data)
        except (ValueError, TypeError) as e:
            logger.warning(f"{self.is_valid_datedata.__name__}() falied to validate date format {date_data}")
            return False
        return True

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        allowed_list = {"Software Engineering": "careers-twitter:sr/team/software-engineering",
                        "Security": "careers-twitter:sr/team/security",
                        "Machine Learning": "careers-twitter:sr/team/machine-learning",
                        "Infrastructure Engineering": "careers-twitter:sr/team/infrastructure-engineering",
                        "IT & IT Enterprise Applications": "careers-twitter:sr/team/it-it-enterprise-applications",
                        "Data Science and Analytics": "careers-twitter:sr/team/data-science-and-analytics"}
        allowed_team_keys = allowed_list.keys()
        team_array = "&".join(map(lambda x: f"team={x}", allowed_list.values()))
        page_size = 100
        resp = self.external_req_get(
            self.listinfo_json_url.format(PAGE_SIZE=page_size, PAGE_FROM=0, TEAM_ARRAY=team_array))
        assert util.check_response(resp, "application/json", 200)
        total_size = resp.json()["totalCount"]
        max_page = self.get_max_page(page_size, total_size)
        for i in range(0, max_page):
            page_from = page_size * i
            resp = self.external_req_get(
                self.listinfo_json_url.format(PAGE_SIZE=page_size, PAGE_FROM=page_from, TEAM_ARRAY=team_array))
            assert util.check_response(resp, "application/json", 200)
            for job in resp.json()["results"]:
                title = job['title']
                full_url_path = job["url"]
                full_url_path = util.get_valid_fullurl(full_url_path, self.base_url)
                teams = list(filter(lambda x: x in allowed_team_keys, map(lambda x: x["title"], job["teams"])))
                if len(teams) == 0:
                    continue

                hinted_title = self.to_position_hint_suffixed_title(title, ",".join(teams))

                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                self.to_valid_datetime(job['modified'])
                if self.is_valid_datedata(job['modified']):
                    page_info["start_date"] = self.to_valid_datetime(job['modified'])
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

                department = TWITTER_NAME
                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()

                target_xpath = "//main[@id='twtr-main']/div/div/div[5]/div/div/div/div[1]/div"
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
