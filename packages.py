
from parse_render_lxml.renderer import LXML_Renderer
from .package import Package


class PackageList:
	"""
	An ordered collection of packages.
	"""
	def __init__(self, packages, logger, cache, compile_conf, document_conf):
		self.packages = []
		self.logger = logger
		for package in packages:
			self.add_package(package)

	def add_package(self, package):
		#todo: check dependencies and conflicts
		assert isinstance(package, Package)
		if not package.loaded:
			print('auto-loading {0:s}'.format(package))
			package.load()
		self.packages.append(package)

	def get_renderer(self):
		chosen = None
		for package in self.packages:
			self.logger.info('getting renderer for {0:s}'.format(package.name), level=3)
			# print('searching template in {0:}'.format(package))
			if package.Renderer is not None:
				if 'verbosity' and chosen is not None:
					self.logger.info('renderer {0:s} overridden by {1:}'.format(chosen.template, package.renderer),
						level=2)
				chosen = package.renderer
		if chosen is None:
			chosen = LXML_Renderer()
			self.logger.info('no package provided a renderer; falling back to the default {0:}'.format(chosen), level=1)
		return chosen

	#todo: cache (others too)
	def get_template(self):
		chosen = None
		for package in self.packages:
			self.logger.info('getting template for {0:s}'.format(package.name), level=3)
			# print('searching template in {0:}'.format(package))
			if package.template is not None:
				if 'verbosity' and chosen is not None:  #todo
					self.logger.info('template {0:s} overridden by {1:s}'.format(chosen.template, package.template),
						 level=2)
				chosen = package.template
		if chosen is None:
			#todo: make a default?
			raise NotImplementedError('None of the packages provides a template to use; {1:d} packages: {0:s}'
				.format(', '.join('{0:}-{1:}'.format(pack.name, pack.version) for pack in self.packages), len(self.packages)))
		return chosen.full_path

	def _yield_resources(self, attr_name, offline, minify=False):
		for package in self.packages:
			self.logger.info('getting {0:s} for {1:s}'.format(attr_name, package.name), level=3)
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

	def yield_compilers(self):
		for package in self.packages:
			for compilers in package.compilers:
				yield compilers

	def yield_pre_processors(self):
		for package in self.packages:
			for pre_processor in package.pre_processors:
				yield pre_processor


