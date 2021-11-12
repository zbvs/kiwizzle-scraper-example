import json
import logging
import queue
from datetime import datetime

from bs4 import BeautifulSoup
from selenium import webdriver

import config
import util
from endpoint.classes.DescWrapper import DescWrapper
from endpoint.classes.ThreadedEndPoint import ThreadedEndPoint

NCSOFT_SETCOOKIE_URL = "https://careers.ncsoft.com/apply/list"
NCSOFT_LISTINFO_PAGE_URL = "https://careers.ncsoft.com/interface/apply/list"
NCSOFT_RECRUIT_PAGE_URL = "https://careers.ncsoft.com/template/html//apply/view"
NCSOFT_MAIN_URL = "https://careers.ncsoft.com/apply/list"

NCSOFT_NAME = "NCSOFT"

logger = logging.getLogger(config.LOGGER_NAME)


class NCSoft(ThreadedEndPoint):
    def __init__(self):
        super().__init__()
        self.setcookie_url = NCSOFT_SETCOOKIE_URL
        self.listinfo_page_url = NCSOFT_LISTINFO_PAGE_URL
        self.recruit_page_url = NCSOFT_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_context(NCSOFT_NAME)
        self.cookies = {}
        resp = self.external_req_get(self.setcookie_url)
        assert util.check_response(resp, 'text/html')
        key_values = resp.headers['Set-Cookie'].split(';')[0].split('=')
        self.cookies[key_values[0]] = key_values[1]

        self.csrf = {}
        bs = BeautifulSoup(resp.text, 'html.parser')

        metas_crsf_header = bs.find_all("meta", {'name': '_csrf_header'})
        assert len(metas_crsf_header) == 1
        self.csrf['header'] = metas_crsf_header[0]['content']

        metas_csrf = bs.find_all("meta", {'name': '_csrf'})
        assert len(metas_csrf) == 1
        self.csrf['value'] = metas_csrf[0]['content']

    def to_valid_datetime(self, date_data):
        return datetime.strptime(date_data, "%Y.%m.%d")

    def extract_job_list(self):
        # {INFO} all necessary paremeters { channelCds , keywords, search_text }
        data = {'order_type': "ORDER_ETC", 'order_direction': "desc", 'page': 1, 'pagesize': 1000, 'channelCds': "",
                'keywords': "", 'search_text': ""}
        data['job_group_cd'] = ""

        all_type_dict = {"T0137": "Directing", "T0138": "Game Programming", "T0139": "General Programming",
                         "T0140": "Data Science", "T0141": "Game Design", "T0142": "Art", "T0143": "Sound",
                         "T0144": "Experience Design",
                         "T0145": "Development Management", "T0146": "QA", "T0147": "AI R & D", "T0167": "Game UX",
                         "T0168": "Technical Game Design",
                         "T0173": "Character Brand Experience", "T0153": "Information Security",
                         "T0154": "System Administration"}

        use_dict = {"T0138": "Game Programming", "T0139": "General Programming",
                    "T0140": "Data Science", "T0146": "QA", "T0147": "AI R & D", "T0167": "Game UX",
                    "T0153": "Information Security", "T0154": "System Administration"}

        result_string = ",".join([key for key in use_dict])

        data['job_type_cd'] = result_string

        headers = {self.csrf['header']: self.csrf['value'], 'Accept': "application/json"}
        resp = self.external_req_post(self.listinfo_page_url, data=data, cookies=self.cookies, headers=headers)
        resp.encoding = 'utf-8'
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)
        node_array = json_data['result']['data']['record']

        logger.debug(f"[{self.__class__.__name__}] extract_job_descs_to_temp() len(node_array):" + str(len(node_array)))

        for node in node_array:
            full_url_path = NCSOFT_MAIN_URL
            title = node['jopenNm']
            hinted_title = self.to_position_hint_suffixed_title(title, use_dict[node['rcutJobTypeCd']])
            desc_hash = util.get_hash_of(self.company_id, full_url_path, title)
            is_new = self.check_hash_not_exist(desc_hash)

            page_info = {"url": full_url_path, "title": title, "hinted_title": hinted_title, "hash": desc_hash,
                         "is_new": is_new}

            page_info['start_date'] = node['startDt']
            page_info['end_date'] = node['endDt']
            page_info['job_id'] = node['jopenId']

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

                job_id = page_info["job_id"]

                headers = {self.csrf['header']: self.csrf['value'], 'Accept': "text/html"}
                data = {'jopenId': job_id}

                resp = self.external_req_post(self.recruit_page_url, data=data, cookies=self.cookies, headers=headers)
                assert util.check_response(resp, 'text/html')
                bs = BeautifulSoup(resp.text, 'html.parser')

                department = NCSOFT_NAME

                article = bs.find("article", {"class": "contents side-strip"})
                content = article.encode_contents().decode()
                text_content = self.get_text_content_from_html(content, driver)

                screenshot = self.get_screenshot_from_localfile(content, driver)
                if screenshot is None:
                    continue

                start_date = self.to_valid_datetime(page_info['start_date'])
                end_date = self.to_valid_datetime(page_info['end_date'])

                yield DescWrapper(full_url_path, title, hinted_title, company_id, is_new, department, content,
                                  text_content, screenshot, start_date, end_date, desc_hash)

        except queue.Empty:
            pass
        driver.quit()
