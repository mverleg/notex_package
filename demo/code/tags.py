

class C():
	"""
		Ignore <c>all</c> comments. Use <c> tag to wrap them.
		The first sentence would become "Ignore  comments."
	"""
	#todo: find a good way to pass information between tags (within a package?) for a compile_2html run

	def __init__(self, keep='false'):
		if keep.lower() in ['t', 'true', 'yes', '1']:
			self.keep = True
		elif keep.lower() in ['f' ,'false', 'no', '0']:
			self.keep = False
		else:
			Exception('Unknown value "" for keep argument, try "true" or "false"'.format(keep))  #todo special exception

	def render(self, content, **options):
		#todo it would probably be better to not accept all options
		if self.keep:
			#todo: maybe filter <!-- and --> from content
			#todo: how to deal with nested tags being allowed sometimes? have to manually call render() on content?
			return '<!-- {0:s} -->'.format(content)
		return ''



