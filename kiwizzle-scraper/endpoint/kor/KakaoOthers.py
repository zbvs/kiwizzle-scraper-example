import logging
import queue
import re
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

KAKAOOTERS_NUMINFO_PAGE_URL = "https://careers.kakao.com/jobs?company=SUBSIDIARY&page=1&part=TECHNOLOGY"
KAKAOOTERS_LISTINFO_PAGE_URL = "https://careers.kakao.com/jobs?company=SUBSIDIARY&page={PAGE_NUM}&part=TECHNOLOGY"
KAKAOOTERS_RECRUIT_PAGE_URL = "https://careers.kakao.com/{PATH}"

KAKAOOTERS_NAME = "KAKAO_OTHERS"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoOthers(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.numinfo_page_url = KAKAOOTERS_NUMINFO_PAGE_URL
        self.listinfo_page_url = KAKAOOTERS_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOOTERS_RECRUIT_PAGE_URL
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.chrome_options = options

    def init_context_entry(self):
        super().init_context(KAKAOOTERS_NAME)

    def to_valid_datetime(self, date_data):
        if date_data == "영입종료시":
            return self.invalid_datetime()
        else:
            return datetime.strptime(date_data, "%Y년 %m월 %d일 까지")

    def extract_job_list(self):
        registered_list = ["카카오", "카카오뱅크", "카카오엔터테인먼트", "카카오모빌리티", "카카오페이", "카카오게임즈", "카카오커머스", "카카오엔터프라이즈", "카카오브레인"]
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.numinfo_page_url)
        a_tags = driver.find_elements_by_xpath("//a[@class='change_page btn_lst']")
        if len(a_tags) == 0:
            max_page = 1
        else:
            max_page = int(re.search('.*/jobs\?page=(\d+)', a_tags[0].get_attribute("href")).groups()[0])
        logger.debug(f"[{self.__class__.__name__}] extract_job_list() max_page:" + str(max_page))
        for page_num in range(1, max_page + 1):
            url = self.listinfo_page_url.format(PAGE_NUM=page_num)
            driver.get(url)
            lis = driver.find_elements_by_xpath("//ul[@class='list_jobs']//li")
            for li in lis:
                company_name = li.find_element_by_xpath("./div/dl[./dt[@class='screen_out']]").find_element_by_xpath(
                    "./dd").text
                if company_name in registered_list:
                    continue

                path = li.find_element_by_xpath(".//a[@class='link_jobs']").get_attribute("href")
                path = path.split('?')[0]
                full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
                title = li.find_element_by_xpath(".//h4[@class='tit_jobs']").text
                hinted_title = title
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                end_date = li.find_elements_by_xpath(".//dl[@class='list_info']/dd")[0].text
                # ex) 2019년 03월 06
                if self.is_valid_datedata(end_date):
                    end_date = self.to_valid_datetime(end_date)
                else:
                    end_date = self.invalid_datetime()
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["end_date"] = end_date
                page_info["department"] = company_name

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
                    element_present = EC.presence_of_element_located((By.XPATH, "//div[@class='area_cont']"))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue
                div = driver.find_element_by_xpath("//div[@class='area_cont']")
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                department = page_info["department"]
                content = div.get_attribute('innerHTML')
                text_content = div.get_attribute('innerText')
                start_date = self.invalid_datetime()
                end_date = page_info["end_date"]
                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
