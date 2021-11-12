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
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

KAKAOENTERPRISE_LISTINFO_PAGE_URL = "https://careers.kakaoenterprise.com/go/Category_All/546844/{LIST_NUM}/?q=&sortColumn=referencedate&sortDirection=desc"
KAKAOENTERPRISE_RECRUIT_PAGE_URL = "https://careers.kakaoenterprise.com"

KAKAOENTERPRISE_NAME = "KAKAO_ENTERPRISE"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoEnterprise(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOENTERPRISE_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOENTERPRISE_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(KAKAOENTERPRISE_NAME)

    def to_valid_datetime(self, date_data):
        if date_data[-1] == ".":
            date_data = date_data[:-1]
        return datetime.strptime(date_data, "%Y.%m.%d")

    def get_max_page(self, resp):
        bs = BeautifulSoup(resp.text, 'html.parser')
        a_tag = bs.find("a", {"title": "마지막 페이지", "class": "paginationItemLast"})
        if a_tag == None:
            return 0

        max_page = re.search("(.*)Category_All/(\d+)/(\d+)/(.+)", a_tag['href']).groups()[2]
        max_page = int(max_page)
        assert max_page % 10 == 0
        return max_page + 10

    def extract_job_list(self):
        categories = ["테크", "인턴"]

        resp = self.external_req_get(self.listinfo_page_url.format(LIST_NUM=0))
        assert util.check_response(resp, 'text/html')
        max_page = self.get_max_page(resp)
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() max_page:" + str(max_page))
        for i in range(0, max_page, 10):
            if i != 0:
                resp = self.external_req_get(self.listinfo_page_url.format(LIST_NUM=i))
                assert util.check_response(resp, 'text/html')
            bs = BeautifulSoup(resp.text, 'html.parser')
            divs = bs.find_all("div", {"class": "jobdetail-phone visible-phone"})
            assert len(divs) > 0
            for div in divs:
                category = div.findChildren("span", {"class": "jobFacility visible-phone"})[0].get_text()
                href = div.span.a['href']
                full_url_path = util.get_valid_fullurl(href, self.recruit_page_url)

                title = div.span.a.get_text()
                hinted_title = title
                if category in categories:
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
                desc_hash = page_info["hash"]
                hinted_title = page_info["hinted_title"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                target_xpath = "//span[@data-careersite-propertyid='customfield1']"
                driver.get(full_url_path)
                timeout = 3
                try:
                    element_present = EC.presence_of_element_located(
                        (By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue
                span = driver.find_element_by_xpath(target_xpath)
                text_date = re.sub(r"\s+", "", span.get_attribute('innerText'))

                company_id = self.company_id
                department = KAKAOENTERPRISE_NAME

                start_date = self.invalid_datetime()
                if self.is_valid_datedata(text_date):
                    end_date = self.to_valid_datetime(text_date)
                else:
                    end_date = self.invalid_datetime()

                target_xpath = "//span[@class='jobdescription']"
                span = driver.find_element_by_xpath(target_xpath)
                screenshot, span = self.get_screenshot(span, driver)
                if screenshot is None:
                    continue

                content = span.get_attribute("outerHTML")
                text_content = span.get_attribute("innerText")
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
