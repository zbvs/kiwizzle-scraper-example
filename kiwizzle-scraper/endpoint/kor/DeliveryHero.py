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

DELIVERYHERO_LISTINFO_PAGE_URL = "https://boards.greenhouse.io/deliveryherokoreatech?gh_src=af60f52a2"
DELIVERYHERO_RECRUIT_PAGE_URL = "https://boards.greenhouse.io"
DELIVERYHERO_NAME = "DELIVERY_HERO"

logger = logging.getLogger(config.LOGGER_NAME)


class DeliveryHero(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = DELIVERYHERO_LISTINFO_PAGE_URL
        self.recruit_page_url = DELIVERYHERO_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(DELIVERYHERO_NAME)

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_page_url)

        target_xpath = "//section/div[@class='opening']"
        timeout = 1
        try:
            element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {target_xpath}")

        div_tags = driver.find_elements_by_xpath(target_xpath)

        for div_tag in div_tags:
            a_tag = div_tag.find_element_by_xpath("./a")
            path = a_tag.get_attribute("href")
            path = path.split("?")[0]
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
                desc_hash = page_info["hash"]
                hinted_title = page_info["hinted_title"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                driver.get(full_url_path)
                timeout = 3
                try:
                    element_present = EC.presence_of_element_located(
                        (By.XPATH, "//div[@id='app_body']/div[@id='content']"))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue
                div = driver.find_element_by_xpath("//div[@id='app_body']/div[@id='content']")
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                department = DELIVERYHERO_NAME
                content = div.get_attribute('innerHTML')
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
