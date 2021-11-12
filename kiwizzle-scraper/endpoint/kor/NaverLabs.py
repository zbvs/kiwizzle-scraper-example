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
from endpoint.classes.EndPoint import EndPoint

NAVERLABS_LISTINFO_PAGE_URL = "https://recruit.naverlabs.com/labs/recruitMain"
NAVERLABS_RECRUIT_PAGE_URL = "https://recruit.naverlabs.com/labs/recruitMain?recruitId={PAGE_NUM}"
NAVERLABS_NAME = "NAVER_LABS"

logger = logging.getLogger(config.LOGGER_NAME)


class NaverLabs(EndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = NAVERLABS_LISTINFO_PAGE_URL
        self.recruit_page_url = NAVERLABS_RECRUIT_PAGE_URL
        self.screenshot_width = 1080

    def init_context_entry(self):
        super().init_context(NAVERLABS_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "영입종료시":
            return self.invalid_datetime()
        else:
            return datetime.strptime(date_data, "%Y년 %m월 %d일 까지")

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_page_url)
        target_iterating_li_xpath = "//ul[@class='jobs_list']/li[@class='jobs_item']"
        timeout = 1
        try:
            element_present = EC.presence_of_element_located((By.XPATH,
                                                              target_iterating_li_xpath))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_iterating_li_xpath}")

        li_size = len(driver.find_elements_by_xpath(target_iterating_li_xpath))
        for i in range(0, li_size):
            li = driver.find_elements_by_xpath(target_iterating_li_xpath)[i]
            li_id = li.get_attribute("id")
            full_url_path = self.recruit_page_url.format(PAGE_NUM=li_id)
            title = li.get_attribute("innerText")
            hinted_title = title

            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}

            page_info["li_index"] = i
            self.page_queue.put(page_info)

        driver.quit()

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

                target_xpath = ".//div[@class='pop_content_area']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                li_index = page_info["li_index"]
                target_iterating_li_xpath = "//ul[@class='jobs_list']/li[@class='jobs_item']"
                li_new_page = driver.find_elements_by_xpath(target_iterating_li_xpath)[li_index]
                target_xpath = ".//div[@class='pop_content_area']"
                div = li_new_page.find_element_by_xpath(target_xpath)
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                target_xpath = ".//div[@class='pop_content_area']/dl[@class='pop_desc_list']"
                dl = li_new_page.find_element_by_xpath(target_xpath)

                department = NAVERLABS_NAME
                content = dl.get_attribute('innerHTML')
                text_content = dl.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)
        except queue.Empty:
            pass
        driver.quit()
