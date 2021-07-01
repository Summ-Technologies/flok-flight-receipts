import logging

from flask_restful import Resource
from flok_flight_receipts import emailtest
from summ_web import responses
from webargs import fields
from webargs.flaskparser import use_args

logger = logging.getLogger(__name__)


class WebhookController(Resource):
    def get(self):
        """Runs the script with saved emails"""
        infos = emailtest.main()
        return responses.success(infos)

    post_data = {"email": fields.Str(required=True)}

    @use_args(post_data)
    def post(self, post_args: dict):
        """Parses for given email"""
        email_html = post_args.get("email")
        info = emailtest.parse(
            email_html,
            emailtest.get_codes(emailtest.CodeType.AIRPORT),
            emailtest.get_codes(emailtest.CodeType.AIRLINE),
        )
        return responses.success(info)
