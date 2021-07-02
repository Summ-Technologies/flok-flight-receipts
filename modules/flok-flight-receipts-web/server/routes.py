from flask_restful import Api

from .controllers import webhook

V1_PREFIX = "/v1."


def route_v1(path: str, minor: int = 0):
    return "/api" + V1_PREFIX + str(minor) + path


def route(path: str, version: str):
    return "/api/v" + version + path


def add_routes(api: Api):
    api.add_resource(webhook.WebhookController, route_v1("/webhook"))
    api.add_resource(webhook.WebhookPublisherTestController, route_v1("/webhook/test"))
