import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOPAY_LISTINFO_PAGE_URL = "https://kakaopay.recruiter.co.kr/app/jobnotice/list.json"
KAKAOPAY_RECRUIT_PAGE_URL = "https://kakaopay.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOPAY_NAME = "KAKAO_PAY"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoPay(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOPAY_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOPAY_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(KAKAOPAY_NAME, ["2021년 경력 채용", "기술", "수시"])
