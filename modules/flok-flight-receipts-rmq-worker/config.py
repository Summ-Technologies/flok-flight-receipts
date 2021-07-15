import os

# SQLALCHEMY
SQLALCHEMY_DATABASE_URI = os.environ["SQLALCHEMY_DATABASE_URI"]

# RMQ connection config
RMQ_USER = os.environ["RMQ_USER"]
RMQ_PASSWORD = os.environ["RMQ_PASSWORD"]
RMQ_HOST = os.environ["RMQ_HOST"]
RMQ_PORT = os.environ["RMQ_PORT"]
RMQ_SECURE = os.environ.get("RMQ_SECURE")

# Google Credentials
GOOGLE_SERVICE_ACC_FILE = os.environ["GOOGLE_SERVICE_ACC_FILE"]
GOOGLE_SERVICE_WORKER_USER_ID = os.environ["GOOGLE_SERVICE_WORKER_USER_ID"]


# Logging
tmp = os.environ.get("SUMM_LOG_FILE")
if tmp:
    SUMM_LOG_FILE = tmp

tmp = os.environ.get("SUMM_LOG_FILE_SIZE")
if tmp:
    SUMM_LOG_FILE_SIZE = tmp
