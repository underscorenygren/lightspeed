## Lightspeed

Lightspeed is a lightweight Continuous Delivery/Integration runner. It's designed as a
DIY replacement to services such as CircleCI, Codeship, etc, for people who don't want
to give permissive access to the external services or just want more control over what tests
to run.

### Prerequisites

- rabbitmq server

### Philosophy

Lightspeed brokers messages from github hooks to listners that register with an administration
endpoint over HTTP/S. Each listener is configured to match against repo names, branches and files, a
and triggers scripts to run in response.

### Components

#### Listeners

Listeners allows you to registered desired behaviour that will be triggered when conditions are met.
Configuration is done via json:

```
{
  "name": "my-repo-with-name", //name substring matches repositories
  "exec": ["python tester.py"], //the commands to run on match
  "cwd": "/some/path", //will run execs in this directory
  "discord_hook": "https://discordapp.com/api/webhooks/someid/more-id", //discord support is experimental
  "discord_notify": "@here"
}
```

#### Admin server

The admin servers allows registration of listener hooks, and can be used for administration
tasks. It's run separately from the hook endpoint so you can apply different security polices
for the two (the admin server shouldn't be exposed to the public internet, since there is no
auth yet).

Under the hood, the admin server matches requests with config files, then uses python's
`subprocess` module to run commands and return the output.

#### Hook server

The hook server is another process that listens on a different port for receive_hook requests
from gitub. You can point those hook at it using [these instructions](https://support.hockeyapp.net/kb/third-party-bug-trackers-services-and-webhooks/how-to-set-up-a-webhook-in-github)

Technically, you can run admin and hook servers on separate machines, but I'd recommend running them locally.
The hook server POSTs to the admin server to register a received hook, so it must have access to
it.

#### Running

- `RABBIT_HOST=rabbit python app/admin.py`
- `python app/listener.py --host rabbit my-config-file.json`
- `python app/hooks.py`
