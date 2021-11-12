import logging
import queue
from datetime import datetime

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

NHN_LISTINFO_PAGE_URL = "https://recruit.nhn.com/ent/recruitings?type=class"
NHN_RECRUIT_PAGE_URL = "https://recruit.nhn.com"

NHN_NAME = "NHN"

logger = logging.getLogger(config.LOGGER_NAME)


class NHN(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = NHN_LISTINFO_PAGE_URL
        self.recruit_page_url = NHN_RECRUIT_PAGE_URL
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.chrome_options = options

    def init_context_entry(self):
        super().init_context(NHN_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "채용시까지":
            return self.invalid_datetime()
        return datetime.strptime(date_data, "%Y.%m.%d")

    def extract_job_list(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_page_url)

        tables = driver.find_elements_by_xpath("//table[@class='tbl_lst' and ./caption/span]")
        target_job_groups = ["게임제작 모집분야", "기술 모집분야", "인프라운영업무 모집분야"]
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() len(tables):" + str(len(tables)))
        for table in tables:
            job_group = table.find_elements_by_xpath("./thead/tr/th")[0].text
            if job_group not in target_job_groups:
                continue
            trs = table.find_elements_by_xpath("./tbody/tr")
            for tr in trs:
                tds = tr.find_elements_by_xpath("./td")
                a_tag = tds[0].find_element_by_xpath(".//a")
                experience = tds[1].text
                term = tds[3].text
                path = a_tag.get_attribute("href")
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                title = a_tag.text

                if experience == "경력":
                    hinted_title = self.to_experience_hint_suffixed_title(title, "경력")
                else:
                    hinted_title = title

                terms = term.split(" ~ ")
                if self.is_valid_datedata(terms[0]):
                    start_date = self.to_valid_datetime(terms[0])
                else:
                    start_date = self.invalid_datetime()

                if self.is_valid_datedata(terms[1]):
                    end_date = self.to_valid_datetime(terms[1])
                else:
                    end_date = self.invalid_datetime()

                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["start_date"] = start_date
                page_info["end_date"] = end_date
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

                driver.get(full_url_path)
                target_xpath = "//div[@class='detail_info']"
                timeout = 1
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

                department = NHN_NAME
                content = div.get_attribute('innerHTML')
                text_content = div.get_attribute('innerText')
                start_date = page_info["start_date"]
                end_date = page_info["end_date"]

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
