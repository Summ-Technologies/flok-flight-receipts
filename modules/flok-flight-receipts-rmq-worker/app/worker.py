import logging
import json
from datetime import datetime
from typing import Any, Dict
from flok_flight_receipts.parser import build_service_acc, fetch_email_list, fetch_email_html, parse_emails, summary
from hawk_db.email_log import EmailLog

from hawk_rmq.queue import NewFlightEmailReceiptMessage

from . import db
from ._config import config

logger = logging.getLogger(__name__)

def parse_new_flight_receipt(
    channel: Any, method_frame: Any, header_frame: Any, message: NewFlightEmailReceiptMessage
) -> None:
    logger.info(f"Received new user email message, {message.serialize()}")
    try:
        # database setup
        session = db.setup_db_session(config["SQLALCHEMY_DATABASE_URI"])
        # gmail client setup
        service_acc_info = json.load(open(config["GOOGLE_SERVICE_ACC_FILE"], 'r'))
        gmail_service = build_service_acc(service_acc_info)
        
        # query most recent based on date_added
+        res: EmailLog = (
+            session.query(EmailLog).order_by(EmailLog.date_added.desc()).first()
+        )

        # get list of emails (most recent first)
        userId = config["GOOGLE_SERVICE_WORKER_USER_ID"]
        messages = fetch_email_list(gmail_service, _userId=userId)
        if len(messages) == 0:
            logger.info("No emails found")
            return

        # check if email ids match most recent
        index = len(messages)
        if res != None:
            for i, message in enumerate(messages):
                if message['id'] == res.email_id:
                    index = i
                    break
        
        if index == 0:
            logger.info("No new emails")
            return

        # store most recent email processed
        newLog = EmailLog()
        newLog.email_id = messages[0]['id']
        session.add(newLog)
        session.commit()

        parts = fetch_email_html(gmail_service, messages[:index], _userId=userId)
        print(f"parsing {len(parts)} emails")
        infos = parse_emails(parts)
        for info in infos:
            if info != None:
                summary(info)
        logger.info(
            f"Successfully parsed emails",
        )
    except Exception as e:
        logger.error(f"Error parsing emails", exc_info=e)

    channel.basic_ack(delivery_tag=method_frame.delivery_tag)
