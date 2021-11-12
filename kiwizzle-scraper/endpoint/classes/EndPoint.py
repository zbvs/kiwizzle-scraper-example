import base64
import hashlib
import json
import logging
import os
import queue
import re
import time
import traceback
import uuid
from urllib.parse import urlparse

import markdown
import requests
from bs4 import BeautifulSoup
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options

import config
import util
from endpoint.classes.DescWrapper import DescWrapper

logger = logging.getLogger(config.LOGGER_NAME)


class EndPoint:
    def __init__(self):
        self.page_queue = queue.Queue()
        self.type = "html"
        self.company_name = None
        self.company_id = None
        self.access_token = None
        self.hash_set = set()
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36")
        self.chrome_options = options
        self.screenshot_width = 1920
        self.screenshot_height = 1080
        self.access_token = self.get_access_token_from_api_server()

    def init_context_entry(self):
        logger.error(f"[{self.__class__.__name__}] not implemented {self.init_context_entry.__name__}")
        raise NotImplementedError(f"[{self.__class__.__name__}] not implemented {self.init_context_entry.__name__}")

    def init_context(self, company_name):
        self.company_name = company_name
        self.company_id = self.get_company_id_from_api_server(company_name)

    def set_external_request_argument(self, *args, **kwargs):
        rule = f"^{config.API_BASE_URL}.*"
        if "url" in kwargs:
            url = kwargs["url"]
        else:
            url = args[0]

        if re.match(rule, url):
            raise Exception(
                f"[{self.__class__.__name__}] invalid url has been passed to {self.set_external_request_argument.__name__}")

        kwargs.setdefault("timeout", config.DEFAULT_REQTIME)
        return kwargs

    # Reqeust methods
    def set_api_request_argument(self, *args, **kwargs):
        rule = f"^{config.API_BASE_URL}.*"
        if "url" in kwargs:
            url = kwargs["url"]
        else:
            url = args[0]
        if not re.match(rule, url):
            raise Exception(
                f"[{self.__class__.__name__}] invalid url has been passed to {self.set_api_request_argument.__name__}")

        kwargs.setdefault("timeout", config.DEFAULT_REQTIME)
        if self.access_token is not None:
            if "cookies" in kwargs:
                cookies = kwargs["cookies"]
                cookies[config.ACCESS_TOKEN_COOKIE_NAME] = self.access_token
            else:
                cookies = {config.ACCESS_TOKEN_COOKIE_NAME: self.access_token}
            kwargs["cookies"] = cookies
        return kwargs

    def external_req_get(self, *args, **kwargs):
        kwargs = self.set_external_request_argument(*args, **kwargs)
        return requests.get(*args, **kwargs)

    def external_req_post(self, *args, **kwargs):
        kwargs = self.set_external_request_argument(*args, **kwargs)
        return requests.post(*args, **kwargs)

    def api_req_get(self, *args, **kwargs):
        kwargs = self.set_api_request_argument(*args, **kwargs)
        return requests.get(*args, **kwargs)

    def api_req_post(self, *args, **kwargs):
        kwargs = self.set_api_request_argument(*args, **kwargs)
        return requests.post(*args, **kwargs)

    def api_req_put(self, *args, **kwargs):
        kwargs = self.set_api_request_argument(*args, **kwargs)
        return requests.put(*args, **kwargs)

    # Util methods
    def is_valid_datedata(self, date_data):
        if type(date_data) != str:
            return False
        try:
            self.to_valid_datetime(date_data)
        except (ValueError, TypeError) as e:
            logger.warning(f"{self.is_valid_datedata.__name__}() falied to validate date format {date_data}")
            return False
        return True

    # noinspection PyMethodMayBeStatic
    def invalid_datetime(self):
        return None

    # some site's json datas can have duplicated job for different list page. (ex:Microsoft)
    # Handle it with set
    def is_processed_hash(self, hash):
        if hash in self.hash_set:
            return True
        self.hash_set.add(hash)
        return False

    # noinspection PyMethodMayBeStatic
    def to_position_hint_suffixed_title(self, title, hint):
        if len(hint) > 0:
            return title + ":::" + hint
        return title

    def to_experience_hint_suffixed_title(self, title, hint):
        if len(hint) > 0:
            return title + ":::" + hint
        return title

    # noinspection PyMethodMayBeStatic
    def refine_links_in_tags(self, html_content, BASE_URL):
        def refine_tags(tags, attribute):
            for tag in tags:
                if re.match("^/.*", tag[attribute]):
                    tag[attribute] = tag[attribute][1:]
                tag[attribute] = BASE_URL + tag[attribute]

        bs = BeautifulSoup(html_content, 'html.parser')
        rule = "^(http://|https://|data:).*"
        results = bs.findAll(["img", "video"], {"src": lambda src: src and not re.match(rule, src)})
        refine_tags(results, "src")
        results = bs.findAll("a", {"href": lambda src: src and not re.match(rule, src)})
        refine_tags(results, "href")
        return bs.decode_contents()

    def get_representative_img_tag_content(self, html_content, origin_url):
        origin_domain = urlparse(origin_url).netloc
        bs = BeautifulSoup(html_content, 'html.parser')

        img_tags = bs.findAll("img", {"src": lambda src: src and re.match("^http.*", src)})
        if len(img_tags) == 0:
            return None

        big = 0
        result_img_tag = None
        resp = None
        for img_tag in img_tags:
            resp = self.external_req_get(img_tag["src"], timeout=config.IMG_GET_REQTIME)

            # response can be redirected request.
            # Redirected request's domain can be be difference from origin_domain.
            # If this is the case, then chances are high that response content-type is just text/html, not image type.
            redirected = len(list(filter(lambda r: 300 <= r.status_code and r.status_code <= 302,  resp.history))) >= 1

            # Sometimes images can be from CDN. in that cases, images are not managed well so we do not apply assertion for them.
            is_domain_differ = urlparse(resp.request.url).netloc != origin_domain

            is_legel_response = util.check_response(resp, config.IMAGE_CONTENT_TYPES, 200)

            assert is_legel_response or redirected or is_domain_differ
            if len(resp.content) > big and is_legel_response:
                result_img_tag = img_tag
                big = len(resp.content)

        assert result_img_tag is not None
        return resp.content

    def to_valid_datetime(self, date_data):
        logger.error(f"[{self.__class__.__name__}] not implemented {self.to_valid_datetime.__name__}")
        raise NotImplementedError(f"[{self.__class__.__name__}] not implemented {self.to_valid_datetime.__name__}")

    # noinspection PyMethodMayBeStatic
    def refine_text_content(self, text):
        text = text.replace(u"\xa0+", " ")
        text = re.sub(r"\n+", r"\n", text)
        return re.sub(r"\\s+", " ", text)

    # noinspection PyMethodMayBeStatic
    def get_redundant_desc_tuple(self, full_url_path, title, company_id, is_new, desc_hash):
        return DescWrapper(full_url_path, title, "", company_id, is_new, "", "", "",
                           "", None, None, desc_hash)

    def get_html_content_from_md(self, md):
        return markdown.markdown(md)

    # Methods with api request
    def health_check_to_api_server(self):
        resp = self.api_req_get(url=config.HEALTH_ENDPOINT)
        assert util.check_response(resp, "application/json")
        return resp.json()

    def get_access_token_from_api_server(self):
        logger.debug(f"[{self.__class__.__name__}] {self.get_access_token_from_api_server.__name__}()")
        resp = self.api_req_get(url=config.ACCESS_TOKEN_ENDPOINT)
        assert util.check_response(resp, "application/json")
        return resp.json()["token"]

    def create_company_from_api_server(self, create_company_request):
        EndPoint.check_create_company_request(create_company_request)
        resp = self.api_req_post(timeout=config.DEFAULT_REQTIME,
                                 url=config.COMPANY_ENDPOINT,
                                 json=create_company_request)
        assert util.check_response(resp, "")
        json_result = resp.json()
        if json_result["companyCode"] != create_company_request["companyCode"]:
            raise Exception(
                f"[{self.__class__.__name__}] {self.create_company_from_api_server.__name__}:  invalid create company result: {json_result}")
        return json_result

    def check_is_company_exist(self, company_code_name):
        resp = self.api_req_get(url=config.COMPANY_ENDPOINT)
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)
        for company in json_data:
            if company["companyCode"] == company_code_name:
                return True
        return False

    def get_company_id_from_api_server(self, company_code_name):
        logger.debug(f"[{self.__class__.__name__}] {self.get_company_id_from_api_server.__name__}()")
        resp = self.api_req_get(url=config.COMPANY_ENDPOINT)
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)
        for company in json_data:
            if company["companyCode"] == company_code_name:
                return company["companyId"]
        raise Exception(
            f"[{self.__class__.__name__}] {self.get_company_id_from_api_server.__name__}:  company not found for company_code_name:" + company_code_name)

    def get_category_id_from_api_server(self, category_codes):
        logger.debug(f"[{self.__class__.__name__}] {self.get_category_id_from_api_server.__name__}()")
        resp = self.api_req_get(url=config.CATEGORY_ENDPOINT)
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)
        json_data = list(filter(lambda x: x["categoryCode"] in category_codes, json_data))
        if len(category_codes) != len(json_data):
            raise Exception(
                f"[{self.__class__.__name__}] {self.get_category_id_from_api_server.__name__}:  one of category in category_codes not found:" + category_codes)
        return json_data

    def get_country_id_from_api_server(self, country_code):
        logger.debug(f"[{self.__class__.__name__}] {self.get_category_id_from_api_server.__name__}()")
        resp = self.api_req_get(url=config.COUNTRY_ENDPOINT)
        assert util.check_response(resp, "application/json")
        json_data = json.loads(resp.text)

        for country in json_data:
            if country["countryCode"] == country_code:
                return country["countryId"]
        raise Exception(
            f"[{self.__class__.__name__}] {self.get_country_id_from_api_server.__name__}:  country not found for country_code:" + country_code)

    def send_get_hash_reqeust_to_api_server(self, company_id, url, title):
        logger.debug(f"[{self.__class__.__name__}] {self.send_get_hash_reqeust_to_api_server.__name__}()")
        temp_desc = {
            "companyId": company_id,
            "url": url,
            "title": title
        }
        resp = self.api_req_post(timeout=config.DEFAULT_REQTIME,
                                 url=config.JOB_HASH_ENDPOINT,
                                 json=temp_desc)
        assert util.check_response(resp, 'text/plain', 200)
        assert resp.text is not None
        return resp.text

    def send_get_desc_request_by_hash_to_api_server(self, hash):
        resp = self.api_req_get(url=config.DESC_ENDPOINT + "?hash=" + hash)
        assert util.check_response(resp, "application/json", [200, 404])
        if resp.status_code == 200:
            return resp.json()
        return None

    def send_img_convert_request_to_api_server(self, content):
        logger.info(
            f"[{self.__class__.__name__}] {self.send_img_convert_request_to_api_server.__name__}() len(content):" + str(
                len(content)))
        data = {
            "img": base64.b64encode(content).decode("utf-8")
        }

        resp = self.api_req_post(timeout=config.IMG_GET_REQTIME,
                                 url=config.IMG_CONVERT_ENDPOINT,
                                 json=data)
        assert util.check_response(resp, 'text/plain', [200, 409])
        if resp.status_code == 409:
            return None
        else:
            return resp.text

    def send_desc_to_api_server_entry(self, scraped_desc):
        EndPoint.check_rest_desc_data(scraped_desc)
        try:
            self.send_desc_to_api_server(scraped_desc)
        except requests.exceptions.Timeout as e:
            logger.warning(
                f"[{self.__class__.__name__}] requests.exceptions. Timeout for send_desc_to_api_server:" + str(e))
            return False
        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}] unexpected error in send_desc_to_api_server:" + str(e))
            logger.warning(traceback.format_exc())
            return False
        return True

    def send_desc_to_api_server(self, scraped_desc):
        if scraped_desc["isNew"]:
            resp = self.api_req_post(timeout=config.API_DESC_REQTIME,
                                     url=config.DESC_ENDPOINT,
                                     json=scraped_desc)
            assert util.check_response(resp, "application/json", 200)
        else:
            if config.UPDATE_MODE:
                desc_id = self.send_get_desc_request_by_hash_to_api_server(scraped_desc["hash"])[0]["descId"]
                resp = self.api_req_put(timeout=config.API_DESC_REQTIME,
                                        url=config.DESC_ENDPOINT + f"/{desc_id}",
                                        json=scraped_desc)
                assert util.check_response(resp, "application/json", 200)
            else:
                resp = self.api_req_post(timeout=config.API_DESC_REQTIME,
                                         url=config.DESC_ENDPOINT,
                                         json=scraped_desc)
                assert util.check_response(resp, "application/json", 403)
        return resp

    def report_existing_hashs_to_api_server(self, hashs, company_id):
        logger.info(
            f"[{self.__class__.__name__}] report_existing_hashs_to_api_server() company_id[{company_id}] reporting hashs of size {len(hashs)}")
        resp = self.api_req_post(timeout=config.API_REPORTING_REQTIME,
                                 url=config.COMPANY_ENDPOINT + "/" + str(company_id) + "/job",
                                 json=hashs)
        assert util.check_response(resp, "application/json")
        return resp

    # Methods without api request
    def get_text_content_from_image_tag(self, origin_text_content, representative_img_tag):
        result = self.send_img_convert_request_to_api_server(representative_img_tag)
        if result is None:
            return None
        return origin_text_content

    def pack_desc_for_rest(self, desc_wrapper):
        if len(desc_wrapper.desc_tuple) != 12:
            raise Exception(
                f"[{self.__class__.__name__}] {self.pack_desc_for_rest.__name__}(): invalid desc_tuple : " + str(
                    desc_wrapper.desc_tuple))

        url, title, hinted_title, company_id, is_new, department, content, text_content, screenshot, start_date, end_date, desc_hash = desc_wrapper.desc_tuple
        text_content = self.refine_text_content(text_content)
        desc_data = {}
        if self.type == "html" and (is_new or config.UPDATE_MODE):
            refined_content = self.refine_links_in_tags(content,
                                                        urlparse(url).scheme + "://" + urlparse(url).netloc + "/")
            desc_data["content"] = refined_content
            if len(text_content) < config.MINIMUM_JOBDESC_TEXT_LEN:
                representative_img_tag = self.get_representative_img_tag_content(refined_content, url)
                if representative_img_tag is None:
                    # Doesn't have any of usable img tag. Just use text_content.
                    desc_data["textContent"] = text_content

                # Does have img tag. Check whether job description already exists.
                elif self.check_hash_not_exist(util.get_hash_of(company_id, url, title)):
                    # Hash does not exist. send image-to-text convert request and use result as textContent
                    text_content_from_image = self.get_text_content_from_image_tag(text_content, representative_img_tag)
                    if text_content_from_image is None:
                        # API server denied to convert it. We should exclude it from desc_queue.
                        return None

                    if len(text_content_from_image) > len(text_content):
                        # Got converted but if result text size of image is smaller than origin text_content
                        # use origin text_content
                        logger.debug(
                            f"[{self.__class__.__name__}] {self.pack_desc_for_rest.__name__}()"
                            f" use extracted text from image:" + text_content_from_image)
                        return text_content_from_image
                    desc_data["textContent"] = text_content_from_image

                else:
                    # Hash does exist. Just send it to api-server so that api-server should not expire it and
                    # just drop it.
                    desc_data["textContent"] = text_content
            else:
                desc_data["textContent"] = text_content

        else:
            desc_data["content"] = content
            desc_data["textContent"] = text_content

        desc_data["url"] = url
        desc_data["title"] = title
        desc_data["hintedTitle"] = hinted_title
        desc_data["companyId"] = company_id
        desc_data["isNew"] = is_new
        desc_data["department"] = department
        desc_data["screenshot"] = screenshot
        desc_data["startDate"] = None if start_date is None else start_date.isoformat()
        desc_data["endDate"] = None if end_date is None else end_date.isoformat()
        desc_data["hash"] = desc_hash
        desc_data["type"] = self.type
        return desc_data

    def extract_desc_and_send_to_api_server(self):
        existing_count, success_count, new_success_count = 0, 0, 0
        self.extract_job_list()
        existing_count = len(self.page_queue.queue)

        hashs = list(map(lambda x: x["hash"], list(self.page_queue.queue)))
        self.report_existing_hashs_to_api_server(hashs, self.company_id)
        for desc_wrapper in self.extract_from_endpoint():
            desc_data = self.pack_desc_for_rest(desc_wrapper)
            if desc_data is None or not desc_data["isNew"]:
                continue
            logger.debug(
                f"[{self.__class__.__name__}] {self.extract_desc_and_send_to_api_server.__name__}() desc_data:" + str(
                    desc_data))

            if self.send_desc_to_api_server_entry(desc_data):
                success_count += 1
                if desc_data["isNew"]:
                    new_success_count += 1
        return existing_count, success_count, new_success_count

    def extract_job_list(self):
        logger.error(f"[{self.__class__.__name__}] not implemented {self.extract_job_list.__name__}")
        raise NotImplementedError(f"[{self.__class__.__name__}] not implemented {self.extract_job_list.__name__}")

    def extract_from_endpoint(self):
        logger.error(f"[{self.__class__.__name__}] not implemented {self.extract_from_endpoint.__name__}")
        raise NotImplementedError(f"[{self.__class__.__name__}] not implemented {self.extract_from_endpoint.__name__}")

    def check_hash_not_exist(self, desc_hash):
        return self.send_get_desc_request_by_hash_to_api_server(desc_hash) is None

    def get_screenshot(self, element, driver):
        try:

            total_height = element.size["height"]
            for cnt in range(0, 5):
                if total_height == 0:
                    time.sleep(0.5)
                    total_height = element.size["height"]
                else:
                    break
                if cnt == 4:
                    return None, None
            driver.set_window_size(self.screenshot_width, total_height + config.SCREEN_EXTRA_HEIGHT)
            time.sleep(0.2)
            for cnt in range(0, 5):
                if element.size["width"] == 0 or element.size["height"] == 0:
                    time.sleep(0.5)
                else:
                    return element.screenshot_as_base64, element
            return None, None

        except StaleElementReferenceException as e:
            logger.warning(f"[{self.__class__.__name__}] get_screenshot() StaleElementReferenceException: {e}\n")
            return None, None

    def get_screenshot_from_localfile(self, content, driver):
        html_file_path = "/tmp/" + hashlib.sha256((uuid.uuid4().hex + content).encode('utf-8')).hexdigest() + ".html"
        f = open(html_file_path, "w")
        f.write(content)
        f.close()

        driver.get("file://" + html_file_path)
        target_xpath = "/html"
        root = driver.find_element_by_xpath(target_xpath)
        driver.set_window_size(self.screenshot_width, root.size["height"] + config.SCREEN_EXTRA_HEIGHT)

        screenshot = driver.get_screenshot_as_base64()

        os.remove(html_file_path)
        return screenshot

    def get_element_by_xpath(self, target_xpath, driver, title=None):
        try:
            element = driver.find_element_by_xpath(target_xpath)
        except NoSuchElementException:
            if title is None:
                logger.warning(
                    f"[{self.__class__.__name__}] get_element_by_xpath() NoSuchElementException for xpath: {target_xpath}")
            else:
                logger.warning(
                    f"[{self.__class__.__name__}] get_element_by_xpath() NoSuchElementException for xpath: {target_xpath}\n" +
                    f"for title: {title}")
            return None
        return element

    def get_text_content_from_html(self, content, driver):
        html_file_path = "/tmp/" + hashlib.sha256((uuid.uuid4().hex + content).encode('utf-8')).hexdigest() + ".html"
        f = open(html_file_path, "w")
        f.write(content)
        f.close()
        driver.get("file://" + html_file_path)
        text = driver.find_element_by_xpath("/html").get_attribute("innerText")

        os.remove(html_file_path)
        return text

    @staticmethod
    def flush_desc_queue_to_list(desc_queue):
        desc_list = []
        try:
            while True:
                desc = desc_queue.get(timeout=0)
                desc_list.append(desc)
                desc_queue.task_done()
        except queue.Empty:
            pass
        return desc_list

    @staticmethod
    def check_create_company_request(request):
        check_list = {'companyCode': str, 'detail': dict, 'publicNameEng': str, 'publicNameKor': str,
                      'pattern': (dict, type(None)),
                      'logo': str}
        EndPoint.check_with_check_list(request, check_list)

    @staticmethod
    def check_create_company_request_detail(detail):
        check_list = {'parent': (int, type(None)), 'isGroup': bool, 'category': list,
                      'country': int}
        EndPoint.check_with_check_list(detail, check_list)

    @staticmethod
    def check_rest_desc_data(desc_data):
        check_list = {'url': str, 'title': str, 'hintedTitle': str, 'companyId': int, 'isNew': bool,
                      'department': str,
                      'content': str, 'textContent': str, 'screenshot': str, 'type': str,
                      'startDate': (str, type(None)),
                      'endDate': (str, type(None)), "hash": str}
        EndPoint.check_with_check_list(desc_data, check_list)

    @staticmethod
    def check_with_check_list(json_data, check_list):
        for key in check_list:
            if not key in json_data:
                raise Exception(
                    f"{EndPoint.check_rest_desc_data.__name__}() desc_data doesn`t key: {key} in :{json_data}")
            if not isinstance(json_data[key], check_list[key]):
                raise Exception(
                    f"{EndPoint.check_rest_desc_data.__name__}() desc_data doesn`t have valid data type for key: {key} , value: {json_data[key]}")

    @staticmethod
    def get_desc_hash(company_id, url, title):
        concatenated = str(company_id) + url + title
        return hashlib.sha256(concatenated.encode()).hexdigest()
