import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOBANK_LISTINFO_PAGE_URL = "https://kakaobank.recruiter.co.kr/app/jobnotice/list.json"
KAKAOBANK_RECRUIT_PAGE_URL = "https://kakaobank.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOBANK_NAME = "KAKAO_BANK"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoBank(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOBANK_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOBANK_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(KAKAOBANK_NAME, ["상시채용", "기술", "정보보호", "2021 개발자 공개채용"])
