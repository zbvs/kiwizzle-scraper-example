import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOMOBILITY_LISTINFO_PAGE_URL = "https://kakaomobility.recruiter.co.kr/app/jobnotice/list.json"
KAKAOMOBILITY_RECRUIT_PAGE_URL = "https://kakaomobility.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOMOBILITY_NAME = "KAKAO_MOBILITY"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoMobility(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOMOBILITY_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOMOBILITY_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(KAKAOMOBILITY_NAME, ["기술"])
