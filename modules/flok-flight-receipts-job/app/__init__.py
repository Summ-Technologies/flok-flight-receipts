import logging

from .worker import parse_new_flight_receipt

logger = logging.getLogger(__name__)


def run(config: dict):
    parse_new_flight_receipt(config)
