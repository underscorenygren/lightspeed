import os
import pika

DEFAULT_Q = 'hello'

def connect(queue=DEFAULT_Q):
	host = os.environ.get("RABBIT_HOST", "rabbit")
	connection = pika.BlockingConnection(pika.ConnectionParameters(host=host,
		connection_attempts=10, retry_delay=1))
	channel = connection.channel()
	channel.queue_declare(queue=queue)
	return channel
