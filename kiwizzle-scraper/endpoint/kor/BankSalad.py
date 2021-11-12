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

BANKSALAD_LISTINFO_PAGE_URL = "https://career.banksalad.com/jobs/"
BANKSALAD_RECRUIT_PAGE_URL = "https://career.banksalad.com"

BANKSALAD_NAME = "BANK_SALAD"

logger = logging.getLogger(config.LOGGER_NAME)


class BankSalad(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = BANKSALAD_LISTINFO_PAGE_URL
        self.recruit_page_url = BANKSALAD_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(BANKSALAD_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "영입종료시":
            return self.invalid_datetime()
        else:
            return datetime.strptime(date_data, "%Y년 %m월 %d일 까지")

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_page_url)

        target_xpath = "//div[./h4[text()='테크']]/ul/li/a"
        timeout = 6
        try:
            element_present = EC.presence_of_element_located((By.XPATH,
                                                              target_xpath))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_xpath}")

        a_tags = driver.find_elements_by_xpath("//div[./h4[text()='테크']]/ul/li/a")
        a_tags.extend(driver.find_elements_by_xpath("//div[./h4[text()='데이터']]/ul/li/a"))
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(a_tags):" + str(len(a_tags)))
        for a_tag in a_tags:
            path = a_tag.get_attribute("href")
            full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
            title = a_tag.get_attribute("innerText")
            hinted_title = title
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}
            self.page_queue.put(page_info)

        driver.quit()

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

                target_xpath = "//div[@class='job-sections']/div[@itemprop='description']"
                driver.get(full_url_path)
                timeout = 4
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = driver.find_element_by_xpath(target_xpath)
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                div = driver.find_element_by_xpath(target_xpath)
                department = BANKSALAD_NAME
                content = div.get_attribute('innerHTML')
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
