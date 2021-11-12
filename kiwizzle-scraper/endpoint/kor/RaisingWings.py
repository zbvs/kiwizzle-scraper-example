import logging

import config
from endpoint.classes.MidasEndpoint import MidasEndpoint

RISINGWINGS_LISTINFO_PAGE_URL = "https://krafton.recruiter.co.kr/app/jobnotice/list.json"
RISINGWINGS_RECRUIT_PAGE_URL = "https://krafton.recruiter.co.kr/app/jobnotice/view?systemKindCode={KIND_CODE}&jobnoticeSn={PAGE_NUM}"

RISINGWINGS_NAME = "RAISINGWINGS"

logger = logging.getLogger(config.LOGGER_NAME)


class RaisingWings(MidasEndpoint):
    def __init__(self):
        super().__init__()
        self.listinfo_page_url = RISINGWINGS_LISTINFO_PAGE_URL
        self.recruit_page_url = RISINGWINGS_RECRUIT_PAGE_URL

    def init_context_entry(self):
        super().init_midas_context(RISINGWINGS_NAME, [])
