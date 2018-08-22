import argparse
import logging
import json
import os
import requests
import time
import portalocker

import rabbit
from test_runner import run

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

def parse_config(args):
	TEST_NAME = "test"
	test_config = {"exec": "echo 'hello'", "name": TEST_NAME}
	cf = args.config
	if cf == TEST_NAME:
		return test_config, None

	config = json.loads(open(cf, 'r').read())
	_dir = os.path.dirname(cf)
	return config, _dir


def consume(args):
	host = args.host
	port = args.port
	url = "http://{}:{}/listeners".format(host, port)

	config, _dir = parse_config(args)
	name = config.get('name')
	if not name:
		logger.error("No name set in config!")

	_exec = config['exec']
	cwd = config.get('cwd')
	if cwd:
		_dir = cwd

	def connect():
		disconnected = True
		logger.info("connecting {} on {}".format(name, url))
		while disconnected:
			logger.debug("sleeping")
			time.sleep(1)
			try:
				resp = requests.post(url, json={"name": name, "config": config})
				disconnected = resp.status_code != 200
			except requests.ConnectionError:
				logger.debug("couldn't connect")

	def update_config(new_config):
		_config, _dir = parse_config(args)
		name = _config['name']
		if _dir is None:
			return
		if not new_config:
			logger.info("skipping update of empty config")
			return

		if 'name' in new_config:
			del new_config['name']
		_config.update(new_config)

		with open(os.path.join(_dir, args.config), 'w') as config_file:
			logger.info("updating config {}".format(config_file))
			config_file.write(json.dumps(_config, indent=2))
			requests.put(url, json={"name": name, "config": _config})

	def notify(notify_data):
		url = "http://{}:{}/listeners".format(host, port)
		logger.debug("notifying {} on {}".format(name, url))
		try:
			resp = requests.put(url, json=dict(notify_data, name=name))
			if resp.status_code != 200:
				logger.error("error on notify: {}".format(resp.text))
		except requests.ConnectionError:
			logger.error("couldn't notify")

	def discord_notify(_config, msg):
		hook = _config.get("discord_hook")
		if hook:
			hook_error = None
			try:
				discord_user = _config.get("discord_notify", u'')
				discord_msg = u"{} {}".format(discord_user, msg)\
						.replace(name, u'`{}`'.format(name))\
						.replace(u'FAILED', u'**FAILED**')

				resp = requests.post(hook, json={"content": discord_msg})
				if resp.status_code != 200:
					hook_error = resp.text
			except requests.RequestException as re:
				hook_error = str(re)
				logger.exception("hook failed")
			if hook_error:
				logger.error("Hook failed to execute: {}".format(hook_error))
			else:
				logger.debug("hook ok")

	def github_status(parsed, state, token):
		if token:
			try:
				resp = requests.post(parsed['status_url'], json={
					"state": state,
					"context": 'ci'},
					headers={
					"Authorization": "token {}".format(token)}
				)
				logger.info("{}: {}".format(resp.status_code, resp.text))
			except requests.exceptions.RequestException:
				logger.exception("couldn't post to github status")

	def run_hook(_config, parsed, updated_branch):

		github_status(parsed, 'pending', _config.get('github_status_token'))

		notify_data = {"msg": "running hook",
			"branch": updated_branch}
		for attr in ['pusher', 'latest_hash']:
			notify_data[attr] = parsed.get(attr)
		notify(notify_data)
		discord_notify(_config, "{pusher} {msg} {name} on {branch}".format(**dict(notify_data, name=name)))
		worked, output = run(_exec, _dir, env={'branch': updated_branch}, logger=logger)

		msg = u"CI job {} {} on branch({})".format(name, "succeeded" if worked else "FAILED", updated_branch)
		notify_data['msg'] = msg
		discord_msg = msg
		logger.info(msg)

		_status = 'success'

		if not worked:
			notify_data['output'] = output.split('\n')
			discord_msg += u"\n```{}```".format(output[-1800:]) if output else "`[no output]`"
			_status = 'failure'

		github_status(parsed, _status, _config.get('github_status_token'))
		notify(notify_data)
		discord_notify(_config, discord_msg)

		if output:
			logger.info(output)
		else:
			logger.info("[no output]")

	def handle_push(_config, parsed, updated_branch):
		branch_filter = _config.get('branch_filter')
		branch = parsed.get("branch")
		filtered = False
		if branch_filter:
			if not isinstance(branch_filter, list):
				logger.error("branch filter isn't a list")
				filtered = True
			elif branch not in branch_filter:
				logger.info("skipping, branch '{}' not in {}".format(branch, branch_filter))
				filtered = True

		files_filter = _config.get("files_filter")
		if not filtered and files_filter:
			if not isinstance(files_filter, list):
				filtered = True
				logger.error("files filter must be a list")
			else:
				all_modified = parsed.get("all_modified")
				filtered = True
				for modified in all_modified:
					for file_filter in files_filter:
						if modified.find(file_filter) != -1:
							logger.debug("found filter match {} with {}".format(file_filter, modified))
							filtered = False
							break
				if filtered:
					logger.debug("modified {} not in {}".format(all_modified, files_filter))
					logger.info("no match in file filters")

		if filtered:
			logger.debug("skipping b/c of filter")

		else:
			lock_file = _config.get('lock_file')
			if lock_file:
				logger.info("acquiring lock {}".format(lock_file))
				timeout = 3 * 60
				try:
					with portalocker.Lock(lock_file, timeout=timeout):
						run_hook(_config, parsed, updated_branch)
				except portalocker.exceptions.LockException:
					logger.error("lock acquisition timeout on {} after {}".format(lock_file, timeout))
			else:
				run_hook(_config, parsed, updated_branch)

	def recv(ch, method, properties, body):
		logger.debug("calling receive on {}".format(body))
		#reloading config
		_config, _ = parse_config(args)
		try:
			parsed = json.loads(body)
			action = parsed.get("action")
			updated_branch = parsed.get("branch", 'master')
			if action == "push":
				handle_push(_config, parsed, updated_branch)

			elif action == "shutdown":
				logger.info("received shutdown signal, reconnecting")
				connect()
				logger.info("reconnected")

			elif action == 'update':
				update_config(parsed.get('data', {}))

			elif action == "created":
				logger.info("successfully connected")
			else:
				logger.info("not recognized action: {}".format(action))
		except:
			logger.exception("error when trying to load body: {}".format(body))

	channel = rabbit.connect(queue=name, host=args.rabbit_host)
	channel.basic_consume(recv, queue=name, no_ack=True)
	logger.info("consuming")
	connect()
	channel.start_consuming()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("config", help="the configuration file to attach to this listener")
	parser.add_argument("--host", default=os.environ.get("HOST", "server"))
	parser.add_argument("--port", default=os.environ.get("PORT", 8080))
	parser.add_argument("--rabbit-host", default=os.environ.get("RABBIT_HOST"))

	consume(parser.parse_args())
