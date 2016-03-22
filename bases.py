
from copy import copy


class Configuration:
	def __init__(self, options, *, logger, cache, compile_conf, parser):
		self.options = copy(options)
		self.logger = logger
		self.cache = cache
		self.compile_conf = compile_conf
		self.parser = parser

	def add_cmd_args(self):
		pass

	def parse_cms_args(self):
		pass


class TagHandler:
	can_contain_tags = False  # tags within this one will also be handled
	can_use_substitutions = True  # substitutions are applies to children of this tag
	final_handler = False  # block other handlers registered for the same tag

	def __init__(self, config):
		self.config = config

	def __call__(self, element, **kwargs):
		raise NotImplementedError('tag {0:} has not implemented __call__ method'.format(self.__class__))

	def __str__(self):
		return self.__class__.__name__


