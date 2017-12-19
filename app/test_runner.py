import subprocess

def run_test(to_exec, cwd):

	output = "no output captured"
	worked = False
	args = {'shell': True}
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


if __name__ == "__main__":
	_dir = "/Users/erik/code/test/"
	_program = "python tester.py"

	worked, output = run_test(_program, _dir)

	print "{}:{}".format("worked" if worked else "FAILED", output)
