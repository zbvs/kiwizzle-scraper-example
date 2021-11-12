import json
import logging
import queue
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

COUPANG_LISTINFO_PAGE_URL = "https://rocketyourcareer.kr.coupang.com/search-jobs/results?ActiveFacetID=Technology&CurrentPage=1&RecordsPerPage={PAGE_NUM}&Distance=50&RadiusUnitType=0&Keywords=&Location=%EB%8C%80%ED%95%9C%EB%AF%BC%EA%B5%AD&ShowRadius=False&IsPagination=False&CustomFacetName=&FacetTerm=&FacetType=0&FacetFilters%5B0%5D.ID=Technology&FacetFilters%5B0%5D.FacetType=5&FacetFilters%5B0%5D.Count=132&FacetFilters%5B0%5D.Display=Technology&FacetFilters%5B0%5D.IsApplied=true&FacetFilters%5B0%5D.FieldName=job_level&FacetFilters%5B1%5D.ID=1835841&FacetFilters%5B1%5D.FacetType=2&FacetFilters%5B1%5D.Count=444&FacetFilters%5B1%5D.Display=%EB%8C%80%ED%95%9C%EB%AF%BC%EA%B5%AD&FacetFilters%5B1%5D.IsApplied=true&FacetFilters%5B1%5D.FieldName=&SearchResultsModuleName=Search+Results&SearchFiltersModuleName=Search+Filters"
COUPANG_RECRUIT_PAGE_URL = "https://rocketyourcareer.kr.coupang.com"

COUPANG_NAME = "COUPANG"

logger = logging.getLogger(config.LOGGER_NAME)


class Coupang(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = COUPANG_LISTINFO_PAGE_URL.format(PAGE_NUM=2000)
        self.recruit_page_url = COUPANG_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(COUPANG_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%d")

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_page_url)
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)
        html_list_content = json_data["results"]

        bs = BeautifulSoup(html_list_content, 'html.parser')
        lis = bs.find_all("li", {"class": "searched-job-item"})

        logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(lis):" + str(len(lis)))
        for li in lis:
            arr = li.findChildren("a", {"data-job-id": True})
            assert len(arr) == 1
            path = arr[0]["href"]

            arr = li.findChildren("h3", {"class": 'searched-job-title'})
            assert len(arr) == 1
            title = arr[0].getText()
            hinted_title = title
            full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
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

                target_xpath = "//section[contains(@class, 'job-description') and @data-selector-name='jobdetails']/div[contains(@class, 'ats-description')]"
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

                department = COUPANG_NAME
                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
