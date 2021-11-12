import os

DEBUG = False

UPDATE_MODE = False

NUM_WORKERS = 2

if os.environ.get('KIWIZZLE_API_HOST') != None and os.environ.get('KIWIZZLE_API_PORT') != None:
    API_BASE_URL = f"http://{os.environ['KIWIZZLE_API_HOST']}:{os.environ['KIWIZZLE_API_PORT']}/internal"
else:
    API_BASE_URL = "http://kiwizzle-internal-api:9191/internal"

HEALTH_ENDPOINT = API_BASE_URL + "/health"
COMPANY_ENDPOINT = API_BASE_URL + "/company"
CATEGORY_ENDPOINT = API_BASE_URL + "/category"
COUNTRY_ENDPOINT = API_BASE_URL + "/country"
DESC_ENDPOINT = API_BASE_URL + "/job"
IMG_CONVERT_ENDPOINT = API_BASE_URL + "/imageconvert"
ACCESS_TOKEN_ENDPOINT = API_BASE_URL + "/servicetoken"
ACCESS_TOKEN_COOKIE_NAME = "auth_token"

JOB_HASH_ENDPOINT = DESC_ENDPOINT + "/hash"

EMPTY_CONTENT = "*채용공고 참고"
SCAN_TERM_MINUTES = 60 * 60 * 1  # every 1 hours
LOGGER_NAME = "scraper"
LOGFILE_PATH = "./scraper.log"
DEFAULT_REQTIME = 5
IMG_GET_REQTIME = 30
API_DESC_REQTIME = 60
API_REPORTING_REQTIME = 60
SCRAPER_SELENIUM = "SELENIUM"
SCRAPER_BS4 = "BS4"
SELENIUM_HEADER = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
}
MINIMUM_JOBDESC_TEXT_LEN = 200

SCREEN_EXTRA_HEIGHT = 500

IMAGE_CONTENT_TYPES = ["image/", "application/octet-stream", "application/download"]
