import json
import logging
import queue
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.IntegratedEndPoint import IntegratedEndPoint

NAVER_BASE_URL = "https://recruit.navercorp.com/"
NAVER_LISTINFO_JSON_URL = "https://recruit.navercorp.com//naver/job/listJson?classNm=developer&startNum=1&endNum=300"
NAVER_RECRUIT_PAGE_URL = "https://recruit.navercorp.com/naver/job/detail/developer?annoId={PAGE_NUM}"

NAVER_NAMES = {"KR": "NAVER", "WTKR": "NAVER_WEBTOON", "NB": "NAVER_CLOUD", "SN": "SNOW", "WM": "NAVER_WORKS",
               "NFN": "NAVER_FINANCIAL", "NL": "NAVER_LABS"}
BLACKLIST_NAMES = ["NAVER_LABS"]
NAVER_DEFAULTNAME = "NAVER"

logger = logging.getLogger(config.LOGGER_NAME)


class Naver(IntegratedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = NAVER_LISTINFO_JSON_URL
        self.recruit_page_url = NAVER_RECRUIT_PAGE_URL
        self.screenshot_width = 1080

    def init_context_entry(self):
        super().init_integrated_context(NAVER_DEFAULTNAME, NAVER_NAMES)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y%m%d")

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_json_url)

        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)

        for recruit_info in json_data:
            page_num = recruit_info["annoId"]
            full_url_path = self.recruit_page_url.format(PAGE_NUM=page_num)
            title = recruit_info['jobNm']
            hinted_title = title
            name_key = recruit_info['sysCompanyCd']
            if name_key in NAVER_NAMES:
                department = NAVER_NAMES[name_key]
                naver_subcompany_id = self.company_ids[NAVER_NAMES[name_key]]
            else:
                logger.error(
                    f"[{self.__class__.__name__}] extract_job_descs_to_temp(): no name_key=\"{name_key}\" found for NAVER_NAMES[name_key]")
                department = NAVER_DEFAULTNAME
                naver_subcompany_id = self.company_ids[NAVER_DEFAULTNAME]

            if department in BLACKLIST_NAMES:
                continue
            start_date = self.to_valid_datetime(recruit_info['staYmd'])
            if recruit_info['endYmd'] is not None:
                end_date = self.to_valid_datetime(recruit_info['endYmd'])
            else:
                end_date = self.invalid_datetime()

            desc_hash = util.get_hash_of(naver_subcompany_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}

            page_info["company_id"] = naver_subcompany_id
            page_info["department"] = department
            page_info["start_date"] = start_date
            page_info["end_date"] = end_date
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
                company_id = page_info["company_id"]

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                target_xpath = "//div[@class='dtl_context']//div[@class='context_area']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                section = driver.find_element_by_xpath(target_xpath)
                screenshot, section = self.get_screenshot(section, driver)
                if screenshot is None:
                    continue

                content = section.get_attribute('outerHTML')
                text_content = section.get_attribute("innerText")

                department = page_info["department"]
                start_date = page_info["start_date"]
                end_date = page_info["end_date"]

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)
        except queue.Empty:
            pass
        driver.quit()
