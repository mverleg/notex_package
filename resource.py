
from glob import glob
from os import mkdir, makedirs
from os.path import join, exists, basename, dirname, splitext
from shutil import copy2
from compiler.utils import hash_str, link_or_copy


class Resource:
	def __init__(self, package, logger, cache, compile_conf, *, local_path=None, remote_path=None,
				 allow_make_offline=True, download_archive=None, downloaded_path=None, copy_map=None):
		"""
		There are basically three options:

		1. Local files, given by local_path.
		2. Remote files, given by remote_path.
		3. Remote files to be downloaded before use, given by download_archive.

		Note that #2 may also be downloaded if allow_make_offline is True and archive is not set.
		Options #1 and #3 can't be used together (if there is already a local file, nothing will be downloaded).

		:param package: Package that this resource belongs to.
		:param local_path: The local path of the resource (wildcards should be expanded before calling Resource.__init__).
		:param remote_path: The remote path of the resource (no wildcards).
		:param allow_make_offline: If true (default), the resource can be downloaded and included in the compiled document.
		:param download_archive: If set, when making an offline version, this archive (.zip) is downloaded and deflated rather than simply downloading remote_path.
		:param downloaded_path: Determines the local path to link after downloading the archive.
		:param copy_map: A mapping from original to final file paths for either local or archive data. Can be used to copy extra files or set the location of the main archive file. If set, the main file should be included.
		"""
		self.logger = logger
		self.cache = cache
		self.compile_conf = compile_conf
		self.package = package
		self.local_path = local_path
		self.remote_path = remote_path
		self.allow_make_offline = allow_make_offline
		self.download_archive = download_archive
		self.downloaded_path = downloaded_path
		self.copy_map = copy_map or {}
		self.resource_dir = self.package.path
		self.archive_dir = None
		if not self.local_path and not self.remote_path:
			self.make_offline()
		self.notes = ['from package "{0:s}"'.format(self.package.name)]
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
		# assert hasattr(local_copy, '__iter__') and not isinstance(local_copy, str), \
		# 	'{0:}: local_copy should be a list'.format(self)
		# assert hasattr(downloaded_copy, '__iter__') and not isinstance(downloaded_copy, str), \
		# 	'{0:}: downloaded_copy should be a list'.format(self)

	def __str__(self):
		pth_str = ('"{0:s}" & "{1:s}"' if (self.local_path and self.remote_path) else '"{0:s}{1:s}"')\
			.format((self.local_path or ''), (self.remote_path or ''))
		return '{0:s} {1:s} from {2:s}'.format(self.__class__.__name__, pth_str, self.package.name)

	@property
	def content(self):
		raise NotImplementedError()

	#todo: caching?
	def make_offline(self):
		"""
		Make the resource available offline if applicable.
		"""
		if self.local_path:
			return
		if not self.allow_make_offline:
			return
		self.resource_dir = join(self.compile_conf.TMP_DIR, 'offline', self.package.name)
		makedirs(self.resource_dir, exist_ok=True, mode=0o700)
		if self.download_archive:
			self._make_offline_from_archive()
		else:
			self._make_offline_from_file()

	def _cut_params(self, pth):
		return pth.split('?', maxsplit=1)[0].split('#', maxsplit=1)[0]

	def _make_offline_from_file(self):
		self.logger.info(' making file available offline: {0:}'.format(self.remote_path), level=2)
		prefix = hash_str('{0:s}.{1:s}'.format(self.package.name, self.remote_path))
		self.local_path = '{0:.8s}_{1:s}'.format(prefix, basename(self._cut_params(self.remote_path)))
		link_or_copy(
			src=self.cache.get_or_create_file(url=self.remote_path),
			dst=join(self.resource_dir, self.local_path),
			exist_ok=True,
		)
		self.notes.append('offline version based on external file "{0:s}"'.format(self.remote_path))

	def _make_offline_from_archive(self):
		self.logger.info(' making archive available offline: {0:}'.format(self.download_archive), level=2)
		prefix = hash_str('{0:s}.{1:s}'.format(self.package.name, self.download_archive))
		self.archive_dir = '{0:.8s}_{1:s}'.format(prefix, splitext(basename(self._cut_params(self.download_archive)))[0])
		archive = self.cache.get_or_create_file(url=self.download_archive)
		dir = self.cache.get_or_create_file(rzip=archive)
		link_or_copy(dir, join(self.resource_dir, self.archive_dir), exist_ok=True)
		self.local_path = join(self.downloaded_path)

	@property
	def full_path(self):
		if self.local_path:
			return join(self.resource_dir, self.local_path)
		return self.remote_path

	@property
	def exists(self):
		if self.remote_path:
			return True
		return exists(self.full_path)

	@property
	def html(self):
		raise NotImplementedError('generic resource cannot be linked from html; use a subclass')

	def copy(self, to, allow_symlink=False):
		"""
		Copy necessary files to `to` if they are local.
		"""
		self.logger.info(' {0:} {2:} for {1:s}'.format(self.__class__.__name__, self.package.name, id(self)), level=3)
		if self.local_path:
			# print('&&', dirname(join(to, self.local_path)))
			if not self.copy_map:
				self.copy_map = {self._cut_params(self.local_path): self._cut_params(self.local_path)}
			for src, dst in self.copy_map.items():
				assert '*' not in src, '{0:}: wildcards not allowed in copy_map'.format(self)
				srcpth = join(self.resource_dir, self.archive_dir or '', src)
				dstpth = join(to, dst)
				if self.logger.get_level() >= 3:
					self.logger.info('  copying {0:s} {1:s} -> {2:}'.format(self.__class__.__name__, srcpth, dstpth), level=3)
				else:
					self.logger.info(' copying {0:s} {1:}'.format(self.__class__.__name__, dstpth), level=2)
				link_or_copy(src=srcpth, dst=dstpth, follow_symlinks=True, allow_linking=allow_symlink, create_dirs=True)


class HtmlResource(Resource):
	pass


class StyleResource(Resource):
	@property
	def html(self):
		print('style', self.local_path, self.remote_path)
		return '<link href="{0:s}" rel="stylesheet" type="text/css" > <!-- {1:s} -->'.format(
			self.local_path or self.remote_path, '; '.join(self.notes))


class ScriptResource(Resource):
	@property
	def html(self):
		print('script', self.local_path, self.remote_path)
		return '<script src="{0:s}" type="text/javascript"></script> <!-- {1:s} -->'.format(
			self.local_path or self.remote_path, '; '.join(self.notes))


class StaticResource(Resource):
	def __init__(self, package, logger, cache, compile_conf, *, copy_map=None, **kwargs):
		assert not copy_map, ('static resources ({0:}) should not have other files copied along with them so '
			'copy_map should be empty').format(self)
		super(StaticResource, self).__init__(package, logger=logger, cache=cache, compile_conf=compile_conf, **kwargs)

