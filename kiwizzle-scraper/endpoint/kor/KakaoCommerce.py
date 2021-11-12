import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOCOMMERCE_LISTINFO_PAGE_URL = "https://kakaocommerce.recruiter.co.kr/app/jobnotice/list.json"
KAKAOCOMMERCE_RECRUIT_PAGE_URL = "https://kakaocommerce.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOCOMMERCE_NAME = "KAKAO_COMMERCE"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoCommerce(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOCOMMERCE_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOCOMMERCE_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(KAKAOCOMMERCE_NAME, ["기술직군"])
