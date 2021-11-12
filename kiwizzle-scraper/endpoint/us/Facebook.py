import base64
import logging
import os
import queue
import re

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

FACEBOOK_LISTINFO_JSON_URL = "https://www.facebookcareers.com/careers/jobs?results_per_page=100&{SUBTEAM_ARRAY}&page={PAGE_NUM}"
FACEBOOK_RECRUIT_PAGE_URL = "https://www.facebookcareers.com"
FACEBOOK_CODE_NAME = "FACEBOOK"

logger = logging.getLogger(config.LOGGER_NAME)


class Facebook(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_json_url = FACEBOOK_LISTINFO_JSON_URL
        self.recruit_page_url = FACEBOOK_RECRUIT_PAGE_URL

    def init_context_entry(self):
        if not self.check_is_company_exist(FACEBOOK_CODE_NAME):
            category_ids = list(
                map(lambda x: x["categoryId"], self.get_category_id_from_api_server(["PORTAL_MESSENGER"])))
            country_id = self.get_country_id_from_api_server("US")
            pattern = {
                "rolePattern": " Responsibilities\n",
                "requirePattern": "Minimum Qualifications\n",
                "preferredPattern": "Preferred Qualifications\n",
                "endPattern": "Locations\n"
            }

            path = os.getcwd()
            with open(path + "/img/" + self.__class__.__name__ + ".png", "rb") as f:
                logo = base64.b64encode(f.read()).decode("ascii")
            request = {"companyCode": FACEBOOK_CODE_NAME, "publicNameEng": "Facebook", "publicNameKor": "페이스북",
                       "pattern": pattern, "logo": logo,
                       "detail": {"parent": None, "isGroup": False, "category": category_ids, "country": country_id}}
            self.create_company_from_api_server(request)
        super().init_context(FACEBOOK_CODE_NAME)

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        page_size = 100
        subteam_list = ["Technical Security", "Production Engineering", "Partner Engineering", "Network Engineering",
                        "Machine Learning", "Engineering", "Data Science", "Data Engineering", "Computer Vision",
                        "Artificial Intelligence"]
        subteam_array = []
        for i in range(0, len(subteam_list)):
            subteam_array.append(f"sub_teams[{i}]={subteam_list[i]}")
        subteam_array = "&".join(subteam_array)
        timeout = 6
        page_num = 1
        retry = 0
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.get(self.listinfo_json_url.format(SUBTEAM_ARRAY=subteam_array, PAGE_NUM=page_num))
        target_xpath = "//div[@id='search_result']"
        try:
            element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            logger.warning(
                f"[{self.__class__.__name__}] Facebook get max_page failed")
            return
        search_result_div = driver.find_element_by_xpath(target_xpath)
        page_div = search_result_div.find_element_by_xpath("./div[4]/div[1]/div")
        pages_text = page_div.get_attribute("innerText")
        pattern = re.compile(r"\d+ (?:of|/) (\d+)")
        result = re.findall(pattern, pages_text)
        assert len(result) == 1
        max_page = int(result[0])
        max_page = self.get_max_page(page_size, max_page)

        for page_num in range(1, max_page + 1):
            driver.get(self.listinfo_json_url.format(SUBTEAM_ARRAY=subteam_array, PAGE_NUM=page_num))
            target_xpath = "//div[@id='search_result']"

            try:
                element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                WebDriverWait(driver, timeout).until(element_present)
            except TimeoutException:
                logger.warning(
                    f"[{self.__class__.__name__}] Facebook list page load page_num:{page_num}, retry:{retry}")
                continue
            retry = 0
            search_result_div = driver.find_element_by_xpath(target_xpath)
            target_xpath = "./div[3]/a"
            a_tags = search_result_div.find_elements_by_xpath(target_xpath)
            for a_tag in a_tags:
                full_url_path = util.get_valid_fullurl(a_tag.get_attribute("href"), self.recruit_page_url)
                job_div = a_tag.find_element_by_xpath("./div/div/div")
                title_div = job_div.find_element_by_xpath("./div")
                title = title_div.get_attribute("innerText")
                hint_div = job_div.find_element_by_xpath("./div[3]/div[2]/div[3]/div[2]/div/div")
                hint = hint_div.get_attribute("innerText")
                try:
                    extra_hint_div = hint_div.find_element_by_xpath("./div")
                    if extra_hint_div is not None:
                        inner_text = extra_hint_div.get_attribute("innerText")
                        hint = hint.replace(inner_text, "")
                        extra_hint = extra_hint_div.get_attribute("data-tooltip-content")
                        hint += ", " + ", ".join(extra_hint.split("\n"))
                except NoSuchElementException:
                    pass

                hinted_title = self.to_position_hint_suffixed_title(title, hint)
                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)
                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}
                self.page_queue.put(page_info)
        driver.quit()

    def extract_from_endpoint(self):
        driver = webdriver.Chrome(executable_path='chrome/chromedriver', options=self.chrome_options)
        driver.set_window_size(self.screenshot_width, self.screenshot_height)
        try:
            while True:
                page_info = self.page_queue.get(timeout=0)
                self.page_queue.task_done()
                remained_size = self.page_queue.unfinished_tasks
                if remained_size % 100 == 0:
                    logger.info("remained_size:" + str(remained_size))
                full_url_path = page_info["url"]
                title = page_info["title"]
                hinted_title = page_info["hinted_title"]
                desc_hash = page_info["hash"]
                is_new = page_info["is_new"]
                company_id = self.company_id

                if not is_new and not config.UPDATE_MODE:
                    yield self.get_redundant_desc_tuple(full_url_path, title, company_id, is_new, desc_hash)
                    continue

                department = FACEBOOK_CODE_NAME
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                target_xpath = "//div[@id='careersContentContainer']/div/div[3]/div[2]/div/div/div[1]/div[1]"
                driver.get(full_url_path)

                timeout = 6
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = self.get_element_by_xpath(target_xpath, driver, title=title)
                if div is None:
                    continue

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
