FROM python:3.7-slim
RUN apt-get update && apt-get upgrade -y

# Allows requirements to be downloaded from custom pypi
ARG PIP_EXTRA_INDEX_URL
ARG PIP_TRUSTED_HOST

# Install required packages
COPY requirements.txt ./requirements.txt
RUN apt-get install -y libpq-dev python3-dev \
    && pip install --pre --no-cache -r requirements.txt \
    && rm requirements.txt

# Copy server code to the /app/ dir
COPY ./app ./app
COPY ./run.py ./run.py

# Default app config
COPY ./config.py ./config.py
ENV APP_CONFIG=./config.py

ENTRYPOINT [ "python", "./run.py" ]