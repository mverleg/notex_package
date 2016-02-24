
from os import listdir
from os.path import join, dirname


dir = join(dirname(__file__), 'licenses')
files = listdir(dir)

LICENSES = {}
for file in listdir(dir):
	with open(join(dir, file)) as fh:
		LICENSES[file] = fh.read()


