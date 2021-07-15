FROM python:3.7-alpine

# Allows requirements to be downloaded from custom pypi
ARG PIP_EXTRA_INDEX_URL
ARG PIP_TRUSTED_HOST

# Install required packages
COPY requirements.txt ./requirements.txt
RUN apk add postgresql-dev \
    && apk add --virtual .build-deps libffi-dev g++ gcc python3-dev musl-dev libxml2-dev libxslt-dev \
    && pip install --pre --no-cache -r requirements.txt \
    && rm requirements.txt \
    && apk del .build-deps

# Copy server code to the /app/ dir
COPY ./app ./app
COPY ./run.py ./run.py

# Default app config
COPY ./config.py ./config.py
ENV APP_CONFIG=./config.py

ENTRYPOINT [ "python", "./run.py" ]