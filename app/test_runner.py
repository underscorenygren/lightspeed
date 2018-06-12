import os
import subprocess

def run_one(to_exec, cwd, env={}, logger=None):
	args = {'shell': True}
	output = ''
	worked = False
	_env = os.environ.copy()
	if not to_exec:
		return False, "no to_exec passed"

	for key, val in env.items():
		_env[key] = val
	if cwd:
		args['cwd'] = cwd
	args['env'] = _env
	args['stderr'] = subprocess.STDOUT
	try:
		if logger:
			logger.debug("running {} in {} with env {}".format(to_exec,
				cwd, _env))
		output = subprocess.check_output(to_exec, **args)
		worked = True
	except subprocess.CalledProcessError as cpe:
		output = cpe.output
	except OSError as oe:
		output = "{}: {}, {}".format(str(oe), cwd, to_exec)
	except Exception as e:
		output = "uncaught exception on {}: {}".format(to_exec, str(e))

	return worked, output.decode('utf-8', errors='ignore') if output else ''


def run(one_or_many, cwd, env={}, logger=None):

	if isinstance(one_or_many, list):
		all_output = u""
		for to_exec in one_or_many:
			_worked, _output = run_one(to_exec, cwd, env=env, logger=logger)
			if not _worked:
				return _worked, _output
			else:
				all_output += u"\n{}".format(_output)
		return True, all_output
	else:
		return run_one(one_or_many, cwd, env=env, logger=logger)


if __name__ == "__main__":
	_dir = "/Users/erik/code/test/"
	_program = "python tester.py"

	worked, output = run(_program, _dir)

	print "{}:{}".format("worked" if worked else "FAILED", output)
