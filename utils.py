
from sys import stderr
from appdirs import user_data_dir
from genericpath import isdir
from os import getenv, makedirs
from re import sub, match


class PackageError(Exception):
	pass


class PackageNotInstalledError(PackageError):
	pass


class InvalidPackageConfigError(PackageError):
	pass


PACKAGE_NAME_INFO = 'Package names can consist of between 3 and 32 alphanumeric characters, starting with a letter.' + \
	' They are case-insensitive and can contain "-_.," (not in sequence) which are all treated as "_".'


def is_external(path):
	return '//' in path


def unique_package_name(name):
	"""
	To avoid confusion, packages are case-insensitive and treat '-_,.+' all the same.
	"""
	new_name = name.lower()
	new_name = sub(r'[\s\.\-\+,]', r'_', new_name)
	new_name = sub(r'__+', r'_', new_name)
	assert match(r'^[a-z][a-z0-9_]{1,30}[a-z0-9]$', new_name), 'Name problem for "{0:s}": {1:s}'.format(name, PACKAGE_NAME_INFO)
	return new_name


def get_package_dir():
	"""
	Get the directory in which packages are installed if not overridden on project level.
	"""
	envpath = getenv('NOTEX_PACKAGE_DIR', '')
	if isdir(envpath):
		return envpath
	defpath = user_data_dir('ntp')
	if not isdir(defpath):
		stderr.write(('package path not set in NOTEX_PACKAGE_DIR and default location does not exist at "{0:s}"; ' +
			'it will be created (this is normal if you\'re running for the first time)').format(defpath))
		makedirs(defpath)
	return defpath

#
# curl_cache_dir = join(gettempdir(), 'notex_curl_cache')  # todo: to settings
# makedirs(curl_cache_dir, exist_ok=True, mode=0o700)
#
#
# def download_resource(frm, to, cache_time=3600):
# 	#todo: recursive
# 	name = hash_str(frm)
# 	cache_pth = join(curl_cache_dir, name)
# 	last = cache.get('{0:s}_lastmod'.format(name))
# 	if not last or (datetime.now() - last).total_seconds() > cache_time or not exists(cache_pth):
# 		print('DOWNLOAD', frm)  #todo tmp
# 		urlretrieve(frm, cache_pth)
# 		cache.set('{0:s}_lastmod'.format(name), datetime.now())
# 	link_or_copy(cache_pth, to, exist_ok=True)

