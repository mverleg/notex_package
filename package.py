
from datetime import datetime
from inspect import isclass
from collections import OrderedDict
from copy import copy
from sys import stderr
from json_tricks.nonp import load
from os import listdir, walk, remove
from os.path import join, relpath, exists
from package_versions import VersionRange, VersionRangeMismatch
from shutil import rmtree
from compiler.utils import hash_str, hash_file, import_obj, link_or_copy
from notexp.bases import Configuration
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
	'command_arguments': [],  # todo: possibly merge with config (not all commands are config though)
	'config': None,
	'pre_processors': [],
	'parser': None,
	'tags': {},
	'compilers': [],
	'linkers': [],
	'substitutions': None,
	'post_processors': [],
	'renderer': None,
	'template': None,
	'static': [],
	'styles': [],
	'scripts': [],
	'readme': 'readme.rst',
	'credits': 'credits.txt',
}


CONFIG_FUNCTIONAL = {'command_arguments', 'pre_processors', 'parser', 'tags', 'compilers', 'linkers', 'substitutions',
	'post_processors', 'renderer', 'template', 'static', 'styles', 'scripts',}


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
		# initialize actions
		self.config = self.parser = self.renderer = None
		self.pre_processors = self.compilers = self.linkers = self.post_processors = ()
		self.tags = OrderedDict()
		self.substitutions = OrderedDict()

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
		# print('chose version', choice, 'from', versions, 'because of', self.version_request)

	def load(self):
		"""
		Loading should not be automatic because it should also work for untrusted packages (e.g. to get the signature).
		"""
		# link_or_copy(self.path, join(self.compile_conf.PACKAGE_DIR, self.name))
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
		self.load_actions(conf)
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

	def _set_up_import_dir(self):
		imp_dir = join(self.compile_conf.PACKAGE_DIR, self.name)
		if exists(imp_dir):
			try:
				with open(join(self.compile_conf.PACKAGE_DIR, '{0:s}.version'.format(self.name)), 'r') as fh:
					stored_version = fh.read()
			except IOError:
				stored_version = None
			if self.version != stored_version:
				self.logger.info('removing wrong version {2:} of package {0:s} from "{1:s}"'.format(self.name,
					imp_dir, stored_version), level=3)
				try:
					remove(imp_dir)
				except IsADirectoryError:
					rmtree(imp_dir)
		if not exists(imp_dir):
			self.logger.info('copy package {0:} to "{1:}"'.format(self.name, imp_dir), level=3)
			link_or_copy(self.path, join(self.compile_conf.PACKAGE_DIR, self.name), exist_ok=True, allow_linking=True)
			with open(join(self.compile_conf.PACKAGE_DIR, '{0:s}.version'.format(self.name)), 'w+') as fh:
				fh.write(self.version)

	def _import_from_package(self, imp_path):
		"""
		First try to import from the package, otherwise fall back to normal pythonpath.
		"""
		try:
			return import_obj('{0:s}.{1:s}'.format(self.name, imp_path))
		except ImportError:
			return import_obj(imp_path)

	def load_actions(self, conf):
		"""
		Load actions like pretty much everything: pre-processors, parsers, tags, compilers, linkers, substitutions,
		post_processors and renderers).
		"""
		def instantiate_action(action, **kwargs):
			if isclass(action):
				try:
					action = action(self.config, **kwargs)
				except TypeError as err:
					raise InvalidPackageConfigError(('action {0:} for package {1:} did not accept the given arguments: '
						'config and kwargs {2:}; alternatively it might have raised a TypeError {3:}')
						.format(action, self, kwargs, err))
			if not hasattr(action, '__call__'):
				raise InvalidPackageConfigError(('action {0:} for package {1:} should be a class (and/)or a callable')
					.format(action, self, kwargs))

			return action

		#todo: better errors, also logging
		self._set_up_import_dir()
		if conf['config']:
			Config = self._import_from_package(conf['config'])
			if Config is None:
				Config = Configuration
			self.config = Config(self.options)
		self.pre_processors = tuple(instantiate_action(self._import_from_package(obj_imp_path))
			for obj_imp_path in conf['pre_processors'])
		if conf['parser']:
			Parser = self._import_from_package(conf['parser'])
			self.parser = Parser(self.config)
		# cache tags which are known under two names, for performance and so that they are identical
		_tag_alias_cache = {}
		for name, obj_imp_path in conf['tags'].items():
			if obj_imp_path not in _tag_alias_cache:
				_tag_alias_cache[obj_imp_path] = instantiate_action(
					self._import_from_package(obj_imp_path))
			self.tags[name] = _tag_alias_cache[obj_imp_path]
		self.compilers = tuple(instantiate_action(self._import_from_package(obj_imp_path))
			for obj_imp_path in conf['compilers'])
		self.linkers = tuple(instantiate_action(self._import_from_package(obj_imp_path))
			for obj_imp_path in conf['linkers'])
		if conf['substitutions']:  #todo (maybe)
			raise NotImplementedError('substitutions')
		self.post_processors = tuple(instantiate_action(self._import_from_package(obj_imp_path))
			for obj_imp_path in conf['post_processors'])
		if conf['renderer']:
			Renderer = self._import_from_package(conf['renderer'])
			self.renderer = Renderer(self.config)


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
				break
		else:
			raise InvalidPackageConfigError('{0:} does not have any functionality ({1:s} are all empty)'.format(
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

	# def yield_compilers(self):
	# 	for compiler in self.compilers:
	# 		yield compiler


