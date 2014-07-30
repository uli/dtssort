import sys
import re
from logging import debug, DEBUG, basicConfig

#basicConfig(level=DEBUG)

ORDER_NAME = 1
ORDER_LABEL = 2
ORDER_ADDRESS = 3

#sort_blocks = [ORDER_ADDRESS, ORDER_LABEL, ORDER_NAME]
#sort_statements = [ORDER_NAME]
sort_blocks = []
sort_statements = []
statement_prio = 0
block_prio = 0

dts = open(sys.argv[1]).read()
dts_size = len(dts)
cursor = 0

# skips whitespace and tells us how many LF it encountered in the process
def skip_whitespace():
	global cursor
	had_newline = 0
	while cursor < dts_size and dts[cursor].isspace():
		if dts[cursor] == '\n':
			had_newline += 1
		cursor += 1
	return had_newline

def parse_comment():
	global cursor
	comment_start = cursor
	comment_end = comment_start
	cursor = comment_end
	while True:
		comment_end = dts[cursor:].find('*/') + 2 + comment_end
		cursor = comment_end
		if skip_whitespace() > 1 or what_is_next(False) not in [NEXT_GLOBAL_COMMENT, NEXT_PRE_COMMENT, NEXT_POST_COMMENT]:
			cursor = comment_end
			break
		else:
			cursor = comment_end
	#debug('comment start %d end %d: %s', comment_start, comment_end, dts[comment_start:comment_end])
	return dts[comment_start:comment_end]

NEXT_EOB = 0		# end of block
NEXT_BLOCK = 1
NEXT_STATEMENT = 2	# property assignment
NEXT_PRE_COMMENT = 3	# comment belonging to the succeeding definition
NEXT_POST_COMMENT = 4	# comment belonging to the preceding definition
NEXT_DIRECTIVE = 5	# preprocessor directive
NEXT_GLOBAL_COMMENT = 6	# standalone comment
NEXT_EOF = 7		# end of file

# identify the upcoming entity, optionally ignoring comments
def what_is_next(ignore_comment):
	global cursor
	start = cursor

	# make sure that a comment at the start of the file
	# is not misinterpreted as a post comment
	if cursor == 0:
		had_newline = 1
	else:
		had_newline = 0
	while True:
		had_newline += skip_whitespace()
		if cursor < dts_size and dts[cursor] == '/' and \
		   dts[cursor+1] == '*':
			parse_comment()
			if had_newline > 0 and skip_whitespace() > 1:
				#debug('global comment %s', dts[start:cursor])
				cursor = start
				return NEXT_GLOBAL_COMMENT
			if not ignore_comment:
				if had_newline > 0:
					#debug('next precomment %s', dts[start:cursor])
					cursor = start
					return NEXT_PRE_COMMENT
				else:
					#debug('next postcomment %s', dts[start:cursor])
					cursor = start
					return NEXT_POST_COMMENT
		else:
			break

	while cursor < dts_size:
		if dts[cursor] == '#' and dts[cursor:].startswith('#include'):
			cursor = start
			return NEXT_DIRECTIVE
		if dts[cursor] == ';':
			cursor = start
			return NEXT_STATEMENT
		elif dts[cursor] == '{':
			cursor = start
			return NEXT_BLOCK
		elif dts[cursor] == '}':
			cursor = start
			return NEXT_EOB
		else:
			cursor += 1

	cursor = start
	return NEXT_EOF

def parse_next():
	global cursor
	#debug('parse_next at',cursor)
	next = what_is_next(True)
	if next == NEXT_BLOCK:
		return Block.parse()
	elif next == NEXT_STATEMENT:
		return Statement.parse(False)
	elif next == NEXT_DIRECTIVE:
		return Statement.parse(True)
	elif next == NEXT_GLOBAL_COMMENT:
		return Comment.parse()
	elif next == NEXT_EOB:
		return None
	elif next == NEXT_EOF:
		if cursor < dts_size:
			# preserve trailing whitespace and comments
			s = Statement()
			s.text = dts[cursor:]
			s.prio = -100
			cursor = dts_size
			return s
		else:
			return None
	else:
		sys.exit('invalid next')

class Part:
	def __init__(self):
		self.prio = 0
		self.sort_list = []

class Definition(Part):
	def __init__(self):
		Part.__init__(self)
		self.name = None
		self.label = None
		self.address = -1
		self.pre_comment = ""
		self.post_comment = ""

class Statement(Definition): 
	def __init__(self):
		Definition.__init__(self)
		self.text = None
		self.prio = statement_prio
		self.sort_list = sort_statements

	def __str__(self):
		return self.pre_comment + self.text + self.post_comment

        @staticmethod
	def parse(is_directive):
	        global cursor
		s = Statement()
		text_start = cursor
		if what_is_next(False) == NEXT_PRE_COMMENT:
			s.pre_comment = parse_comment()
			text_start = cursor
		skip_whitespace()

		if is_directive: end_char = '\n'
		else: end_char = ';'

		# find the next semicolon that is neither escaped nor
		# within a comment
		text_end = cursor
		while text_end < dts_size:
			if dts[text_end] == '\\':
				text_end += 2
			elif dts[text_end:text_end+2] == '/*':
				text_end += dts[text_end:].find('*/')
			else:
				if dts[text_end] == end_char:
					text_end += 1
					break
				text_end += 1

		s.text = dts[text_start:text_end]
		cursor = text_end
		if what_is_next(False) == NEXT_POST_COMMENT:
			s.post_comment = parse_comment()
		
		if is_directive:
			s.name = s.text.split()[1].strip('<>')
		else:
			s.name = s.text.split('=')[0].strip()

		debug('statement name %s', s.name)
		debug('statement text %s',s.text)
		debug('statement precom %s',s.pre_comment)
		debug('statement postcom %s',s.post_comment)
		return s

class Comment(Part):
	def __init__(self):
		Part.__init__(self)
		self.text = None
	
	def __str__(self):
		return self.text
	
	@staticmethod
	def parse():
		global cursor
		c = Comment()
		c.text = parse_comment()
		return c

class Block(Definition):
	def __init__(self):
		Definition.__init__(self)
		self.prio = block_prio
		self.sort_list = sort_blocks
		self.prefix = None
		self.suffix = None
		self.contents = []

	def __str__(self):
		text = self.pre_comment + self.prefix
		for c in self.contents:
			text += str(c)
		text += self.suffix
		return text

        @staticmethod
	def parse():
	        global cursor
		b = Block()
		prefix_start = cursor
		if what_is_next(False) == NEXT_PRE_COMMENT:
			b.pre_comment = parse_comment()
			prefix_start = cursor

		skip_whitespace()
		if cursor >= dts_size:
			return None

		cursor += dts[cursor:].find('{') + 1
		prefix_end = cursor
		b.prefix = dts[prefix_start:prefix_end]
		debug('block prefix %s',b.prefix)
		
		while True:
			n = parse_next()
			if n != None:
				b.contents += [n]
			else:
				suffix_start = cursor
				suffix_end = dts[cursor:].find('};') + 2 \
					     + suffix_start
				b.suffix = dts[suffix_start:suffix_end]
				cursor = suffix_end
				break
		
		head = b.prefix.rstrip('{')
		if ':' in head:
			b.label = head.split(':')[0].strip()
			head = head.split(':')[1]
		if '@' in head:
			b.name, addr = head.split('@')
			try:
				b.address = int(addr, 16)
			except:
				b.address = addr.strip()
		else:
			b.name = head
		b.name = b.name.strip()

		debug('block name %s',b.name)
		debug('block label %s',b.label)
		debug('block suffix %s',b.suffix)
		debug('block precom %s',b.pre_comment)
		debug('block postcom %s',b.post_comment)
		debug('block address %s',b.address)
		
		b.contents.sort(cmp=dt_cmp)
		return b

def dt_cmp(a, b):
	if a.prio != b.prio:
		return cmp(b.prio, a.prio)
	if a.__class__ != b.__class__:
		return 0
	for i in a.sort_list:
		if i == ORDER_ADDRESS and a.address != b.address:
			return cmp(a.address, b.address)
		elif i == ORDER_NAME and a.name != b.name:
			return cmp(a.name, b.name)
		elif i == ORDER_LABEL and a.label != b.label:
			return cmp(a.label, b.label)
	return 0

tree = list()
while True:
	p = parse_next()
	if p: tree += [p]
	else: break
tree.sort(cmp=dt_cmp)

for p in tree:
	sys.stdout.write(str(p))
