import datetime
import json
import logging
import signal
import re

import tornado.autoreload
import tornado.ioloop
import tornado.web
import tornado.options
import pika

import rabbit

from shared import ADMIN_PORT, \
		configure_logger, \
		env, \
		json_serializer, \
		Hello


logger = logging.getLogger()


def now():
	return datetime.datetime.utcnow()


def is_updated_since(d1, seconds_old):
	return now() - d1 < datetime.timedelta(seconds=seconds_old)


class Listener(object):

	def __init__(self, name):

		self.updated_at = now()
		self.name = name
		self.last_push = {}
		self.notify = {}

	def as_dict(self):
		return {"updated_at": self.updated_at,
				"name": self.name,
				"last_push": self.last_push,
				"notify": self.notify}


class Listeners(object):
	def __init__(self):
		self.listeners = {}
		self.channel = rabbit.connect()

	def add(self, name, listener):
		self.listeners[name] = listener
		self._with_reconnect(lambda: self.channel.queue_declare(name))
		self.notify(name, "created")
		return listener

	def delete(self, name):
		del self.listeners[name]

	def get(self, name):
		listener = None
		if name:
			listener = self.listeners.get(name)
		return listener

	def get_all(self):
		return dict([(key, listener.as_dict()) for (key, listener) in self.listeners.items()])

	def notify(self, name, action, **kwargs):
		body = json.dumps(dict(action=action, **kwargs))
		logger.debug("notifying {} with {}: {}".format(name, action, body))
		self._with_reconnect(
				lambda: self.channel.basic_publish(exchange='', routing_key=name, body=body))

	def _with_reconnect(self, fn):
		try:
			fn()
		except (pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed):
			logger.debug("reconnecting rabbit")
			self.channel = rabbit.connect()
			fn()

	def notify_all(self, action):
		logger.debug("notifying all of {}".format(action))
		for name, _ in self.listeners.items():
			self.notify(name, action)

	def match_repo(self, repo_name):
		just_repo = repo_name.split('/')[-1]
		to_return = []

		for name, listener in self.listeners.items():
			for reg in ["{}$".format(just_repo), "^{}".format(just_repo)]:
				if re.search(reg, name):
					to_return.append(listener)
		return to_return


listeners = Listeners()


class BaseHandler(tornado.web.RequestHandler):

	def _write(self, obj):
		self.set_header("Content-type", "application/json")
		if obj is None:
			self.set_status(404)
			self.write('{}')
		else:
			self.write(json.dumps(obj, default=json_serializer))

	def error(self, msg):

		self.set_status(400)
		return self.write({"error": msg})


class ListenerHandler(BaseHandler):
	def get(self, name=None):
		listener = listeners.get(name)
		self._write(listener.as_dict() if listener else None)


class ListenersHandler(BaseHandler):
	def get(self):

		self._write(listeners.get_all())

	def post(self):

		data = tornado.escape.json_decode(self.request.body)
		name = data.get('name')
		if not name:
			return self.error("no name supplied")

		listener = listeners.add(name, Listener(name))
		logger.debug('added listener {}'.format(name))

		self._write(listener.as_dict())

	def put(self):
		data = tornado.escape.json_decode(self.request.body)
		name = data.get('name')
		if not name:
			return self.error("no name supplied")
		listener = listeners.get(name)
		if not listener:
			return self.error("no listener with that name")

		del data['name']
		logger.debug("updating listener({}) data".format(name))
		listeners.notify(name, 'update', data=data)

	def delete(self):

		data = tornado.escape.json_decode(self.request.body)
		name = data.get('name')
		if not name:
			return self.error("no name supplied")

		try:
			listeners.delete(name)
			self.write({"msg": "ok"})
		except KeyError:
			self.error("no such name {}".format(name))


class MatchHandler(tornado.web.RequestHandler):

	def post(self):

		body = self.request.body
		data = json.loads(body)
		repo_name = data['repo_name']
		pusher = data['pusher']
		branch = data['branch']
		latest_hash = data['latest_hash']
		all_modified = data['all_modified']

		matched = listeners.match_repo(repo_name)
		out = {}
		if not matched:
			msg = "no listener for {}".format(repo_name)
			logger.debug(msg)
			out = {"msg": msg}
		else:
			for listener in matched:
				listener.last_push = data
				name = listener.name
				logger.debug("notifying {}".format(name))
				listeners.notify(name, "push", pusher=pusher,
						branch=branch, latest_hash=latest_hash,
						all_modified=all_modified)
		self.write(out)


if __name__ == "__main__":

	app = tornado.web.Application(
			[
				(r'/listeners/(?P<name>[-_\w\d]+)/?', ListenerHandler),
				(r'/listeners/?', ListenersHandler),
				(r'/match/?', MatchHandler),
				(r'/', Hello, {"message": "ui"}),
			],
			debug=True
		)

	tornado.options.parse_command_line()
	logger = configure_logger('tornado.application')
	logger.debug("starting")
	admin_port = env("ADMIN_PORT", ADMIN_PORT)
	app.listen(admin_port, address='0.0.0.0')

	def on_reload(*args, **kwargs):
		listeners.notify_all("shutdown")

	def sig_handler(sig, frame):
		listeners.notify_all("shutdown")

	signal.signal(signal.SIGTERM, sig_handler)
	tornado.autoreload.add_reload_hook(on_reload)
	tornado.ioloop.IOLoop.instance().start()
