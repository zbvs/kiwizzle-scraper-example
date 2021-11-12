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
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

BAEMIN_LISTINFO_JSON_URL = "https://career.woowahan.com/w1/recruits?category=jobGroupCodes%3ABA005001&recruitCampaignSeq={GROUP_SEQ}&jobGroupCodes=BA005001&page=0&size={SIZE}"
BAEMIN_RECRUIT_PAGE_URL = "https://career.woowahan.com/recruitment/{JOB_ID}/detail"

WOOWABROS_NAME = "WOOWA_BROS"

logger = logging.getLogger(config.LOGGER_NAME)


class WoowaBros(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = BAEMIN_LISTINFO_JSON_URL
        self.recruit_page_url = BAEMIN_RECRUIT_PAGE_URL
        self.chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    def init_context_entry(self):
        super().init_context(WOOWABROS_NAME)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%d %H:%M:%S")

    def extract_job_list(self):
        group_seq = [0, 1]
        for seq in group_seq:
            resp = self.external_req_get(self.listinfo_json_url.format(GROUP_SEQ=seq, SIZE=200))
            assert util.check_response(resp, "application/json")

            json_data = json.loads(resp.text)
            jobs = json_data['data']['list']

            totalCount = json_data['data']['totalSize']
            logger.debug(f"[{self.__class__.__name__}] extract_job_list() totalCount:" + str(totalCount))

            assert len(jobs) == totalCount

            for job_info in jobs:
                job_id = job_info['recruitNumber']
                title = job_info['recruitName']
                hinted_title = title
                full_url_path = self.recruit_page_url.format(JOB_ID=job_id)
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                start_date = job_info['recruitOpenDate']
                end_date = job_info['recruitCloseDate']

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["start_date"] = start_date
                page_info["end_date"] = end_date

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
                driver.set_script_timeout(4)
                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                target_xpath = "//div[@class='detail-view editor-viewer']"

                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located(
                        (By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                department = WOOWABROS_NAME
                div = driver.find_element_by_xpath(target_xpath)
                screenshot, div = self.get_screenshot(div, driver)
                if screenshot is None:
                    continue

                content = div.get_attribute("innerHTML")
                text_content = div.get_attribute("innerText")
                start_date = self.to_valid_datetime(page_info['start_date']) if self.is_valid_datedata(
                    page_info['start_date']) else self.invalid_datetime()
                end_date = self.to_valid_datetime(page_info['end_date']) if self.is_valid_datedata(
                    page_info['end_date']) else self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)
        except queue.Empty:
            pass
        driver.quit()
