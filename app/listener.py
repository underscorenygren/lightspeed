import argparse
import logging
import json
import os
import requests
import time

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
		url = "http://{}:{}/listeners".format(host, port)
		logger.info("connecting {} on {}".format(name, url))
		while disconnected:
			logger.debug("sleeping")
			time.sleep(1)
			try:
				resp = requests.post(url, json={"name": name})
				disconnected = resp.status_code != 200
			except requests.ConnectionError:
				logger.debug("couldn't connect")

	def notify(notify_data):
		url = "http://{}:{}/listeners".format(host, port)
		logger.debug("notifying {} on {}".format(name, url))
		try:
			resp = requests.put(url, json=dict(notify_data, name=name))
			if resp.status_code != 200:
				logger.error("error on notify: {}".format(resp.text))
		except requests.ConnectionError:
			logger.error("couldn't notify")

	def recv(ch, method, properties, body):
		logger.debug("calling receive on {}".format(body))
		#reloading config
		_config, _ = parse_config(args)
		try:
			parsed = json.loads(body)
			action = parsed.get("action")
			updated_branch = parsed.get("branch", 'master')
			if action == "push":
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
					notify_data = {"msg": "running hook",
						"branch": updated_branch}
					for attr in ['pusher', 'latest_hash']:
						notify_data[attr] = parsed.get(attr)
					notify(notify_data)
					worked, output = run(_exec, _dir, env={'branch': updated_branch}, logger=logger)

					notify_data['msg'] = "completed" if worked else "FAILED"
					if not worked:
						notify_data['output'] = output.split('\n')
					notify(notify_data)

					hook = _config.get("discord_hook")
					msg = "[{}] {}".format(name, "test passed!" if worked else "FAILURE!\n{}".format(output))
					logger.info(msg)
					fail_msg = "FAILED"
					if output:
						logger.info(output)
					if not worked:
						logger.info("[no output]")

					if hook:
						hook_error = None
						try:
							discord_msg = msg
							if not worked:
								out = "```{}```".format(output[:1900]) if output else "[no output]"
								discord_msg = "[{}] {} {} {}".format(name, fail_msg, _config.get("discord_notify"), out)
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
					else:
						logger.debug("no hook registered")

			elif action == "shutdown":
				logger.info("received shutdown signal, reconnecting")
				connect()
				logger.info("reconnected")

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
