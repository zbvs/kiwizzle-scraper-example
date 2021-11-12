import logging
import queue
import time
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

APPLE_JOB_REQUEST = {
    "query": "",
    "filters": {
        "range": {
            "standardWeeklyHours": {
                "start": None,
                "end": None
            }
        },
        "teams": [
            {
                "teams.teamID": "teamsAndSubTeams-HRDWR",
                "teams.subTeamID": "subTeam-MCHLN"
            },
            {
                "teams.teamID": "teamsAndSubTeams-MLAI",
                "teams.subTeamID": "subTeam-MLI"
            },
            {
                "teams.teamID": "teamsAndSubTeams-MLAI",
                "teams.subTeamID": "subTeam-DLRL"
            },
            {
                "teams.teamID": "teamsAndSubTeams-MLAI",
                "teams.subTeamID": "subTeam-NLP"
            },
            {
                "teams.teamID": "teamsAndSubTeams-MLAI",
                "teams.subTeamID": "subTeam-CV"
            },
            {
                "teams.teamID": "teamsAndSubTeams-MLAI",
                "teams.subTeamID": "subTeam-AR"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-AF"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-CLD"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-COS"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-DSR"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-EPM"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-ISTECH"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-MCHLN"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-SEC"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-SQAT"
            },
            {
                "teams.teamID": "teamsAndSubTeams-SFTWR",
                "teams.subTeamID": "subTeam-WSFT"
            },
            {
                "teams.teamID": "teamsAndSubTeams-CORSV",
                "teams.subTeamID": "subTeam-IT"
            },
            {
                "teams.teamID": "teamsAndSubTeams-CORSV",
                "teams.subTeamID": "subTeam-GLSEC"
            },
            {
                "teams.teamID": "teamsAndSubTeams-CORSV",
                "teams.subTeamID": "subTeam-INFOSEC"
            }
        ]
    },
    "page": 1,
    "locale": "en-us",
    "sort": "relevance"
}

APPLE_CSRFTOKEN_URL = "https://jobs.apple.com/api/csrfToken"
APPLE_LISTINFO_JSON_URL = "https://jobs.apple.com/api/role/search"
APPLE_RECRUIT_PAGE_URL = "https://jobs.apple.com/en-us/details/{JOB_ID}/{JOB_TITLE}"

APPLE_NAME = "APPLE"
APPLE_PAGE_SIZE = 20

logger = logging.getLogger(config.LOGGER_NAME)


class Apple(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.csrf_page_url = APPLE_CSRFTOKEN_URL
        self.listinfo_json_url = APPLE_LISTINFO_JSON_URL
        self.recruit_page_url = APPLE_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_context(APPLE_NAME)
        resp = self.external_req_get(self.csrf_page_url)
        assert util.check_response(resp, content_types=None, status_codes=200)
        self.csrf_token = resp.headers["X-Apple-CSRF-Token"]

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y-%m-%dT%H:%M:%S.%fZ")

    def get_max_page(self, page_size, total_size):
        return (total_size // page_size) + (1 if total_size % page_size != 0 else 0)

    def extract_job_list(self):
        req_format = APPLE_JOB_REQUEST
        resp = self.external_req_post(self.listinfo_json_url, json=req_format)
        assert util.check_response(resp, "application/json", 200)
        total_size = resp.json()["totalRecords"]
        max_page = self.get_max_page(APPLE_PAGE_SIZE, total_size)

        for i in range(0, max_page):
            page = i + 1
            req_format["page"] = page
            resp = self.external_req_post(self.listinfo_json_url, json=req_format)
            assert util.check_response(resp, "application/json", 200)

            for job in resp.json()["searchResults"]:
                job_id = job["positionId"]
                url_title = job["transformedPostingTitle"]
                full_url_path = self.recruit_page_url.format(JOB_ID=job_id, JOB_TITLE=url_title)
                title = job["postingTitle"]
                hinted_title = self.to_position_hint_suffixed_title(title, job["team"]["teamName"])

                desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
                is_new = self.check_hash_not_exist(desc_hash)

                if self.is_processed_hash(desc_hash):
                    continue

                page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                             "is_new": is_new}

                if self.is_valid_datedata(job['postDateInGMT']):
                    page_info["start_date"] = self.to_valid_datetime(job['postDateInGMT'])
                else:
                    page_info["start_date"] = self.invalid_datetime()
                self.page_queue.put(page_info)
            time.sleep(0.5)

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

                department = APPLE_NAME

                start_date = page_info["start_date"]
                end_date = self.invalid_datetime()
                # Currently some apple job page ( 2~4 pages ) returns 403 forbidden.
                target_xpath = "//main//div[@class='job-details']/div[@itemprop='description']"
                driver.get(full_url_path)

                timeout = 2
                try:
                    element_present = EC.presence_of_element_located((By.XPATH, target_xpath))
                    WebDriverWait(driver, timeout).until(element_present)
                except TimeoutException:
                    logger.warning(
                        f"[{self.__class__.__name__}] WebDriverWait() timeout: failed to load page : {title}\n{full_url_path}")
                    continue

                div = self.get_element_by_xpath(target_xpath, driver)
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
