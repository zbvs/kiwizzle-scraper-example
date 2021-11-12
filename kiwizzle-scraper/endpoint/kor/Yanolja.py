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

YANOLJA_LISTINFO_PAGE_URL_1 = "https://recruitment.yanolja.co/go/yanolja/586944/?locale=ko_KR&previewCategory=true&referrerSave=false"
YANOLJA_LISTINFO_PAGE_URL_2 = "https://recruitment.yanolja.co/go/yanolja-cloud/587044/?locale=ko_KR&previewCategory=true&referrerSave=false"
YANOLJA_RECRUIT_PAGE_URL = "https://recruitment.yanolja.co"

YANOLJA_CODE_NAME = "YANOLJA"

logger = logging.getLogger(config.LOGGER_NAME)


class Yanolja(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url_1 = YANOLJA_LISTINFO_PAGE_URL_1
        self.listinfo_page_url_2 = YANOLJA_LISTINFO_PAGE_URL_2
        self.recruit_page_url = YANOLJA_RECRUIT_PAGE_URL
        self.screenshot_width = 700

    def init_context_entry(self):
        super().init_context(YANOLJA_CODE_NAME)

    def extract_job_list(self):
        def extract_from_rendered_page(driver, listinfo_url, team_type):
            driver.get(listinfo_url)
            target_xpath = "//div[@class='career_list_wrap']/div[./p[@class='type'] and @class='career_list']"
            timeout = 1
            try:
                element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                WebDriverWait(driver, timeout).until(element_present)
            except TimeoutException:
                logger.warning(
                    f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : \n{listinfo_url}")

            div_tags = driver.find_elements_by_xpath(target_xpath)

            for div in div_tags:
                p_tag = div.find_element_by_xpath("./p")
                if p_tag.get_attribute('innerText') != team_type:
                    continue

                a_tag = div.find_element_by_xpath("./a")
                path = a_tag.get_attribute("href")
                title = a_tag.get_attribute('innerText')
                hinted_title = title
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                self.page_queue.put(page_info)

        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        extract_from_rendered_page(driver, self.listinfo_page_url_1, "Tech")
        extract_from_rendered_page(driver, self.listinfo_page_url_2, "Tech")

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

                target_xpath = "//div[@class='career_content']/div[@class='content']"
                driver.get(full_url_path)
                timeout = 2
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

                department = YANOLJA_CODE_NAME
                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute('innerText')

                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)


        except queue.Empty:
            pass
        driver.quit()
