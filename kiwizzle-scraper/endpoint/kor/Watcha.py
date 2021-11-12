import logging
import queue
import re

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

WATCHA_LISTINFO_PAGE_URL = "https://watcha.team/fb9d1a3f-c79a-4430-8eb7-4e972027af2a"
WATCHA_RECRUIT_PAGE_URL = "https://watcha.team{PATH}"
WATCHA_NAME = "WATCHA"

logger = logging.getLogger(config.LOGGER_NAME)


class Watcha(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = WATCHA_LISTINFO_PAGE_URL
        self.recruit_page_url = WATCHA_RECRUIT_PAGE_URL
        self.screenshot_width = 1080

    def init_context_entry(self):
        super().init_context(WATCHA_NAME)

    def extract_path(self, page_driver, path):
        rule = "^(http://|https://).*"
        if re.match(rule, path):
            full_url_path = path
        else:
            full_url_path = self.recruit_page_url.format(PATH=path)
        page_driver.get(full_url_path)
        timeout = 3
        try:
            element_present = EC.presence_of_element_located(
                (By.XPATH, "//div[@class='js-job-title rb-text-1']"))
            WebDriverWait(page_driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {full_url_path}")
            return None
        title = page_driver.find_element_by_xpath("//div[@class='js-job-title rb-text-1']").get_attribute(
            "innerText")
        hinted_title = title
        full_url_path = page_driver.current_url
        desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
        is_new = self.check_hash_not_exist(desc_hash)
        company_id = self.company_id
        department = WATCHA_NAME
        div = page_driver.find_element_by_xpath("//div[@class='jobdesciption']")
        screenshot, div = self.get_screenshot(div, page_driver)
        if screenshot is None:
            return None
        content = div.get_attribute("outerHTML")
        text_content = div.get_attribute("innerText")
        start_date = self.invalid_datetime()
        end_date = self.invalid_datetime()

        page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                     "is_new": is_new}

        page_info["screenshot"] = screenshot
        page_info["content"] = content
        page_info["text_content"] = text_content
        page_info["company_id"] = company_id
        page_info["department"] = department
        page_info["start_date"] = start_date
        page_info["end_date"] = end_date
        return page_info

    def extract_job_list(self):
        main_driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        main_driver.get(self.listinfo_page_url)
        target_xpath = "//div[contains(@class, 'notion-page-content')]"
        timeout = 1
        try:
            element_present = EC.presence_of_element_located((By.XPATH,
                                                              "//div[contains(@class, 'notion-page-content')]"))
            WebDriverWait(main_driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_xpath}")

        divider_start = main_driver.find_element_by_xpath(
            "//div[@class='notion-page-content width padding']//div[contains(@class, 'notion-sub_header-block') and .//h3[text()='여러 개발직군 채용을 진행하고 있어요']]")
        divider_end = main_driver.find_element_by_xpath(
            "//div[@class='notion-page-content width padding']//div[contains(@class, 'notion-sub_header-block') and .//h3[text()='왓챠에서 함께 성장해나가요']]")

        parent = main_driver.find_elements_by_xpath(
            "//div[@class='notion-page-content width padding']")
        parent = parent[0]
        divs = parent.find_elements_by_xpath(".//div[@data-block-id]")

        prev_size = len(divs)
        for i in range(0, len(divs)):
            div = divs[i]
            if div.get_attribute("data-block-id") == divider_start.get_attribute("data-block-id"):
                divs = divs[i:]
                break
        assert prev_size != len(divs)
        prev_size = len(divs)
        for i in range(0, len(divs)):
            div = divs[i]
            if div.get_attribute("data-block-id") == divider_end.get_attribute("data-block-id"):
                divs = divs[:i]
                break
        assert prev_size != len(divs)
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(divs):" + str(len(divs)))

        page_driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        for div in divs:
            a_tags = div.find_elements_by_xpath(".//div/a[@class='notion-link-token notion-enable-hover']")
            if len(a_tags) != 1:
                continue
            path = a_tags[0].get_attribute("href")
            page_info = self.extract_path(page_driver, path)
            if page_info is not None:
                self.page_queue.put(page_info)
        main_driver.quit()

    def extract_from_endpoint(self):
        try:
            while True:
                page_info = self.page_queue.get(timeout=0)
                self.page_queue.task_done()

                full_url_path = page_info["url"]
                title = page_info["title"]
                desc_hash = page_info["hash"]
                hinted_title = page_info["hinted_title"]
                is_new = page_info["is_new"]
                company_id = page_info["company_id"]

                screenshot = page_info["screenshot"]
                content = page_info["content"]
                text_content = page_info["text_content"]
                department = page_info["department"]
                start_date = page_info["start_date"]
                end_date = page_info["end_date"]

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
