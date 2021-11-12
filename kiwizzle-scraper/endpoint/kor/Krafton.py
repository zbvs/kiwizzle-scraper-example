import logging
import queue
import re
from datetime import datetime

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

KRAFTON_LISTINFO_PAGE_URL = "https://krafton.com/careers/jobs/"
KRAFTON_RECRUIT_PAGE_URL = "https://krafton.com/careers/recruit-detail/?job={JOB_ID}"

KRAFTON_NAME = "KRAFTON"

logger = logging.getLogger(config.LOGGER_NAME)


class Krafton(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KRAFTON_LISTINFO_PAGE_URL
        self.recruit_page_url = KRAFTON_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_context(KRAFTON_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "영입종료시":
            return self.invalid_datetime()
        else:
            return datetime.strptime(date_data, "%Y년 %m월 %d일 까지")

    def extract_job_list(self):
        data = {
            "search_department": "Data,ITInfra,Tech",
            "var_page": 1,
            "search_list_cnt": 500
        }
        resp = self.external_req_post(self.listinfo_page_url, data=data)
        assert util.check_response(resp, "text/html")
        bs = BeautifulSoup(resp.text, 'html.parser')
        divs = bs.find_all("div", {"class": "RecruitItem"})
        for div in divs:
            a_tag = div.find("a", {"class": "RecruitItemTitle-link"})
            category_span = div.find("span", {"class": "RecruitItemMetaCategory-text"})
            path = a_tag["href"]
            number = re.search(r"[^a-bA-Z]job=(\d+)($|[^a-bA-Z\d])", path).group(1)
            full_url_path = self.recruit_page_url.format(JOB_ID=number)
            title = a_tag.find("span", {"class": "TextHoverLine"}).get_text()
            category = category_span.get_text()
            hinted_title = self.to_position_hint_suffixed_title(title, category)
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}
            self.page_queue.put(page_info)

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

                target_xpath = "//article[@id='post-recruit']"
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

                target_xpath = "//iframe[@id='JOB_BOARD_CONTENT']"
                driver.switch_to.frame(driver.find_element_by_xpath(target_xpath))
                target_xpath = "//div[@id='app_body']/div[@id='content']"
                try:
                    div = driver.find_element_by_xpath(target_xpath)
                except NoSuchElementException:
                    target_xpath = "//div[@id='wrapper']/div[@id='main']"
                    try:
                        div = driver.find_element_by_xpath(target_xpath)
                    except NoSuchElementException:
                        logger.warning(
                            f"[{self.__class__.__name__}] WebDriverWait() NoSuchElementException: failed to find xpath {target_xpath}\n title:{title}\nfull_url_path:{full_url_path}")
                        continue

                department = self.company_name
                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
