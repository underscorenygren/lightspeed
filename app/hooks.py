import logging
import json

import tornado.web
import tornado.options
from tornado.httpclient import AsyncHTTPClient
from shared import ADMIN_PORT, \
		configure_logger, \
		env, \
		json_serializer, \
		Hello


class ReceiveHook(tornado.web.RequestHandler):

	def post(self):

		logger = logging.getLogger('tornado.application')
		data = tornado.escape.json_decode(self.request.body)
		#pretty = json.dumps(data, indent=2)

		pusher = data.get("pusher", {}).get("name", "unknown")
		branch = data.get("ref", "missing").split('/')[-1]
		latest_hash = data.get("after")
		repo = data.get("repository", {})
		repo_name = repo.get("full_name")
		statuses_url = repo.get('statuses_url')
		status_url = None
		if statuses_url and statuses_url.find("{sha}") != -1:
			status_url = statuses_url.format(sha=latest_hash)

		all_modified = set()
		for commit in data.get("commits", []):
			for modified in commit.get("modified", []):
				all_modified.add(modified)
		deleted = data.get("deleted")
		if deleted:
			if not env("TRIGGER_ON_DELETE"):
				return self.write({"msg": "skipping delete action"})

		logger.info("{} pushed {}({}). Modified: {}".format(pusher, branch, latest_hash, all_modified))

		#logger.debug(json.dumps(data, indent=2))

		data = {
				"repo_name": repo_name,
				"pusher": pusher,
				"branch": branch,
				"latest_hash": latest_hash,
				"all_modified": [m for m in all_modified]}
		if status_url:
			data["status_url"] = status_url

		admin_url = "http://{}:{}/match/".format(
				env("ADMIN_DOMAIN", "127.0.0.1"),
				env("ADMIN_PORT", ADMIN_PORT))

		AsyncHTTPClient().fetch(admin_url,
				method="POST",
				headers={"Content-type": "application/json"},
				body=json.dumps(data, default=json_serializer),
				callback=lambda resp: logger.info(resp))

		self.write({"msg": "ok"})


if __name__ == "__main__":

	app = tornado.web.Application(
			[
				(r'/receive_hook', ReceiveHook),
				(r'/', Hello),
			],
			debug=True
		)

	tornado.options.parse_command_line()
	logger = configure_logger('tornado.application')
	logger.debug("starting hook server")
	app.listen(8000, address='0.0.0.0')

	tornado.ioloop.IOLoop.instance().start()
