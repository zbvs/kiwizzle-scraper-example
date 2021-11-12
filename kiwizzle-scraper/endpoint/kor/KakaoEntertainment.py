import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOENTERTAINMENT_LISTINFO_PAGE_URL = "https://kakaoent.recruiter.co.kr/app/jobnotice/list.json"
KAKAOENTERTAINMENT_RECRUIT_PAGE_URL = "https://kakaoent.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOENTERTAINMENT_NAME = "KAKAO_ENTERTAINMENT"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoEntertainment(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOENTERTAINMENT_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOENTERTAINMENT_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_midas_context(KAKAOENTERTAINMENT_NAME, ["개발자 공개채용(테크)"])
