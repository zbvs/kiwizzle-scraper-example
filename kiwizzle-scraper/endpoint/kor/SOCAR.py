import logging
import queue
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

SOCAR_LISTINFO_PAGE_URL = "https://www.notion.so/d458b6b77a2243fb873d1ac800c321f7"
SOCAR_RECRUIT_PAGE_URL = "https://www.notion.so"
SOCAR_NAME = "SOCAR"

logger = logging.getLogger(config.LOGGER_NAME)


class SOCAR(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = SOCAR_LISTINFO_PAGE_URL
        self.recruit_page_url = SOCAR_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_context(SOCAR_NAME)

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_page_url)

        time.sleep(2)
        target_xpath = "//div[@class='notion-selectable notion-page-block']"
        timeout = 2
        try:
            element_present = EC.presence_of_element_located(
                (By.XPATH, target_xpath))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_xpath}")

        key_list = ["개발", "데이터", "프로덕트", "모빌리티시스템"]
        for key in key_list:
            parent_div = driver.find_element_by_xpath(
                "//div[@class='notion-page-content']/div[@class='notion-selectable notion-collection_view-block'" +
                f" and .//div[@placeholder and text()='{key}']]")
            a_tags = parent_div.find_elements_by_xpath(
                ".//div[@class='notion-list-view']/div[@class='notion-selectable notion-collection_view-block']//a")
            logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(a_tags):" + str(len(a_tags)))
            for a_tag in a_tags:
                path = a_tag.get_attribute("href")
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                titles = a_tag.get_attribute("innerText")
                lines = titles.split("\n")
                title = lines[0]
                hinted_title = self.to_experience_hint_suffixed_title(title, "경력 " + lines[1])
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
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
                hinted_title = page_info["hinted_title"]
                desc_hash = page_info["hash"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                target_xpath = "//div[@class='notion-page-content']"
                driver.get(full_url_path)
                timeout = 3
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

                department = SOCAR_NAME
                content = div.get_attribute('innerHTML')
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        finally:
            driver.quit()
