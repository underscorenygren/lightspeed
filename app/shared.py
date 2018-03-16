import logging
import datetime
import os
import tornado.web

ADMIN_PORT = 8080


def configure_logger(name):
	logger = logging.getLogger(name)
	logger.addHandler(logging.StreamHandler())
	logger.setLevel(logging.DEBUG)
	return logger


def env(key, default=None):
	return os.environ.get(key, default)


def json_serializer(obj):

	if isinstance(obj, datetime.datetime):
		return obj.isoformat()

	raise TypeError("coudldn't serialize {}".format(type(obj)))


class Hello(tornado.web.RequestHandler):

	def initialize(self, **kwargs):
		self.message = kwargs.get('message', 'world')

	def get(self):

		self.write({"hello": self.message})
