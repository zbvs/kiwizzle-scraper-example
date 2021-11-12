import logging
import queue
import re
from datetime import datetime

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.EndPoint import EndPoint

HYPERCONNECT_BASE_URL = "https://career.hyperconnect.com"
HYPERCONNECT_MAIN_URL = "https://career.hyperconnect.com/jobs"
HYPERCONNECT_RECRUIT_PAGE_URL = "https://career.hyperconnect.com/job/{PAGE_ID}"
HYPERCONNECT_NAME = "HYPERCONNECT"

logger = logging.getLogger(config.LOGGER_NAME)


class Hyperconnect(EndPoint):
    def __init__(self):
        super().__init__()
        self.base_url = HYPERCONNECT_BASE_URL
        self.main_page_url = HYPERCONNECT_MAIN_URL
        self.recruit_page_url = HYPERCONNECT_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_context(HYPERCONNECT_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "영입종료시":
            return self.invalid_datetime()
        else:
            return datetime.strptime(date_data, "%Y년 %m월 %d일 까지")

    def extract_job_list(self):
        allowed_teams = ["DATA", "ENGINEERING"]
        resp = self.external_req_get(self.main_page_url)
        assert util.check_response(resp, 'text/html')
        bs = BeautifulSoup(resp.text, 'html.parser')
        href_pattern = re.compile('^/page-data/sq/d/*')
        links = bs.find("head").find_all("link",
                                         {"rel": "preload", "href": lambda src: src and href_pattern.match(src)})

        href_pattern = re.compile('^/page-data/sq/d/*')
        json_data = None
        for link in links:
            url = self.base_url + link["href"]
            resp = self.external_req_get(url)
            if resp.text.find("applyStepImg") != -1:
                json_data = resp.json()
                break

        assert json_data is not None
        nodes = json_data["data"]["allLever"]["nodes"]

        for node in nodes:
            team = node["categories"]["team"]
            if team not in allowed_teams:
                continue
            title = node["text"]
            hinted_title = self.to_position_hint_suffixed_title(title, team)
            full_url_path = self.recruit_page_url.format(PAGE_ID=node["lever_id"])
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}
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

                target_xpath = "//div/main/div[@class='MuiContainer-root MuiContainer-maxWidthLg']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                department = HYPERCONNECT_NAME
                div = driver.find_element_by_xpath(target_xpath)
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                content = div.get_attribute("innerHTML")
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()
                driver.execute_script("window.history.go(-1)")

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
