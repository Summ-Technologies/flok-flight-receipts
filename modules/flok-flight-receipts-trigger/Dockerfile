FROM python:3.7-alpine

# Allows requirements to be downloaded from custom pypi
ARG PIP_EXTRA_INDEX_URL
ARG PIP_TRUSTED_HOST

# Install required packages
COPY requirements.txt ./requirements.txt
RUN pip install --pre --no-cache -r requirements.txt \
    && rm requirements.txt \
    && apk del .build-deps

# Copy server code to the /app/ dir
COPY ./run.py ./run.py

ENTRYPOINT [ "python", "./run.py" ]