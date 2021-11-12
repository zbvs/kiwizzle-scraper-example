import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

KAKAOGAMES_LISTINFO_PAGE_URL = "https://kakaogames.recruiter.co.kr/app/jobnotice/list.json"
KAKAOGAMES_RECRUIT_PAGE_URL = "https://kakaogames.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

KAKAOGAMES_NAME = "KAKAO_GAMES"

logger = logging.getLogger(config.LOGGER_NAME)


class KakaoGames(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = KAKAOGAMES_LISTINFO_PAGE_URL
        self.recruit_page_url = KAKAOGAMES_RECRUIT_PAGE_URL
        self.screenshot_width = 800

    def init_context_entry(self):
        super().init_midas_context(KAKAOGAMES_NAME, [])
