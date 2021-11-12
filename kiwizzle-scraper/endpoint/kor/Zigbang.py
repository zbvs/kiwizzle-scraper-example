import logging
import queue

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

ZIGBANG_LISTINFO_PAGE_URL = "https://career.zigbang.com/f427eee2-b913-4b21-948a-3a7f5e8de42a"
ZIGBANG_LISTINFO_PAGE_URL2 = "https://career.zigbang.com/d800a2ae-bab9-407d-8cf1-c009e55d46db"
ZIGBANG_RECRUIT_PAGE_URL = "https://career.zigbang.com"
ZIGBANG_NAME = "ZIGBANG"

logger = logging.getLogger(config.LOGGER_NAME)


class Zigbang(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = ZIGBANG_LISTINFO_PAGE_URL
        self.listinfo_page_url2 = ZIGBANG_LISTINFO_PAGE_URL2
        self.recruit_page_url = ZIGBANG_RECRUIT_PAGE_URL
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.chrome_options = options

    def init_context_entry(self):
        super().init_context(ZIGBANG_NAME)

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)

        def extract_job_per_url(listinfo_page_url):
            driver.get(listinfo_page_url)
            target_xpath = "//div[@class='notion-scroller horizontal']"
            timeout = 2
            try:
                element_present = EC.presence_of_element_located(
                    (By.XPATH, target_xpath))
                WebDriverWait(driver, timeout).until(element_present)
            except TimeoutException:
                logger.warning(
                    f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_xpath}")

            divs = driver.find_elements_by_xpath(
                "//div[@class='notion-scroller horizontal']//div[contains(@class,'notion-page-block notion-collection-item')]")

            logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(a_tags):" + str(len(divs)))
            for div in divs:
                a_tags = div.find_elements_by_xpath("./a")
                if len(a_tags) != 1:
                    continue
                a_tag = a_tags[0]
                path = a_tag.get_attribute("href")
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                title = a_tag.get_attribute("innerText")
                titles = title.split("\n")
                if len(titles) > 1:
                    title = titles[0]
                    hinted_title = self.to_position_hint_suffixed_title(titles[0], titles[1])
                else:
                    title = titles[0]
                    hinted_title = titles[0]
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                self.page_queue.put(page_info)

        extract_job_per_url(self.listinfo_page_url)
        extract_job_per_url(self.listinfo_page_url2)
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

                driver.get(full_url_path)
                timeout = 3
                try:
                    element_present = EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class,'notion-page-content')]"))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = driver.find_element_by_xpath("//div[contains(@class,'notion-page-content')]")
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                department = ZIGBANG_NAME
                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
