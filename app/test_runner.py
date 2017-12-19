import subprocess

def run_one(to_exec, cwd):
	args = {'shell': True}
	output = ''
	worked = False
	if cwd:
		args['cwd'] = cwd
	try:
		output = subprocess.check_output(to_exec, **args)
		worked = True
	except subprocess.CalledProcessError as cpe:
		output = cpe.output
	except OSError as oe:
		output = "{}: {}, {}".format(str(oe), cwd, to_exec)
	except Exception as e:
		output = "uncaught exception on {}: {}".format(to_exec, str(e))

	return worked, output


def run(one_or_many, cwd):

	if isinstance(one_or_many, list):
		all_output = ""
		for to_exec in one_or_many:
			_worked, _output = run_one(to_exec, cwd)
			if not _worked:
				return _worked, _output
			else:
				all_output += "\n{}".format(_output)
		return True, all_output
	else:
		return run_one(one_or_many)


if __name__ == "__main__":
	_dir = "/Users/erik/code/test/"
	_program = "python tester.py"

	worked, output = run(_program, _dir)

	print "{}:{}".format("worked" if worked else "FAILED", output)
