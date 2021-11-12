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

logger = logging.getLogger(config.LOGGER_NAME)


class MidasEndpoint(ThreadedEndPoint):
    def init_midas_context(self, company_name, jobclass_list):
        super().init_context(company_name)
        self.jobclass_list = jobclass_list

    def to_valid_datetime(self, date_data):
        year = date_data['year'] + (1900)
        month = date_data['month'] + 1
        date = date_data['date']
        hour = date_data['hours']
        minute = date_data['minutes']
        second = date_data['seconds']

        return datetime(year, month, date, hour, minute, second)

    def extract_job_list(self):
        data = {'recruitClassName': "", 'jobnoticeStateCode': 10, 'pageSize': 1000, 'currentPage': 1}

        def iter_node_array(node_array):
            for node in node_array:
                if node['receiptState'] == "접수중":
                    full_url_path = self.recruit_page_url.format(KIND_CODE=node['systemKindCode'],
                                                                 PAGE_NUM=node['jobnoticeSn'])
                    title = node['jobnoticeName']
                    hinted_title = title
                    desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                    is_new = self.check_hash_not_exist(desc_hash)

                    page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                                 "is_new": is_new}

                    page_info['start_date'] = node['applyStartDate']
                    page_info['end_date'] = node['applyEndDate']
                    self.page_queue.put(page_info)

        if len(self.jobclass_list) == 0:
            resp = self.external_req_post(self.listinfo_page_url, data=data)

            assert util.check_response(resp, 'text/plain')
            json_data = json.loads(resp.text)
            node_array = json_data["list"]

            logger.debug(f"[{self.__class__.__name__}] extract_job_list() resp.text:" + resp.text)

            iter_node_array(node_array)
        else:
            for jobclass in self.jobclass_list:
                data['recruitClassName'] = jobclass
                resp = self.external_req_post(self.listinfo_page_url, data=data)

                assert util.check_response(resp, 'text/plain')
                json_data = json.loads(resp.text)
                node_array = json_data["list"]

                logger.debug(f"[{self.__class__.__name__}] extract_job_list() resp.text:" + resp.text)

                iter_node_array(node_array)

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

                target_xpath = "//iframe[@id='viewSmartEditor']"
                driver.get(full_url_path)
                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                driver.switch_to.frame(driver.find_element_by_xpath(target_xpath))
                body = driver.find_element_by_xpath('.//body')
                screenshot, body = self.get_screenshot(body, driver)
                if screenshot is None:
                    continue

                department = self.company_name
                content = body.get_attribute('outerHTML')
                text_content = body.get_attribute("innerText")

                start_date = self.to_valid_datetime(page_info['start_date'])
                end_date = self.to_valid_datetime(page_info['end_date'])

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
