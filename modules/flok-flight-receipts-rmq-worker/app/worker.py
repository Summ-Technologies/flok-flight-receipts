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
        userId = config["GOOGLE_SERVICE_WORKER_USER_ID"]
        # database setup
        session = db.setup_db_session(config["SQLALCHEMY_DATABASE_URI"])
        # gmail client setup
        service_acc_info = json.load(open(config["GOOGLE_SERVICE_ACC_FILE"], 'r'))
        gmail_service = build_service_acc(service_acc_info, userId)
        # gmail_service = build_service()
        
        # query most recent based on date_added
        res: EmailLog = (
            session.query(EmailLog).order_by(EmailLog.date_added.desc()).first()
        )

        # get list of emails (most recent first)
        messages = fetch_email_list(gmail_service, _userId=userId, count=500)
        print("Loaded", len(messages), "messages")
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
        report = ""
        results, errs = parse_emails(emails, logging=True)
        for i, info in enumerate(results):
            report += str(i+1) + "\n" + summary(info) + "\n"

        for email in errs:
            report += email['id'] + ": " + email['err'] + "\n"

        f = open("report.txt", "w")
        f.write(report)
        f.close()

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
        newLog = EmailLog()
        newLog.email_id = messages[0]['id']
        session.add(newLog)
        session.commit()

    except Exception as e:
        logger.error(f"Error parsing emails", exc_info=e)

    channel.basic_ack(delivery_tag=method_frame.delivery_tag)
