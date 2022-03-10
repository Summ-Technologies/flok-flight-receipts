import json
import logging
from datetime import datetime

from flok_flight_receipts.parser import (build_gmail_service, fetch_email_html,
                                         fetch_email_list, parse_emails)
from flok_flight_receipts.sheets import build_sheets_service, write_to_sheet
from flok_flight_receipts.slack import *
from hawk_db.email_log import EmailLog
from sqlalchemy.orm.session import Session

from . import db

logger = logging.getLogger(__name__)


def parse_new_flight_receipt(config: dict) -> None:
    start_time = datetime.now()
    try:
        userId = config["GOOGLE_SERVICE_WORKER_USER_ID"]
        # database setup
        session: Session = db.setup_db_session(config["SQLALCHEMY_DATABASE_URI"])
        # gmail client setup
        service_acc_info = json.load(
            open(config["GOOGLE_SERVICE_ACC_FILE"], 'r'))
        gmail_service = build_gmail_service(service_acc_info, userId)
        sheets_service = build_sheets_service(service_acc_info)

        tot_emails = 0
        n_errs = 0
        slack_summary = ''

        groups = session.query(EmailLog).filter(
            EmailLog.active.is_(True)).all()
        for res in groups:
            try:
                # get list of emails (most recent first)
                logger.info("Fetching emails for %s", res.address)
                messages = fetch_email_list(
                    gmail_service, _userId=userId, count=500, to=res.address)
                print("Loaded", len(messages), "messages addressed to", res.address)
                if len(messages) == 0:
                    logger.info("No emails found")
                    continue

                # check if email ids match most recent
                index = len(messages)
                if res != None:
                    for i, message in enumerate(messages):
                        if message['id'] == res.email_id:
                            index = i
                            break

                if index == 0:
                    logger.info("No new emails")
                    continue

                emails = fetch_email_html(
                    gmail_service, messages[:index], _userId=userId)

                print(f"parsing {len(emails)} emails")
                results, errs = parse_emails(emails, logging=True)

                tot_emails += len(emails)
                n_errs += len(errs)
                slack_summary += group_summary(res, results, errs)

                try:
                    write_to_sheet(sheets_service, res.sheet, results, errs)
                except Exception as e:
                    logger.error("Something went wrong writing to the google sheet. email={%s}, sheet={%s}.", res.address, res.sheet, exc_info=e)
                    slack_summary += f'THERE WAS AN ERROR WRITING TO THE GOOGLE SHEET for email={res.address}.'
                    continue
            except Exception as e:
                    logger.error("Something went wrong with %s. Skipping...", res.address, exc_info=e)
                    slack_summary += f'THERE WAS AN ERROR WITH {res.address}.'
                    continue

            logger.info(
                f"Successfully parsed emails",
            )
            # store most recent email processed
            res.email_id = messages[0]['id']
            session.commit()
        
        try:
            slack_client = create_slack_client(config["SLACK_BOT_TOKEN"])
            post_to_slack(slack_client, start_time, len(groups), tot_emails, n_errs, slack_summary)
        except Exception as exc:
            logger.error("Slack message failed to post with summary of run", exc_info=exc)
        session.close()

    except Exception as e:
        logger.error(f"Error parsing emails", exc_info=e)
