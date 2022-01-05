import os

import app
import summ_logging

from summ_common.config import Config

config = Config()

config.from_pyfile(os.environ["APP_CONFIG"])
summ_logging.configure_logging(config, debug=config.get("DEBUG", False))

app.run(config)