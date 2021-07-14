import os
import requests

worker_url = os.environ["WORKER_URL"]

requests.get(worker_url)
