import logging
import queue
import re

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

SHOPIFY_LISTINFO_PAGE_URL = "https://www.shopify.com/careers/search?teams[]=data&teams[]=engineering&teams[]=security&keywords=&sort=team_asc"
SHOPIFY_BASE_URL = "https://www.shopify.com"

SHOPIFY_CODE_NAME = "SHOPIFY"

logger = logging.getLogger(config.LOGGER_NAME)


class Shopify(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = SHOPIFY_LISTINFO_PAGE_URL
        self.recruit_page_url = SHOPIFY_BASE_URL

    def init_context_entry(self):
        super().init_context(SHOPIFY_CODE_NAME)

    def extract_job_list(self):
        resp = self.external_req_get(self.listinfo_page_url)
        assert util.check_response(resp, "text/html", 200)
        allowed_teams = ["Data Science & Engineering", "Engineering & Development", "Trust and Security"]
        bs = BeautifulSoup(resp.text, 'html.parser')

        trs = bs.find("tbody", {"class": "jobs-table__body"}).findChildren("tr")

        def refine_text(text):
            pattern = "^\\s*([^\\s].*[^\\s])\\s*$"
            result = re.search(pattern, text).group(1)
            return result

        for tr in trs:
            tds = tr.find_all("td")
            path = tds[0].find("a")["href"]
            full_url_path = util.get_valid_fullurl(path, self.recruit_page_url)
            title = tds[0].get_text()
            title = refine_text(title)
            team = tds[1].get_text()
            team = refine_text(team)
            if team not in allowed_teams:
                logger.warning(f"[{self.__class__.__name__}] team: {team}  not in allowed_teams: {allowed_teams}")
                continue
            hinted_title = self.to_position_hint_suffixed_title(title, team)
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            if self.is_processed_hash(desc_hash):
                continue
            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}
            self.page_queue.put(page_info)

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

                department = SHOPIFY_CODE_NAME
                start_date = self.invalid_datetime()
                end_date = self.invalid_datetime()

                target_xpath = "//main[@id='Main']/section[2]/div/div/div[2]/div[1]"
                driver.get(full_url_path)
                timeout = 2
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
