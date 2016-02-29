
from copy import copy


class Configuration:
	def __init__(self, options):
		self.options = copy(options)

	def add_cmd_args(self):
		pass

	def parse_cms_args(self):
		pass


class TagHandler:
	can_contain_tags = False
	can_use_substitutions = True

	def __init__(self, config):
		self.config = config

	def __call__(self, element, **kwargs):
		raise NotImplementedError('tag {0:} has not implemented __call__ method'.format(self.__class__))

	def __str__(self):
		return self.__class__.__name__


