import json
import logging
import queue
import ssl
from datetime import datetime

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from urllib3 import poolmanager

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

NETMARBLE_LISTINFO_JSON_URL = "https://company.netmarble.com/rem/api/select/index.jsp"
NETMARBLE_RECRUIT_JSON_URL = "https://company.netmarble.com/rem/api/select/"
NETMARBLE_RECRUIT_PAGE_URL = "https://company.netmarble.com/rem/www/notice.jsp?anno_id={ANNO_ID}&annotype=all"

NETMARBLE_NAME = "NETMARBLE"

logger = logging.getLogger(config.LOGGER_NAME)


class Netmarble(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = NETMARBLE_LISTINFO_JSON_URL
        self.recruit_json_url = NETMARBLE_RECRUIT_JSON_URL
        self.recruit_page_url = NETMARBLE_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(NETMARBLE_NAME)
        # issue ref:
        #   https://stackoverflow.com/questions/61631955/python-requests-ssl-error-during-requests
        #   https://github.com/psf/requests/issues/4775
        session = requests.session()
        session.mount('https://', self.TLSAdapter())
        self.session = session

    class TLSAdapter(requests.adapters.HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False):
            """Create and initialize the urllib3 PoolManager."""
            ctx = ssl.create_default_context()
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            self.poolmanager = poolmanager.PoolManager(
                num_pools=connections,
                maxsize=maxsize,
                block=block,
                ssl_version=ssl.PROTOCOL_TLS,
                ssl_context=ctx)

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%d %H:%M:%S.%f")

    def extract_job_list(self):
        req_data = {"requestName": "anno_select", "locale_cd": "KO", "company_cd": "01", "req_type_cd": "",
                    "rem_job_group_cd": "05", "hashtag": "", "sta_row": "1", "end_row": "1000", "title": ""}
        jobgroup_dict = {"AI": "05", "BIGDATA": "07", "GAME_PUBLISHING_TECH": "04", "GAME_DEVELOPMENT": "01"}

        for key_job_group in jobgroup_dict:
            rem_job_group_cd = jobgroup_dict[key_job_group]
            req_data["rem_job_group_cd"] = rem_job_group_cd
            resp = self.session.post(url=self.listinfo_json_url, json=req_data, timeout=config.DEFAULT_REQTIME)
            assert util.check_response(resp, "application/json")

            json_data = json.loads(resp.text)
            logger.debug(
                f"[{self.__class__.__name__}] extract_job_descs_to_temp() len(json_data['response']):" + str(
                    len(json_data['response'])))
            for list_info in json_data["response"]:
                anno_id = list_info["anno_id"]
                title = list_info["anno_subject"]
                hinted_title = self.to_position_hint_suffixed_title(title, key_job_group)
                full_url_path = self.recruit_page_url.format(ANNO_ID=anno_id)
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                json_url = self.recruit_json_url.format(ANNO_ID=anno_id)

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                page_info["json_url"] = json_url
                page_info["anno_id"] = anno_id

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

                anno_id = page_info["anno_id"]
                json_url = page_info["json_url"]

                data = {"requestName": "anno_detail", "anno_id": anno_id}
                resp = self.session.post(json_url, json=data, timeout=config.DEFAULT_REQTIME)
                assert util.check_response(resp, "application/json")
                job_desc = json.loads(resp.text)["response"][0]
                department = NETMARBLE_NAME

                target_xpath = "//div[@class='recruit_area']//div[@class='recruit_view_cont']"
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

                assert type(job_desc['accept_sta_ymd']) == str
                start_date = self.to_valid_datetime(job_desc['accept_sta_ymd'])
                if job_desc['accept_end_ymd'] is not None:
                    assert type(job_desc['accept_end_ymd']) == str
                    end_date = self.to_valid_datetime(job_desc['accept_end_ymd'])
                else:
                    end_date = self.invalid_datetime()

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
