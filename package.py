
from datetime import datetime
from sys import stderr
from collections import OrderedDict
from copy import copy
from json_tricks.nonp import load
from os import listdir, walk
from os.path import join, relpath
from package_versions import VersionRange, VersionRangeMismatch
from compiler.utils import hash_str, hash_file
from notexp.utils import PackageNotInstalledError, InvalidPackageConfigError
from .license import LICENSES
from .resource import get_resources
from .utils import get_package_dir


CONFIG_REQUIRED = {'name', 'version', 'license',}


CONFIG_DEFAULTS = {
	'requirements': {},
	'pip_requirements': [],
	'external_requirements': [],
	'conflicts_with': {},
	'command_arguments': [],
	'pre_processor': [],
	'parser': None,
	'linkers': [],
	'tags': {},
	'substitutions': None,
	'post_process': [],
	'renderer': None,
	'template': None,
	'static': [],
	'styles': [],
	'scripts': [],
	'readme': 'readme.rst',
	'credits': 'credits.txt',
}


CONFIG_FUNCTIONAL = {'command_arguments', 'pre_processor', 'parser', 'linkers', 'tags', 'substitutions',
	'post_process', 'renderer', 'template', 'static', 'styles', 'scripts',}


class Package:
	def __init__(self, name, version, options, logger, cache, compile_conf, *, packages_dir=None):
		self.loaded = False
		self.name = name
		self.logger = logger
		self.cache = cache
		self.compile_conf = compile_conf
		if packages_dir is None:
			packages_dir = get_package_dir()
		self.packages_dir = packages_dir
		if not options:
			options = {}
		self.options = options
		self.version_request = version
		self.path = self.version = None
		self.choose_version()

	def __repr__(self):
		return '<{0:}.{1:s}: {2:s} {3:s}>'.format(self.__class__.__module__, self.__class__.__name__, self.name,
			self.version or self.version_request)

	def get_versions(self):
		try:
			vdirs = sorted(listdir(join(self.packages_dir, self.name)))
		except FileNotFoundError:
			raise PackageNotInstalledError('package {0:s} not found (checked "{1:s}" which contains: [{2:s}])' \
				.format(self.name, self.packages_dir, ', '.join(listdir(self.packages_dir))))
		return vdirs

	def choose_version(self):
		"""
		Choose from among the available versions, or raise a VersionRangeMismatch if there are no candidates.
		"""
		versions = self.get_versions()
		try:
			choice = VersionRange(self.version_request).choose(versions, conflict='error')
		except VersionRangeMismatch:
			raise VersionRangeMismatch('package {0:s} has no installed version that satisfies {1:s} [it has {2:s}]' \
				.format(self.name, self.version_request, ', '.join(versions)))  #todo: add note about installing?
		self.version = choice
		self.path = join(self.packages_dir, self.name, self.version)
		print('chose version', choice, 'from', versions, 'because of', self.version_request)

	def load(self):
		"""
		Loading should not be automatic because it should also work for untrusted packages (e.g. to get the signature).
		"""
		try:
			with open(join(self.path, 'config.json')) as fh:
				conf = load(fh)
		except FileNotFoundError:
			raise InvalidPackageConfigError('config.json was not found in "{0:s}"'.format(self.path))
		except ValueError as err:
			raise InvalidPackageConfigError('config file for {0:} is not valid json'.format(self, str(err)))
		if not (conf.get('name', None) == self.name and conf.get('version', None) == self.version):
			raise InvalidPackageConfigError(('Package config for {0:} contains mismatching name and/or version '
				'{1:s} {2:s}').format(self, conf.get('name', None), conf.get('version', None)))
		# print(self.get_signature()[:8])
		self.load_meta(conf)
		conf = self.config_add_defaults(conf)
		self.config_load_textfiles(conf)
		self.load_resources(conf)
		self.loaded = True
		return self

	def load_resources(self, conf):
		"""
		Load non-python files: template, styles, scripts and static files.
		"""
		self.template, self.styles, self.scripts, self.static = get_resources(group_name=self.name, path=self.path,
			logger=self.logger, cache=self.cache, compile_conf=self.compile_conf, template_conf=conf['template'],
			style_conf=conf['styles'], script_conf=conf['scripts'], static_conf=conf['static'],
			note='from package {0:s}'.format(self.name)
		)

	def load_meta(self,  conf):
		"""
		Load meta data file which is added by the package index server.
		"""
		self.date = datetime.now()  #todo: tmp
		self.author = '??'  # todo
		self.signature = self.get_signature()  #todo: this should be the one from meta file; can't hash the whole project every load
		self.is_approved = True
		self.approved_on = datetime.now()  # todo (None if not approved)

	def config_add_defaults(self, config):
		"""
		Add default values for all parameters that have defaults, check that all parameters
		without defaults have some value, and check that there are no unknown parameters.
		"""
		unknown_keys = set(config.keys()) - CONFIG_REQUIRED - set(CONFIG_DEFAULTS.keys())
		if unknown_keys:
			raise InvalidPackageConfigError('{0:} has unknown configuration parameter(s): {1:}'.format(
				self, ', '.join(unknown_keys)))
		missing_keys = CONFIG_REQUIRED - set(config.keys())
		if missing_keys:
			raise InvalidPackageConfigError('{0:} is missing a value for configuration parameter(s): {1:}'.format(
				self, ', '.join(missing_keys)))
		conf = copy(CONFIG_DEFAULTS)
		conf.update(config)
		for func_key in CONFIG_FUNCTIONAL:
			if conf[func_key]:
				# print('  ',func_key)
				break
		else:
			raise NotImplementedError('{0:} does not have any functionality ({1:s} are all empty)'.format(
				self, ', '.join(CONFIG_FUNCTIONAL))) #todo
			logger.strict_fail('{0:} does not have any functionality ({1:s} are all empty)'.format(
				self, ', '.join(CONFIG_FUNCTIONAL)))
		return conf

	def config_load_textfiles(self, conf):
		try:
			with open(join(self.path, conf['readme'])) as fh:
				self.readme = fh.read()
		except FileNotFoundError:
			self.readme = None
		try:
			with open(join(self.path, conf['credits'])) as fh:
				self.credits = fh.read()
		except FileNotFoundError:
			self.credits = None
		if conf['license'] in LICENSES:
			self.license_text = LICENSES[conf['license']].format(name=self.author, year=self.date.year)
		else:
			self.license_text = '??'
			stderr.write('not an approved package (wrong license)')

	def yield_files_list(self):
		for root, directories, filenames in walk(self.path):
			for filename in filenames:
				yield relpath(join(root, filename), self.path)

	def get_file_signatures(self):
		file_sigs = OrderedDict()
		for file in  sorted(self.yield_files_list()):
			file_sigs[file] = hash_file(join(self.path, file))
		return file_sigs

	def get_file_signatures_string(self):
		return '\n'.join('{0:s}\t{1:s}'.format(name, hash) for name, hash in self.get_file_signatures().items())

	def get_signature(self):
		#on installing, not all the time
		return hash_str(self.get_file_signatures_string())

	def check_filenames(self):
		#on installing, not all the time
		#todo make sure all filenames are boring: alphanumeric or -_. or space(?)
		pass


