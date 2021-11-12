import logging

import config
from endpoint.endpoints import endpoints
from main import init, health_check, extract_one

logger = logging.getLogger(config.LOGGER_NAME)


def run_one():
    init()
    health_check()
    extract_one(endpoints["Google"], test=True)


if __name__ == '__main__':
    run_one()
