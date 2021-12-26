import json
import logging
from datetime import datetime
from typing import Any, Dict

from flok_flight_receipts.parser import (build_gmail_service, fetch_email_html,
                                         fetch_email_list, parse_emails)
from flok_flight_receipts.sheets import build_sheets_service, write_to_sheet
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
        userId = config["GOOGLE_SERVICE_WORKER_USER_ID"]
        # database setup
        session = db.setup_db_session(config["SQLALCHEMY_DATABASE_URI"])
        # gmail client setup
        service_acc_info = json.load(open(config["GOOGLE_SERVICE_ACC_FILE"], 'r'))
        gmail_service = build_gmail_service(service_acc_info, userId)
        sheets_service = build_sheets_service(service_acc_info)
        # gmail_service = build_service()
        
        groups = session.query(EmailLog).filter(EmailLog.active.is_(True)).all()
        for res in groups:
            # get list of emails (most recent first)
            messages = fetch_email_list(gmail_service, _userId=userId, count=500, to=res.address)
            print("Loaded", len(messages), "messages addressed to", res.address)
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
            
            emails = fetch_email_html(gmail_service, messages[:index], _userId=userId)

            print(f"parsing {len(emails)} emails")
            results, errs = parse_emails(emails, logging=True)

            write_to_sheet(sheets_service, res.sheet, results, errs)

            # correct = open("test.txt", "r").readlines()
            # test = open("report.txt", "r").readlines()
            # for i in range(len(correct)):
            #     if correct[i] != test[i]:
            #         print(f"\nError on line {i+1}:")
            #         print("Expected: ", correct[i])
            #         print("But got:  ", test[i])
            #         exit(0)
            # print("\n\nOutput correct.\n\n")

            logger.info(
                f"Successfully parsed emails",
            )
            # store most recent email processed
            res.email_id = messages[0]['id']
            session.commit()

    except Exception as e:
        logger.error(f"Error parsing emails", exc_info=e)

    channel.basic_ack(delivery_tag=method_frame.delivery_tag)
