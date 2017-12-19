import logging
import json
import datetime

import tornado.ioloop
import tornado.web
import tornado.options

import rabbit


def configure_logger(name):
	logger = logging.getLogger(name)
	logger.addHandler(logging.StreamHandler())
	logger.setLevel(logging.DEBUG)
	return logger


def now():
	return datetime.datetime.utcnow()


def is_updated_since(d1, seconds_old):
	return now() - d1 < datetime.timedelta(seconds=seconds_old)


class Listener(object):

	def __init__(self, name):

		self.updated_at = now()
		self.name = name

	def as_dict(self):
		return {"updated_at": self.updated_at,
				"name": self.name}


class Listeners(object):
	def __init__(self):
		self.listeners = {}
		self.channel = rabbit.connect()

	def add(self, name, listener):
		self.listeners[name] = listener
		self.channel.queue_declare(name)
		self.notify(name, "created")
		return listener

	def delete(self, name):
		del self.listeners[name]

	def get_all(self):
		return dict([(key, listener.as_dict()) for (key, listener) in self.listeners.items()])

	def notify(self, name, action):
		body = json.dumps({"action": action})
		logger.debug("notifying {} with {}: {}".format(name, action, body))
		self.channel.basic_publish(exchange='', routing_key=name, body=body)

	def notify_all(self, action):
		logger.debug("notifying all")
		for name, _ in self.listeners.items():
			self.notify(name, action)


listeners = Listeners()


class ReceiveHook(tornado.web.RequestHandler):

	def post(self):

		logger = logging.getLogger('tornado.application')
		data = tornado.escape.json_decode(self.request.body)
		#pretty = json.dumps(data, indent=2)

		pusher = data.get("pusher", {}).get("name", "unknown")
		branch = data.get("ref", "missing").split('/')[-1]
		latest_hash = data.get("after")
		all_modified = set()
		for commit in data.get("commits", []):
			for modified in commit.get("modified", []):
				all_modified.add(modified)

		logger.info("{} pushed {}({}). Modified: {}".format(pusher, branch, latest_hash, all_modified))

		listeners.notify_all("push")

		self.write({})


def json_serializer(obj):

	if isinstance(obj, datetime.datetime):
		return obj.isoformat()

	raise TypeError("coudldn't serialize {}".format(type(obj)))


class ListenerHandler(tornado.web.RequestHandler):

	def _write(self, obj):
		self.write(json.dumps(obj, default=json_serializer))

	def error(self, msg):

		self.set_status(400)
		return self.write({"error": msg})

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


class Hello(tornado.web.RequestHandler):

	def get(self):

		self.write({"hello": "world"})


if __name__ == "__main__":

	app = tornado.web.Application(
			[
				(r'/receive_hook', ReceiveHook),
				(r'/listeners', ListenerHandler),
				(r'/', Hello),
			],
			debug=True
		)

	tornado.options.parse_command_line()
	logger = configure_logger('tornado.application')
	logger.debug("starting")
	app.listen(8080)
	tornado.ioloop.IOLoop.instance().start()
