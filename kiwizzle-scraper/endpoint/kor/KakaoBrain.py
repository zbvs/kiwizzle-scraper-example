import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOBRAIN_LISTINFO_PAGE_URL = "https://kakaobrain.recruiter.co.kr/app/jobnotice/list.json"
KAKAOBRAIN_RECRUIT_PAGE_URL = "https://kakaobrain.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOBRAIN_NAME = "KAKAO_BRAIN"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoBrain(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOBRAIN_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOBRAIN_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(KAKAOBRAIN_NAME, ["AI Researcher", "AI Software Engineer"])
