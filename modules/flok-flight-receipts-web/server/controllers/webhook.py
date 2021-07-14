import logging

from flask_restful import Resource
from flok_flight_receipts import parser
from summ_web import responses
from webargs import fields
from webargs.flaskparser import use_args

from hawk_rmq.queue import NEW_FLIGHT_EMAIL_RECEIPT_QUEUE, NewFlightEmailReceiptMessage

from .. import rmq

flight_email_receipt_publisher = rmq.get_publisher(NEW_FLIGHT_EMAIL_RECEIPT_QUEUE)

logger = logging.getLogger(__name__)


class WebhookController(Resource):
    def get(self):
        """Runs the script with saved emails"""
        infos = parser.local()
        return responses.success(infos)

    post_data = {"email": fields.Str(required=True)}

    @use_args(post_data)
    def post(self, post_args: dict):
        """Parses for given email"""
        email_html = post_args.get("email")
        info = parser.parse(
            email_html,
            parser.get_codes(parser.CodeType.AIRPORT),
            parser.get_codes(parser.CodeType.AIRLINE),
        )

        return responses.success(infos)

class WebhookPublisherTestController(Resource):
    def get(self):
        flight_email_receipt_publisher.publish(NewFlightEmailReceiptMessage())
        return responses.success("Success")
