FROM jaredhanson11/serverbase
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
COPY ./config.py ./
COPY ./server ./server
