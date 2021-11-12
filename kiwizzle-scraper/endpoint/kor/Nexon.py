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

NEXON_LISTINFO_PAGE_URL = "https://career.nexon.com/user/recruit/member/postList?joinCorp=NX"
NEXON_RECRUIT_PAGE_URL = "https://career.nexon.com"

NEXON_NAME = "NEXON"

logger = logging.getLogger(config.LOGGER_NAME)


class Nexon(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = NEXON_LISTINFO_PAGE_URL
        self.recruit_page_url = NEXON_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(NEXON_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%y.%m.%d")

    def get_max_page(self, resp):
        bs = BeautifulSoup(resp.text, 'html.parser')
        field_set = bs.find("fieldset", {"class": "paging"})
        if field_set is None:
            return 0
        a_tag = field_set.find("a", {"class": "last"})
        if a_tag is None:
            a_tags = field_set.find_all("a")
            a_tags = list(filter(
                lambda x: len(x["class"]) == 1 and x["class"][0] == "page" and re.match("\\s*^(\\d+)\\s*$",
                                                                                        x.get_text()), a_tags))
            page_string = int(re.search("(\\d+)", a_tags[-1].get_text()).group(1))
        else:
            page_string = int(re.search("(\\d+)", a_tag.get_text()).group(1))
        return int(page_string) - 1

    def extract_job_list(self):
        job_groups = {5: "게임프로그래밍", 11: "게임사운드", 12: "웹기획", 21: "분석가(Analyst)", 22: "엔지니어", 23: "정보보안"}

        def extract_one_job_group(key_job_group):
            data_dict = {"joinCorp": "NX", "currentPage": 0, "ddlJobGroupCd": key_job_group}
            resp = self.external_req_post(self.listinfo_page_url, data=data_dict)
            assert util.check_response(resp, 'text/html')
            max_page = self.get_max_page(resp)
            logger.debug(f"[{self.__class__.__name__}] extract_job_descs_to_temp() max_page:" + str(max_page))

            for page_num in range(0, max_page):
                data_dict["currentPage"] = page_num
                resp = self.external_req_post(self.listinfo_page_url, data=data_dict)
                assert util.check_response(resp, 'text/html')
                bs = BeautifulSoup(resp.text, 'html.parser')
                lis = bs.find("div", {"class": "wrapPostGroup"}).find("ul").find_all("li")
                assert len(lis) != 0
                for li in lis:
                    title = li.find("dt").get_text()
                    hinted_title = self.to_position_hint_suffixed_title(title, job_groups[key_job_group])
                    href_path = re.search("(.*reNo=\\d+)", li.find("a")["href"]).group(1)
                    full_url_path = util.get_valid_fullurl(href_path, self.recruit_page_url)
                    desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                    is_new = self.check_hash_not_exist(desc_hash)
                    exp = li.find("span", {"class": lambda x: not x}).get_text()
                    job_group = li.find("span", {"class": "tinted"}).get_text()
                    page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                                 "is_new": is_new}
                    page_info["exp"] = exp
                    page_info["job_group"] = job_group
                    self.page_queue.put(page_info)

        for key in job_groups:
            extract_one_job_group(key)

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

                department = NEXON_NAME

                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                target_xpath = "//div[@class='detailContents']"
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

                content = div.get_attribute('outerHTML')
                text_content = div.get_attribute("innerText")

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
