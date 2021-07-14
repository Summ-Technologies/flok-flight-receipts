import logging
from typing import List, Tuple

import pika

from summ_rabbitmq.connection import RMQConnection
from summ_rabbitmq.consume import RMQConsumer
from summ_rabbitmq.queue import BaseQueue
from hawk_rmq.queue import NEW_FLIGHT_EMAIL_RECEIPT_QUEUE

from . import _config
from .worker import parse_new_flight_receipt

logger = logging.getLogger(__name__)

queues: List[Tuple[BaseQueue, callable]] = [
    (NEW_FLIGHT_EMAIL_RECEIPT_QUEUE, parse_new_flight_receipt),
]

def run(config: dict):
    logger.info("Starting consumer...")
    logger.debug(f"Setting config object with values: {config}")

    _config.config.update(config)
    
    rmq_connection = RMQConnection(config=_config.config)
    for queue_callback in queues:
        logger.info("Adding queue %s.", queue_callback[0].queue_name)
        consumer = RMQConsumer(queue=queue_callback[0], connection=rmq_connection)
        consumer.setup_consumer(queue_callback[1])
    rmq_connection.get_channel().start_consuming()
    logger.info("Stopped consuming.")
    rmq_connection.teardown()
    logger.info("Connection torn down. Consumer closing...")