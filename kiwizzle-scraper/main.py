import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler

import requests

import config
import send_mail
from endpoint.classes.EndPoint import EndPoint
from endpoint.endpoints import endpoints

logger = logging.getLogger(config.LOGGER_NAME)


def init(use_file_log=False):
    class Unbuffered:
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            self.stream.write(data)
            self.stream.flush()

        def __getattr__(self, attr):
            return getattr(self.stream, attr)

    sys.stdout = Unbuffered(sys.stdout)

    if os.path.exists(config.LOGFILE_PATH):
        os.remove(config.LOGFILE_PATH)

    steam_handler = logging.StreamHandler()
    if use_file_log:
        file_handler = RotatingFileHandler(config.LOGFILE_PATH, mode='w', maxBytes=50 * 1024 * 1024,
                                           backupCount=2, encoding=None, delay=False)
        formatter = logging.Formatter('%(asctime)s - %(name)s [%(levelname)s] : %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        steam_handler.setFormatter(formatter)
    # logging levels: CRITICAL, ERROR, WARN, INFO, DEBUG
    if config.DEBUG:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    if config.DEBUG:
        steam_handler.setLevel(logging.DEBUG)
    else:
        steam_handler.setLevel(logging.INFO)
    logger.addHandler(steam_handler)


def health_check():
    _endpoint = EndPoint()
    logger.info("Connecting to kiwizzle-api")
    while True:
        try:
            if _endpoint.health_check_to_api_server() == True:
                break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.info(f"health_check: {config.HEALTH_ENDPOINT} doesn't reply  :" + str(e))
            time.sleep(5)
            continue
        except Exception as e:
            logger.error(
                f"health_check; Exception occur: While health checking END_POINT {config.HEALTH_ENDPOINT}" + str(e))
            logger.exception(e)
            exit()
    logger.info("kiwizzle-api Found")


def extract_one(endpoint_class, test=False):
    logger.info("Extraction start")
    total_count = 0
    success_total = 0
    new_success_total = 0
    try:
        endpoint = endpoint_class()
        endpoint.init_context_entry()
        logger.info(f"[{endpoint.__class__.__name__}] start extraction method extract_descs_to_queue()")
        total_count, success_total, new_success_total = endpoint.extract_desc_and_send_to_api_server()
        if total_count == 0:
            title = f"[{endpoint.__class__.__name__}] 0 desc scraped:"
            logger.warning(title)
        logger.info(
            f"[{endpoint.__class__.__name__}] total_count:{total_count}, sent success_total: {success_total}, new_success_total: {new_success_total}")
    except requests.exceptions.Timeout as e:
        logger.warning(f"[{endpoint.__class__.__name__}] requests.exceptions.Timeout:" + str(e))
        logger.warning(traceback.format_exc())
    except Exception as e:
        title = f"[{endpoint.__class__.__name__}] Exception occur:" + str(e)
        logger.error(title)
        logger.exception(e)
        if test == False:
            send_mail.send_mail(title, title + "\n" + "".join(traceback.format_tb(e.__traceback__)))
    return total_count, success_total, new_success_total


def extract():
    logger.info("Extraction start")
    result_scraped_total = 0
    result_success_total = 0
    result_new_total = 0

    for key in endpoints:
        scraped_count, success_total, new_success_total = extract_one(endpoints[key])
        result_scraped_total += scraped_count
        result_success_total += success_total
        result_new_total += new_success_total
    logger.info(
        f"Extraction end.  result_scraped_total:{result_scraped_total}, sent result_success_total: {result_success_total}, result_new_total: {result_new_total}")


def extract_infinite():
    while True:
        extract()
        logger.info("Extraction ended. Get into sleep")
        time.sleep(config.SCAN_TERM_MINUTES)


def main():
    init()
    health_check()
    extract_infinite()


if __name__ == '__main__':
    main()
