import os

# SQLALCHEMY
SQLALCHEMY_DATABASE_URI = os.environ["SQLALCHEMY_DATABASE_URI"]

# Google Credentials
GOOGLE_SERVICE_ACC_FILE = os.environ["GOOGLE_SERVICE_ACC_FILE"]
GOOGLE_SERVICE_WORKER_USER_ID = os.environ["GOOGLE_SERVICE_WORKER_USER_ID"]

# Slack Credentials
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]


# Logging
tmp = os.environ.get("SUMM_LOG_FILE")
if tmp:
    SUMM_LOG_FILE = tmp

tmp = os.environ.get("SUMM_LOG_FILE_SIZE")
if tmp:
    SUMM_LOG_FILE_SIZE = tmp
