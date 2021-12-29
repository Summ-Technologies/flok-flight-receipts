from datetime import datetime

from slack_sdk import WebClient

from .sheets import SHEET_TAB_ID

CHANNEL = 'flight-receipts'


def create_slack_client(bot_token):
    return WebClient(token=bot_token)


def post_to_slack(client, start_time, n_groups, n_emails, n_errs, group_details):
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Flight Receipt Parser Results"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*When:*\n{start_time.strftime('%m/%d/%Y, %H:%M:%S')}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Duration:*\n~{(datetime.now() - start_time).seconds // 60} minutes"
                }
            ]
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*New Emails:*\n{n_emails}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Parsing Errors:*\n{n_errs}"
                }
            ]
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Distinct Groups:*\n{n_groups}"
                },
            ]
        },
    ]
    client.chat_postMessage(channel=CHANNEL, blocks=blocks)

    res = client.files_upload(channels=CHANNEL, initial_comment='View detailed group summaries here:',
                              content=group_details, filename='group_results.txt')
    print(res)


def group_summary(email_log, results, errs):
    summary = "=" * 45 + '\n'
    summary += f"Group {email_log.id}: {email_log.address} | https://docs.google.com/spreadsheets/d/{email_log.sheet}/edit#gid={SHEET_TAB_ID}\n"
    summary += f"• Received {len(results + errs)} new emails with {len(errs)} parsing errors.\n"

    summary += f"Error Descriptions:\n"
    for e in errs:
        summary += "-" * 30 + "\n"
        summary += f"\tReceived from: {e['address']}\n"
        summary += f"\tSubject: {e['subject']}\n"
        summary += f"\tError Message: {e['err']}\n"
        summary += f"\thttps://mail.google.com/#all/{e['id']}\n"

    return summary
