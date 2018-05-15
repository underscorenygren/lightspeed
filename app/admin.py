import datetime
import json
import logging
import os
import re
import signal

import tornado.autoreload
import tornado.ioloop
import tornado.options
import tornado.web

import pika
import rabbit

from shared import ADMIN_PORT, \
		configure_logger, \
		env, \
		json_serializer, \
		Hello


logger = logging.getLogger()
listeners = None


def now():
	return datetime.datetime.utcnow()


def is_updated_since(d1, seconds_old):
	return now() - d1 < datetime.timedelta(seconds=seconds_old)

def filter_push_data(data):
	KEYS = ['pusher', 'branch', 'latest_hash', 'all_modified']
	return {key: value for (key, value) in data.items() if key in KEYS}


class Listener(object):

	def __init__(self, name=None, config=None,
			updated_at=None, last_push=None, last_pushes=None,
			notify=None):

		if not name:
			raise ValueError("Listener must have name")

		self.updated_at = updated_at or now()
		self.name = name
		self.last_push = last_push
		self.last_pushes = last_pushes or {}
		self.notify = notify or {}
		self.config = config or {}

	def as_dict(self):
		return {"updated_at": self.updated_at,
				"name": self.name,
				"last_push": self.last_push,
				"last_pushes": self.last_pushes,
				"notify": self.notify,
				"config": self.config}


class Listeners(object):
	def __init__(self):
		self.listeners = {}
		self.channel = rabbit.connect()

	def add(self, name=None, listener=None):
		if not listener:
			raise ValueError("listener required")
		name = name or listener.name
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

	def set_default_headers(self):
		self.set_header("Access-Control-Allow-Origin", "*")
		self.set_header("Access-Control-Allow-Headers", "x-requested-with")
		self.set_header('Access-Control-Allow-Methods', 'POST, PUT, GET, OPTIONS')

	def get(self):

		self._write(listeners.get_all())

	def options(self):
		self.set_status(204)
		self.finish()

	def post(self):

		data = tornado.escape.json_decode(self.request.body)
		name = data.get('name')
		if not name:
			return self.error("no name supplied")

		listener = listeners.get(name)
		if listener:
			logger.info("not updating existing listener {} on POST, use PUT".format(name))
		else:
			logger.debug('added listener {}'.format(name))
			listener = listeners.add(name=name, listener=Listener(name=name, config=data.get('config')))

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
		update_data = data.get('data')
		msg = "no action mapped"
		if update_data:
			logger.debug("updating listener({}) data".format(name))
			listeners.notify(name, 'update', data=update_data)
			msg = "updated {}".format(name)
		elif data.get('retrigger'):
			listener = listeners.get(name)
			if not listener:
				return self.error("no listener registed")
			if not listener.last_pushes:
				return self.error("no push received by this listener")

			msg = "retriggering {}".format(name)
			logger.debug(msg)
			for (key, push) in listener.last_pushes.items():
				logger.debug("notifying {}".format(key))
				listeners.notify(name, "push", **filter_push_data(push))

			listeners.notify(name, 'retrigger')
		elif data.get('config'):
			msg = "updating config"
			listener = listeners.get(name)
			if not listener:
				return self.error("no listener registed")
			logger.debug(msg)
			listener.config = data['config']

		else:
			return self.error(msg)

		self._write({"msg": msg})

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

		matched = listeners.match_repo(repo_name)
		out = {}
		if not matched:
			msg = "no listener for {}".format(repo_name)
			logger.debug(msg)
			out = {"msg": msg}
		else:
			branch = data['branch']
			for listener in matched:
				listener.last_pushes[branch] = data
				listener.last_push = data
				name = listener.name
				logger.debug("notifying {}".format(name))
				listeners.notify(name, "push", **filter_push_data(data))
		self.write(out)


if __name__ == "__main__":

	# NB: Global
	listeners = Listeners()
	app = tornado.web.Application(
			[
				(r'/listeners/(?P<name>[-_\w\d]+)/?', ListenerHandler),
				(r'/listeners/?', ListenersHandler),
				(r'/match/?', MatchHandler),
				(r'/([a-zA-z0-9]+[.a-z0-9]{3,5})', tornado.web.StaticFileHandler, {'path': os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ui')}),
				(r'/', Hello, {"message": "ui"}),
			],
			debug=True
		)
	data_store = '/tmp/ls-admin.json'

	def store_listeners():
		logger.info("catching signal, storing listeners on disk at {}".format(data_store))
		with open(data_store, 'w') as f:
			f.write(json.dumps([listener_dict for listener_dict in listeners.get_all().values()], indent=2, default=lambda _date: _date.isoformat()))

	def load_listeners():
		logger.info("loading listeners from disk at {}".format(data_store))
		try:
			with open(data_store, 'r') as f:
				for listener_dict in json.loads(f.read()):
					logger.info("loading {} from disk".format(listener_dict))
					try:
						listeners.add(listener=Listener(**listener_dict))
					except ValueError:
						logger.error("listener is malformed")

		except (IOError, ValueError):
			logger.info("couldn't load data store")

	tornado.options.parse_command_line()
	logger = configure_logger('tornado.application')
	logger.debug("starting")
	admin_port = env("ADMIN_PORT", ADMIN_PORT)
	load_listeners()
	app.listen(admin_port, address='0.0.0.0')

	def on_reload(*args, **kwargs):
		listeners.notify_all("shutdown")

	def sig_handler(sig, frame):
		store_listeners()
		listeners.notify_all("shutdown")

	signal.signal(signal.SIGTERM, sig_handler)
	signal.signal(signal.SIGINT, sig_handler)
	tornado.autoreload.add_reload_hook(on_reload)
	tornado.ioloop.IOLoop.instance().start()
