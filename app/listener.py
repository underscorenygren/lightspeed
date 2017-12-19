import os
import logging
import json
import requests
import argparse

import rabbit
from test_runner import run_test

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

def parse_config(args):
	TEST_NAME = "test"
	test_config = {"exec": "echo 'hello'", "name": TEST_NAME}
	cf = args.config
	if cf == TEST_NAME:
		return test_config, None

	config = json.loads(open(cf, 'r'))
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

	def recv(ch, method, properties, body):
		logger.debug("calling receive on {}".format(body))
		try:
			parsed = json.loads(body)
			action = parsed.get("action")
			if action == "push":
				worked, output = run_test(_exec, _dir)
				if worked:
					logger.info("test passed!")
				else:
					logger.error("FAILURE!\n{}".format(output))
			else:
				logger.info("not recognized action: {}".format(action))
		except:
			logger.error("error when trying to load body: {}".format(body))

	channel = rabbit.connect(queue=name)
	channel.basic_consume(recv, queue=name, no_ack=True)
	logger.info("consuming")
	url = "http://{}:{}/listeners".format(host, port)
	logger.info("registering {} on {}".format(name, url))
	requests.post(url, json={"name": name})
	channel.start_consuming()


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("config", help="the configuration file to attach to this listener")
	parser.add_argument("--host", default=os.environ.get("HOST", "server"))
	parser.add_argument("--port", default=os.environ.get("PORT", 8080))

	consume(parser.parse_args())
