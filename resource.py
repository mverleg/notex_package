
from functools import partial
from glob import glob
from css_html_js_minify import process_single_css_file, process_single_js_file
from genericpath import isfile, getmtime
from os import makedirs
from os.path import join, exists, basename, splitext, abspath, relpath
from re import findall
from compiler.utils import hash_str, link_or_copy
from notexp.utils import InvalidPackageConfigError
from .utils import is_external


def get_resources(*, group_name, path, logger, cache, compile_conf, template_conf=None, style_conf=None,
		script_conf=None, static_conf=None, note=None):
	"""
	Get resource instances based on configuration such as a package's config.json or a <resource> tag.

	:param group_name: Name for the group this resource belongs to (e.g. package, document); used in filepaths.
	:param path: Path where local resources are found (not needed for remote ones).
	:param template_conf: Template configuration (a str path or None).
	:param style_conf: Style configuration (a list of either str paths or dict options).
	:param script_conf: Similar to style.
	:param static_conf: Similar to style, but only included, not copied.
	:return: template, styles, scripts, static
	"""
	def expand(res_info, cls, logger):
		collected = []
		for opts in res_info:
			if not isinstance(opts, dict):
				if is_external(opts):
					opts = dict(remote_path=opts)
				else:
					opts = dict(local_path=opts)
			if 'local_path' in opts:
				full_paths = abspath(join(path, opts['local_path']))
				#todo: recursive glob requires python 3.5 (and use ** for recursion)
				expanded = tuple(relpath(pth, path) for pth in glob(full_paths))
				if 'remote_path' in opts and '*' in opts['local_path']:
					raise InvalidPackageConfigError(('wildcard in local_path "{0:s}" not allowed if remote_path is set '
						'("{1:s}"), since remote_path cannot have wildcards').format(
							opts['local_path'], opts['path_path']))
				if not expanded:
					logger.info('no match for "{0:}" (expected in "{1:s}")'.format(opts, full_paths), level=2)
				del opts['local_path']
				for pth in expanded:
					collected.append(cls(logger=logger, cache=cache, compile_conf=compile_conf, group_name=group_name,
						resource_dir=path, local_path=pth, note=note, **opts))
			else:
				collected.append(cls(logger=logger, cache=cache, compile_conf=compile_conf, group_name=group_name,
					resource_dir=path, note=note, **opts))
		return collected

	template, styles, scripts, static = None, [], [], []
	if template_conf:
		template = HtmlResource(logger=logger, cache=cache, compile_conf=compile_conf, group_name=group_name,
			resource_dir=path, local_path=template_conf, note=note)
		assert isfile(join(path, template.local_path)), \
			'template {0:s} does not exist'.format(template.local_path)
	if style_conf:
		styles = expand(style_conf, cls=StyleResource, logger=logger)
		for resource in styles:
			assert resource.exists, 'style {0:} does not exist at {1:s}'.format(resource, resource.full_file_path)
	if script_conf:
		scripts = expand(script_conf, cls=ScriptResource, logger=logger)
		for resource in scripts:
			assert resource.exists, 'scripts {0:} does not exist at {1:s}'.format(resource, resource.full_file_path)
	if static_conf:
		static = expand(static_conf, cls=StaticResource, logger=logger)
		for resource in static:
			assert resource.exists, 'static {0:} does not exist at {1:s}'.format(resource, resource.full_file_path)
	return template, styles, scripts, static


#todo: should this be in compiler or here? it's used by Package and Section
class Resource:
	def __init__(self, logger, cache, compile_conf, group_name, resource_dir=None, *, local_path=None, remote_path=None,
			allow_make_offline=True, download_archive=None, downloaded_path=None, copy_map=None, allow_minify=True,
			tag_type=None, internalize=None, note=None):
		"""
		There are basically three options:

		1. Local files, given by local_path.
		2. Remote files, given by remote_path.
		3. Remote files to be downloaded before use, given by download_archive.

		Note that #2 may also be downloaded if allow_make_offline is True and archive is not set.
		Options #1 and #3 can't be used together (if there is already a local file, nothing will be downloaded).

		:param resource_dir: The directory where local resources are to be found.
		:param local_path: The local path of the resource (wildcards should be expanded before calling Resource.__init__).
		:param remote_path: The remote path of the resource (no wildcards).
		:param allow_make_offline: If true (default), the resource can be downloaded and included in the compiled document.
		:param download_archive: If set, when making an offline version, this archive (.zip) is downloaded and deflated rather than simply downloading remote_path.
		:param downloaded_path: Determines the local path to link after downloading the archive.
		:param copy_map: A mapping from original to final file paths for either local or archive data. Can be used to copy extra files or set the location of the main archive file.
		:param allow_minify: Allow (not guarantee) automatic minifying of resources (should be False if already minified; True by default).
		:param tag_type: Value of the tag's `type` parameter (if not standard) for scripts and styles.
		:param internalize: If `True`, put the file content inside the tag within the document, rather than linking it (the default `None` allows the compiler to choose).
		:param note: A simple text note that may be included.
		"""
		self.logger = logger
		self.cache = cache
		self.compile_conf = compile_conf

		assert local_path or remote_path or download_archive, ('{0:}: at least one of local_path, remote_path or '
			'download_archive should be set').format(self)
		if local_path:
			assert not download_archive and not downloaded_path, ('{0:}: if a local path is given, download_archive '
				'and downloaded_path should be empty').format(self)
		if download_archive:
			assert allow_make_offline, ('making an offline version of resource {0:} should be allowed '
				'if download_archive is set').format(self)
		if local_path:
			assert not download_archive and not downloaded_path, ('since local_path is set for resource {0:}, '
				'download_archive and downloaded_path are redundant options and should not be set').format(self)
		if downloaded_path:
			assert download_archive, ('{0:}: downloaded_path should only be set if '
				'download_archive is set').format(self)

		if local_path:
			self.local_path, self.local_params = self.split_params(local_path)
		else:
			self.local_path, self.local_params = None, ''
		self.remote_path = remote_path
		self.allow_make_offline = allow_make_offline
		self.download_archive = download_archive
		self.downloaded_path = downloaded_path
		self.copy_map = copy_map or {}
		self.resource_dir = resource_dir
		self.archive_dir = None
		self.group_name = group_name
		if not self.local_path and not self.remote_path:
			self.make_offline()
		self.allow_minify = allow_minify
		self.processed_path = None
		self.tag_type = tag_type
		if internalize:
			assert local_path or allow_make_offline, 'To internalize a resource, it must be available offline ' \
				'(either `local_path` is set or `allow_make_offline` is `True`)'
		self.internalize = internalize
		self.notes = [note] if note else []  #['from package "{0:s}"'.format(self.package.name)]
		# assert hasattr(local_copy, '__iter__') and not isinstance(local_copy, str), \
		# 	'{0:}: local_copy should be a list'.format(self)
		# assert hasattr(downloaded_copy, '__iter__') and not isinstance(downloaded_copy, str), \
		# 	'{0:}: downloaded_copy should be a list'.format(self)

	def __str__(self):
		pth_str = ('"{0:s}" & "{1:s}"' if (self.local_path and self.remote_path) else '"{0:s}{1:s}"')\
			.format((self.local_path or ''), (self.remote_path or ''))
		return '{0:s} {2:s} {1:s}'.format(self.__class__.__name__, pth_str, self.group_name)

	#todo: caching?
	def make_offline(self):
		"""
		Make the resource available offline if applicable.
		"""
		if self.local_path:
			return
		if not self.allow_make_offline:
			return
		self.resource_dir = join(self.compile_conf.TMP_DIR, 'offline', self.group_name)
		makedirs(self.resource_dir, exist_ok=True, mode=0o700)
		if self.download_archive:
			self._make_offline_from_archive()
		elif self.remote_path:
			self._make_offline_from_file()
		else:
			raise AssertionError('no resource found for {0:}'.format(self))

	@staticmethod
	def split_params(pth):
		parts = findall(r'^([^?#]*)([?#].*)$', pth)
		if not parts:
			return pth, ''
		return parts[0][0], parts[0][1]

	def _make_offline_from_file(self):
		self.logger.info(' making file available offline: {0:}'.format(self.remote_path), level=2)
		prefix = hash_str('{0:s}.{1:s}'.format(self.group_name, self.remote_path))
		pth, self.local_params = self.split_params(self.remote_path)
		self.local_path = '{0:.6s}{1:s}'.format(prefix, basename(pth))
		link_or_copy(
			src=self.cache.get_or_create_file(url=self.remote_path),
			dst=join(self.resource_dir, self.local_path),
			exist_ok=True,
		)
		self.notes.append('downloaded from "{0:s}"'.format(self.remote_path))

	def _make_offline_from_archive(self):
		self.logger.info(' making archive available offline: {0:}'.format(self.download_archive), level=2)
		prefix = hash_str('{0:s}.{1:s}'.format(self.group_name, self.download_archive))
		self.archive_dir = '{0:.8s}_{1:s}'.format(prefix,
			splitext(basename(self.split_params(self.download_archive)[0]))[0])
		archive = self.cache.get_or_create_file(url=self.download_archive)
		dir = self.cache.get_or_create_file(rzip=archive)
		link_or_copy(dir, join(self.resource_dir, self.archive_dir), exist_ok=True)
		self.local_path, self.local_params = self.split_params(self.downloaded_path)

	def minify(self):
		"""
		Subclasses can override this to minify file(s) (not gzip, just remove parts).
		Should be used after make_offline, since it can only minify local files.
		"""
		if not self.allow_minify:
			return
		self.notes = []

	@property
	def full_file_path(self):
		"""
		Full path to where the local file, if set, can be loaded (so no GET parameters etc).
		"""
		if self.local_path:
			assert self.resource_dir, 'cannot get file path for {0:s} since `resource_dir` is not set'.format(self)
			return join(self.resource_dir, self.archive_dir or '', self.local_path)
		return None

	@property
	def full_path(self):
		"""
		Full path including parameters to the local or remote file.
		"""
		if self.local_path:
			return self.full_file_path + self.local_params
		return self.remote_path

	@property
	def relative_path(self):
		"""
		Path relative to the document, including parameters.
		"""
		if self.local_path:
			return self.local_path + self.local_params
		return self.remote_path

	@property
	def exists(self):
		if self.remote_path:
			return True
		return exists(self.full_file_path)

	@property
	def html(self):
		raise NotImplementedError('generic resource cannot be linked from html; use a subclass')

	def copy(self, to, allow_symlink=False):
		"""
		Copy necessary files to `to` if they are local.
		"""
		self.logger.info(' {0:} {2:} for {1:s}'.format(self.__class__.__name__,
			self.group_name, id(self) % 100000), level=3)
		if self.local_path is None:
			return
		if self.processed_path is None:
			self.processed_path = self.full_file_path
		if self.copy_map:
			allow_symlink = False  # this may be too aggressive
		else:
			self.copy_map = {None: self.local_path}
		for src, dst in self.copy_map.items():
			if src:
				assert '*' not in src, '{0:}: wildcards not allowed in copy_map'.format(self)
				assert self.resource_dir is not None, 'local resources should have resource_dir specified'
				srcpth = join(self.resource_dir, self.archive_dir or '', src)
			else:
				srcpth = self.processed_path
			dstpth = join(to, dst)
			if self.logger.get_level() >= 3:
				self.logger.info('  copying {0:s} {1:s} -> {2:}'.format(self.__class__.__name__, srcpth, dstpth), level=3)
			else:
				self.logger.info(' copying {0:s} {1:}'.format(self.__class__.__name__, dstpth), level=2)
			if exists(dstpth) and getmtime(dstpth) >= getmtime(srcpth):
				self.logger.info('  {0:s} {1:s} seems unchanged'.format(self.__class__.__name__, dstpth), level=3)
			else:
				link_or_copy(src=srcpth, dst=dstpth, follow_symlinks=True, allow_linking=allow_symlink, create_dirs=True, exist_ok=True)

	def _do_process(self, func, name='res_proc'):
		if not self.allow_minify:
			return
		self.notes = []
		if self.local_path is None:
			return
		if self.processed_path is None:
			self.processed_path = self.full_file_path
		src = self.processed_path
		makedirs(self.resource_dir, exist_ok=True, mode=0o700)
		self.processed_path = join(self.compile_conf.TMP_DIR, name, self.group_name, self.local_path)
		if self.logger.get_level() >= 3:
			self.logger.info('  processing {0:s} {1:s} -> {2:}'.format(self.__class__.__name__, src, self.processed_path), level=3)
		else:
			self.logger.info(' processing {0:s} {1:}'.format(self.__class__.__name__, self.processed_path), level=2)
		link_or_copy(src=self.cache.get_or_create_file(func=partial(func, src), dependencies=(src,)),
			dst=self.processed_path, exist_ok=False, allow_overwrite=True)


class LinkedResource(Resource):
	def file_content(self):
		"""
		Get the content of a file if it is available locally (e.g. for internalizing).
		"""
		assert self.local_path, ('resource ({0:s}) must be local or have already been localized in order to get '
			'file content').format(self)
		with open(self.local_path, 'r') as fh:
			return fh.read()


class NonLinkedResource(Resource):
	def __init__(self, logger, cache, compile_conf, group_name, resource_dir=None,
			*, copy_map=None, tag_type=None, internalize=None, **kwargs):
		"""
		Check that no options are set that are irrelevant to NonLinkedResources.
		"""
		name = kwargs.get('local_path', None) or kwargs.get('remote_path', None) or \
			kwargs.get('download_archive', None)
		assert tag_type is None, ('static resource ({0:}) should not have `tag_type` ({1:})')\
			.format(name, tag_type)
		assert internalize is None, ('static resource ({0:}) should not set `internalize`').format(name)
		assert not copy_map, ('static resources ({0:}) should not have other files copied along with them so '
			'copy_map should be empty').format(name)
		super(NonLinkedResource, self).__init__(logger=logger, cache=cache, compile_conf=compile_conf,
			group_name=group_name, resource_dir=resource_dir, **kwargs)

	def file_content(self):
		raise NotImplementedError('resource `{0:s}` does not support getting file content')


class HtmlResource(NonLinkedResource):
	pass


class StyleResource(LinkedResource):
	@property
	def html(self):
		"""
		Get the html for this tag.
		"""
		tag_type = self.tag_type or 'text/css'
		if self.internalize:#todo
			return '<style rel="stylesheet" type="{1:s}" >{0:s}</style>'.format(self.file_content(), tag_type) + \
				(' <!-- file content inserted; {0:s} -->'.format('; '.join(self.notes)) if self.notes else '')
		return '<link href="{0:s}" rel="stylesheet" type="{1:s}" >'.format(self.relative_path, tag_type) + \
			(' <!-- {0:s} -->'.format('; '.join(self.notes)) if self.notes else '')

	def minify(self):
		"""
		Minimize the tag if possible (strip whitespace and things like that).
		"""
		def min_css(inpath, outpath):
			process_single_css_file(css_file_path=inpath, output_path=outpath, overwrite=False)
		return self._do_process(min_css, 'minify')


class ScriptResource(LinkedResource):
	@property
	def html(self):
		"""
		Get the html for this tag.
		"""
		tag_type = self.tag_type or 'text/javascript'
		if self.internalize:
			return '<script type="{1:s}" >{0:s}</script>'.format(self.file_content(), self.tag_type) + \
				(' <!-- file content inserted; {0:s} -->'.format('; '.join(self.notes)) if self.notes else '')
		return '<script src="{0:s}" type="{1:s}"></script>'.format(self.relative_path, tag_type) + \
			(' <!-- {0:s} -->'.format('; '.join(self.notes)) if self.notes else '')

	def minify(self):
		"""
		Minimize the tag if possible (strip whitespace and things like that).
		"""
		def min_js(inpath, outpath):
			process_single_js_file(js_file_path=inpath, output_path=outpath, overwrite=False)
		return self._do_process(min_js, 'minify')


class StaticResource(NonLinkedResource):
	pass


