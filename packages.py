
from notex_pkgs.lxml_pr.parser import LXML_Parser
from notex_pkgs.lxml_pr.renderer import LXML_Renderer
from notexp.resource import Resource
from .package import Package


class PackageList:
	"""
	An ordered collection of packages.
	"""
	def __init__(self, packages, logger, cache, compile_conf, document_conf):
		#todo: PackageList gets document_conf but individual packages do not
		self.packages = []
		self.logger = logger
		self.cache = cache
		self.compile_conf = compile_conf
		for package in packages:
			self.add_package(package)

	def add_package(self, package):
		#todo: check dependencies and conflicts
		assert isinstance(package, Package)
		if not package.loaded:
			self.logger.info('auto-loading {0:s}'.format(package), level=2)
			package.load()
		self.packages.append(package)

	def _get_single(self, attr_name, fallback=None):
		chosen = None
		for package in self.packages:
			self.logger.info('  getting {1:s} for {0:s}'.format(package.name, attr_name), level=3)
			if getattr(package, attr_name) is not None:
				if chosen is not None:
					self.logger.info('{2:s} {0:s} overridden by {1:}'.format(
						chosen.template, getattr(package, attr_name), attr_name), level=2)
				chosen = getattr(package, attr_name)
		if chosen is None:
			chosen = fallback
			self.logger.info('no package provided {1:s}; falling back to the default {0:}'.format(
				chosen, attr_name), level=2)
		return chosen

	def get_parser(self):
		return self._get_single('parser', LXML_Parser(None))

	def get_renderer(self):
		return self._get_single('renderer', LXML_Renderer(None))

	def get_template(self):
		fallback = Resource(logger=self.logger, cache=self.cache, compile_conf=self.compile_conf, group_name='fallback',
		                    resource_dir=self.compile_conf.code_dir, local_path='fallback_template.html')
		return self._get_single('template', fallback)

	def _yield_resources(self, attr_name, offline, minify=False):
		for package in self.packages:
			self.logger.info('  getting {0:s} for {1:s}'.format(attr_name, package.name), level=4)
			for resource in getattr(package, attr_name, ()):
				if offline:
					resource.make_offline()
				if minify:
					resource.minify()
				yield resource

	def yield_styles(self, offline=False, minify=False):
		return self._yield_resources('styles', offline=offline, minify=minify)

	def yield_scripts(self, offline=False, minify=False):
		return self._yield_resources('scripts', offline=offline, minify=minify)

	def yield_static(self, offline=False, minify=False):
		return self._yield_resources('static', offline=offline, minify=minify)

	def _yield_series(self, attr_name):
		for package in self.packages:
			self.logger.info('  getting {0:s} for {1:s}'.format(attr_name, package.name), level=4)
			for item in getattr(package, attr_name):
				yield item

	def yield_pre_processors(self):
		return self._yield_series('pre_processors')

	def get_tags(self):
		tags = {}
		for package in self.packages:
			for base_name, tag in package.tags.items():
				for tag_name in (base_name, '{0:s}-{1:s}'.format(package.name, base_name)):
					if tag_name in tags:
						if getattr(tags[tag_name][-1], 'final_handler', False):
							self.logger(('  tag handler {0:} for {1:} not registered because final_handler tag {2:} was '
								'registered before').format(tag, tag_name, tags[tag_name][-1]), level=2)
						else:
							tags[tag_name].append(tag)
					else:
						tags[tag_name] = [tag]
		return tags

	def yield_compilers(self):
		return self._yield_series('compilers')

	def yield_linkers(self):
		return self._yield_series('linkers')

	def yield_post_processors(self):
		return self._yield_series('post_processors')


