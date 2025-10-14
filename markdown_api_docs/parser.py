"""Provides a light-weight C++ parser.

The provided parser processes only declarations, statements and
expressions are not sparsed.

References:
- C++ reference
  https://en.cppreference.com/w/cpp/
- Working Draft. Programming Languages - C++
  https://timsong-cpp.github.io/cppwp/
"""

import functools
import collections
import contextlib
import inspect
import textwrap
from .spanstr import spanstr


class _REQUIRED(object):
  """A singleton object representing a required argument in namedtuple
  subclasses.
  """
REQUIRED = _REQUIRED()


class _UNEXPECTED(object):
  """A singleton object representing an unexpeted event in parseing C++
  that parser will report as debug messages to the user.
  """
UNEXPECTED = _UNEXPECTED()


class _TBD(object):
  """A singleton object representing a to-be-defined attribute in
  namedtuple subclasses.
  """
  def tostring(self, tab=''):
    return 'TBD'
TBD = _TBD()

class _MISSING_KEY(object):
  """A singleton object representing missing key in split cache.
  """
MISSING_KEY = _MISSING_KEY()

class ScopeBlock:
  """Scope block.

  A scope block is a set of symbols and their specifications.

  If a symbol belongs to a scope block then we say that the symbol is
  defined in this scope block.

  A symbol can be defined only in one scope block.

  A symbol is visible in its scope block and in all subblocks of the
  scope block.

  A symbol can be addressed from other scope blocks using its scope
  block name.

  A symbol can be a type name, a declarator name, or a block name.

  All scope blocks have parent scope blocks except so-called global
  scope block that parent is a Context instance.

  A scope block has a set of friend blocks (think of C++ using
  declaration) that symbols are visible in the scope block similar to
  the scope block symbols.
  """

  def __init__(self, name, parent=None):
    self.name = name
    self.parent = parent
    self.symbols = dict()  # contains pairs (name, specification)
    self.friends = dict()  # contains pairs (fullname, scope block)

  @property
  def fullname(self):
    if isinstance(self.parent, type(self)):
      return self.parent.fullname + '::' + self.name      
    return self.name

  def __repr__(self):
    return f'{type(self).__name__}(fullname={self.fullname}, symbols={list(self.symbols)})'

  def __get_block(self, name):
    if name.startswith('::'):
      fullname = name
    else:
      fullname = self.fullname + '::' + name

class Block:
  """Block is a generalization of a namespace.

  Block is used to store also class member declarations, for instance.
  """
  def __init__(self, parent, name, origin):
    self.parent = parent
    assert isinstance(name, str), name
    assert '::' not in name, name
    self.name = name
    self.origin = origin        # a specification instance that has a name
    self.entities = dict()      # contains pairs (name, entities)
    self.children = dict()      # contains pairs (block name, block)

  def tostring(self, tab=''):
    lines = [f'{tab}{self.name} {{']
    lines.append(f'{tab}  fullname = {self.fullname}')
    lines.append(f'{tab}  origin = {self.origin}')
    if self.entities:
      lines.append(f'{tab}  entities = [')
      for n, e in self.entities.items():
        lines.append(f'{tab}    `{n}`: <{type(e).__name__}>')
      lines.append(f'{tab}  ]')
    if self.children:
      lines.append(f'{tab}  children = [')
      for n, c in self.children.items():
        lines.append(c.tostring(tab=tab + '    ') + ',')
      lines.append(f'{tab}  ]')
    lines.append(f'{tab}}}')
    return '\n'.join(lines)

  def __str__(self):
    return self.tostring()
    
  @property
  def isempty(self):
    return not (self.entities or self.children)

  @property
  def fullname(self):
    if isinstance(self.parent, type(self)):
      return self.parent.fullname + '//' + self.name      
    return self.name

  @property
  def root(self):
    if isinstance(self.parent, type(self)):
      return self.parent.root
    return self

  def get_or_make_block(self, name, spec):
    if '::' in name:
      if name.startswith('::'):
        return self.root.get_or_make_block(name[2:], spec)
      n, r = name.split('::')
      if n not in self.children:
        self.children[n] = Block(self, n, spec)
      r = r.lstrip()
      return self.children[n].get_or_make_block(r, spec)
    if name not in self.children:
      self.children[name] = Block(self, name, spec)
    return self.children[name]

  def register(self, entity):
    self.parent.register_entity(self.name, entity)

  def update(self, entity):
    self.parent.update_entity(self.name, entity)

  def unregister(self):
    self.parent.unregister_entity(self.name)
    if self.isempty:
      self.parent.children.pop(self.name)

  def register_entity(self, name, entity):
    #assert name.isidentifier() or (name.startswith('~') and name[1:].isidentifier()) or name.startswith('operator'), (name,)
    if name in self.entities:
      self.entities[(name, None)] = self.entities[name]
    self.entities[name] = entity

  def update_entity(self, name, entity):
    #assert name.isidentifier() or (name.startswith('~') and name[1:].isidentifier()) or name.startswith('operator'), (name,)
    self.entities[name] = entity
    if (name, None) in self.entities:
      self.entities.pop((name, None), None)

  def unregister_entity(self, name):
    if (name, None) in self.entities:
      self.entities[name] = self.entities.pop((name, None))
    else:
      self.entities.pop(name, None)

def block_split(ctx, head, spec_with_tbd, split, line):
  """Splitter of <body> in

    <spec> = <head> <body>

  where <head> is known, `line` presumably starts with <body>, and
  `<spec>` is partly defined (its <body> member is defined as TBD).
  When <body> is succesfully parsed, return <spec> that TBD is
  replaced with <body>, and `rest` of `line`.

  As a side effect, a new block is created within the current
  ctx.block. The name of the new block will be `str(head)`. In
  addition, `spec_with_tbd` is registered in the current block under
  the name of the new block. While parsing the `body` part, the new
  block will be the current ctx.block temporarily. When succesful,
  `spec_with_tbd` will be replaced with `spec`, otherwise it will be
  removed from ctx.block.
  """
  block = ctx.get_or_make_block(head)
  block.register(spec_with_tbd)
  with ctx.block_context(block):
    body, rest = split(ctx, line)
  if body:
    name_with_tbd = None
    for n in spec_with_tbd._fields:
      if name_with_tbd is None:
        if getattr(spec_with_tbd, n) is TBD:
          name_with_tbd = n
      else:
        assert getattr(spec_with_tbd, n) is not TBD, (name_with_tbd, n)
    assert name_with_tbd is not None
    spec = spec_with_tbd._replace(**{name_with_tbd: body})
    if isinstance(body[0], (tuple, list)):
      for item in body[0]:
        n = get_entity_name(item)
        if n is not None:
          block.update_entity(n, item)
    block.update(spec)
    return spec, rest
  else:
    block.unregister()
    return None, line

class Scope:
  """Represents a set of symbols that are visible in the current scope.
  """
  def __init__(self, parent=None):
    self.parent = parent
    self.namespaces = []
    self.declarations = dict()

  def __repr__(self):
    return f'{type(self).__name__}(namespaces={self.namespaces}, declarations={self.declarations})'

  def copy(self):
    new = type(self)(parent=self)
    new.namespaces.extend(self.namespaces)
    new.declarations.update(self.declarations)
    return new

def get_entity_name(obj):
  if isinstance(obj, str) or obj is None:
    return
  i = list(obj._find(declarator_id, identifier))
  if len(i) == 0:
    return
  #assert len(i) == 1, (i, obj)
  n = i[0]
  i = list(n._find(qualified_id))
  if len(i) == 0:
    pass
  else:
    #assert len(i) == 1, (i, n)
    n = i[0].unqualified_id

  return str(n)

class Context:
  """
  Holds a set of states of a parsing process.
  """
  def __init__(self, source=None, debug=False, enable_debug_rerun=False):
    # when true, stop parsing
    self.stop = False
    self.enable_debug_rerun = enable_debug_rerun
    self.debug = debug
    # grammar path enables tracking of namedtuple instance generation
    # sequence but it is expensive when using inspect.stack
    self.make_grammar_path = debug

    self.longest_match = None

    self.raise_on_unexpected = False

    self.scope = Scope()

    # block is the target for adding declarations
    self.block = Block(self, '__GLOBAL__', source)  # root block

    self._unique_counter = 0

    self.detect_recurrence = dict()  # holds pairs (cls name, line)

    self.enable_abstract_declarator = False

    self.split_depth = 0
    
    import sys
    sys.setrecursionlimit(5000)

    self.split_cache = dict()  # holds pairs ((cls, line.span[0]), cls.split(ctx, line))

  @property
  def tab(self):
    return ' ' * self.split_depth
    
  def get_or_make_block(self, head):
    if isinstance(head, Namedtuple):
      name = get_entity_name(head)
      if name is None:
        name = str(head)
      assert name is not None, (head)
    else:
      assert 0, (head, type(head))
      name = str(head)
    return self.block.get_or_make_block(name, head)

  def namespace(self, name):  # TODO: UNUSED?
    if name is None:
      name = f'__UNIQUE_{self._unique_counter}__'
      self._unique_counter += 1
    else:
      assert isinstance(name, ns_name), name
      name = str(name[0])
    return self.block_context(self.get_or_make_block(name))

  def block_context(self, block):
    class context(contextlib.ContextDecorator):
      def __init__(self, ctx, block):
        self.ctx = ctx
        self.block = block
        self.prev_block = ctx.block
  
      def __enter__(self):
        print(f'entering {self.block.fullname} from {self.prev_block.fullname} : {self.block.origin=}')
        self.ctx.block = self.block

      def __exit__(self, exc_type, exc, exc_tb):
        print(f'leaving {self.block.fullname} to {self.prev_block.fullname} : {self.block.parent.origin=}')
        self.ctx.block = self.prev_block
    return context(self, block)

  def abstract_declarator(self, enable=True):
    class context(contextlib.ContextDecorator):
      def __init__(self, ctx, desired_state):
        self.ctx = ctx
        self.saved_state = None
        self.desired_state = desired_state
      def __enter__(self):
        assert self.saved_state is None
        self.saved_state = self.ctx.enable_abstract_declarator
        self.ctx.enable_abstract_declarator = self.desired_state
      def __exit__(self, exc_type, exc, exc_tb):
        assert self.saved_state is not None
        self.ctx.enable_abstract_declarator = self.saved_state
        self.saved_state = None
    return context(self, enable)

  def report(self):
    if self.longest_match is not None:
      result, rest = self.longest_match

      if self.make_grammar_path:
        print(f'Grammar path: {result._grammar_path}')

      if isinstance(rest, spanstr):
        parsed_indent =   '+     '
        unparsed_indent = '-     '
        parsed_code = rest.storage[:rest.span[0]]
        unparsed_code = rest.storage[rest.span[0]:]

        if 1:
          parsed_code = parsed_indent + ('\n' + parsed_indent).join(str(parsed_code).splitlines()[-10:])
          unparsed_code = unparsed_indent + ('\n' + unparsed_indent).join(str(unparsed_code).splitlines()[:5])
        else:
          parsed_code = ('\n' + parsed_indent).join(textwrap.TextWrapper(initial_indent=parsed_indent).wrap(str(parsed_code))[-10:])
          unparsed_code = ('\n' + unparsed_indent).join(textwrap.TextWrapper(initial_indent=unparsed_indent).wrap(str(unparsed_code))[:5])
        print(f'Parsed code:\n{parsed_code}')
        print(f'Unparsed code:\n{unparsed_code}')

class Namedtuple:
  """Base class for nametuple instances.
  """

  def _find(self, *types):
    """Yield instances of specified types contained in nametuple instances. 
    """
    if isinstance(self, types):
      yield self
    else:
      for k, v in self._asdict().items():
        if isinstance(v, Namedtuple):
          yield from v._find(*types)

        
def namedtuple(name, field_names=None, base=None, *, defaults=None, extra_attrs={}, split=None):
  """An enhanced namedtuple function.

  Returns a new Python type representing a C++ grammar specification.
  """
  if field_names is None:
    field_names = ['content']
    if defaults is None:
      defaults = [REQUIRED]
  field_names = [name.replace('-', '_') for name in field_names]

  def eq(self, other):
    return type(self) is type(other) and tuple(self) == tuple(other)

  def tostring_default(self, tab=''):

    def worker(obj, tab=''):
      if isinstance(obj, str):
        return repr(obj)
      elif isinstance(obj, spanstr):
        return obj.tostring(with_location=True)
      elif type(obj) is tuple:
        s = ',\n'.join([worker(item, tab=tab) for item in obj])
        if len(obj) == 1:
          s += ','
        return f'({s.lstrip()})'
      elif type(obj) is list:
        s = ',\n'.join([worker(item, tab=tab) for item in obj])
        return f'[{s.lstrip()}]'
      elif obj is None:
        return 'N/A',
      else:
        return obj.tostring(tab=tab)

    def prefix(obj):
      if hasattr(obj, '_alt_path'):
        p = '->'.join(obj._alt_path)
        if p:
          p += '->'
      else:
        p = ''
      return p

    p = prefix(self)

    if self._fields == ('content',):
      s = worker(self[0], tab=tab + '  ')
      if '\n' not in s:
        return f'{tab}{p}{type(self).__name__}({s})'
      lines = [f'{tab}{p}{type(self).__name__}(']
      s = f'{tab}{s.lstrip()};'
      lines.append(s)
      lines.append(f'{tab})')
    else:
      lines = [f'{tab}{p}{type(self).__name__}(']
      for i, n in enumerate(self._fields):
        if self[i] is None:
          continue
        s = worker(self[i], tab=tab + '  ')
        if n == type(self[i]).__name__:
          s = f'{tab}{s.lstrip()};'
        else:
          s = f'{tab}{n}: {s.lstrip()};'
        lines.append(s)
      lines.append(f'{tab})')

    return '\n'.join(lines)

  def repr_default(self):
    data = [f'{k}=`{v}`' for k, v in self._asdict().items() if v is not None]
    return f'{type(self).__name__}({", ".join(data)})'

  def str_default(self):
    fmt = getattr(self, 'format', None)

    if self._fields == ('content',):
      if isinstance(self.content, list):
        return ', '.join(map(str, self.content))
      elif type(self.content) is tuple:
        return ' '.join(map(str, self.content))
      if fmt is None:
        fmt = '{0}'

    if fmt is not None:
      lst = []
      for i in range(len(self._fields)):
        if self[i] is None:
          s = ''
        else:
          s = str(self[i])
        lst.append(s)
        if not s:
          fmt = fmt.replace(f'{{{i}}} ', '').replace(f' {{{i}}}', '').replace(f'{{{i}}}', '')
      return fmt.format(*lst)
    return ' '.join([str(v) for k, v in self._asdict().items() if v is not None])

  def alternatives_default(cls):
    return None

  def split_keywords_default(cls):
    return None

  def postprocess_default(cls, ctx, item, rest):
    return item, rest

  def split_default(cls, ctx, line, *args, **kwargs):
    # default implementation for alternatives and specified split_keywords
    alternatives = cls.alternatives()
    if alternatives is not None:
      for alt in alternatives:
        r = alt.split(ctx, line)
        if r is NotImplemented:
          print(f'{alt.__name__}.split(ctx, `{line.splitlines()[0]}`) <- NOT IMPLEMENTED, SKIPPING')
          continue
        if r is None:
          continue
        assert type(r) is tuple, type(r)
        result, rest = r
        if result is not None:
          if not hasattr(result, '_alt_path'):
            result._alt_path = ()
          result._alt_path += (cls.__name__,)
          return result, rest  # splitter already does postprocessing
      return
    keywords = cls.split_keywords()
    if keywords is not None:
      w, rest = word.split(ctx, line)
      if w and w in keywords:
        return cls(w), rest
      return
    return NotImplemented

  def update_default(self, ctx):
    pass

  def alt_name(self):
    p = getattr(self, '_alt_path', ()) + (type(self).__name__,)
    return '-'.join(p)

  if base is not None:
    split = splitter(base.split)
    bases = (collections.namedtuple(name, field_names, defaults=defaults), Namedtuple, base)
  else:
    split = splitter(split_default if split is None else split)
    bases = (collections.namedtuple(name, field_names, defaults=defaults), Namedtuple)
  return type(name, bases,
              dict(__eq__=eq,
                   __repr__=repr_default, __str__=str_default,
                   tostring=tostring_default,
                   update=update_default,
                   alternatives=classmethod(alternatives_default),
                   split_keywords=classmethod(split_keywords_default),
                   postprocess=classmethod(postprocess_default),
                   skip_debug=classmethod(lambda cls: False),
                   _grammar_path=None,
                   alt_name=property(alt_name),
                   split=split,
                   **extra_attrs))

#################################################################
#       Grammar definition utilities
#################################################################

def _compute_grammar_path(result):
    plst = []
    plst.append(type(result).__name__)
    for fr in inspect.stack():
      c = fr.frame.f_locals.get('cls')
      if c is not None:
        if not plst or plst[-1] != c.__name__:
          plst.append(c.__name__)    
    return '->'.join(reversed(plst))

def _resolve_name_and_specs(args):
  if isinstance(args[0], str):
    name = args[0]
    specs = args[1:]
  else:
    specs = args
    name = '_'.join((f'lambda_{id(a)}' if a.__name__ == '<lambda>' else a.__name__) for a in args)
  return name, specs

def pair_or_item(name, separators, item, recursive=True):
  """
  item
  spec separator item
  """
  separators = (separators,) if isinstance(separators, str) else separators

  def pair_or_item_split(cls, ctx, line, left=None):
    if left is None:
      left, rest = cls._item.split(ctx, line)
    else:
      rest = line
    if left:
      for sep in cls._separators:
        if isinstance(sep, str):
          if startswith_token(rest, sep):
            s = rest[:len(sep)]
            rest_ = rest[len(sep):].lstrip()
          else:
            continue
        else:
          s, rest_ = sep.split(ctx, rest)
          if not s:
            continue
        right, rest_ = cls._item.split(ctx, rest_)
        if right:
          item = cls(left, s, right)
          if recursive:
            r = pair_or_item_split(cls, ctx, rest_, left=item)
            if r is not None:
              return r
          return item, rest_              
      return left, rest

  return namedtuple(name, ['left', 'separator', 'right'],
                    split=pair_or_item_split,
                    extra_attrs=dict(_item=item, _separators=separators))

def item_sequence(name, item):
  """
  item
  spec item
  """

  def item_sequence_split(cls, ctx, line):
    i, rest = cls._item.split(ctx, line)
    if i:
      j, rest = item_sequence_split(cls, ctx, rest)
      if j:
        return cls((i,) + j.content), rest
      return cls((i,)), rest
    return None, line

  return namedtuple(name, ['content'],
                    split=item_sequence_split,
                    extra_attrs=dict(_item=item))



def item_optional_dots(item):
  """
  spec ...?
  """
  name = item.__name__
  def item_optional_dots_split(cls, ctx, line):
    i, rest = cls._item.split(ctx, line)
    if i:
      if rest.startswith('...'):
        return cls(i), rest[3:].lstrip()
      return i, rest
  return namedtuple(name, ['item'],
                    split=item_optional_dots_split,
                    extra_attrs=dict(_item=item))

def item_optional_suffix(item, suffix):
  """
  item suffix?
  """
  name = item.__name__
  def item_optional_suffix_split(cls, ctx, line):
    i, rest = cls._item.split(ctx, line)
    if i:
      t, rest = cls._suffix.split(ctx, rest)
      if t:
        return cls(i, t), rest
      return i, rest
  return namedtuple(name, ['item', 'suffix'],
                    split=item_optional_suffix_split,
                    extra_attrs=dict(_item=item, _suffix=suffix))

def item_optional_prefix(item, prefix):
  """
  prefix? item
  """
  name = f'optional_{prefix.__name__}_{item.__name__}'
  def item_optional_prefix_split(cls, ctx, line):
    t, rest = cls._prefix.split(ctx, line)
    i, rest = cls._item.split(ctx, rest)
    if i:
      if t:
        return cls(t, i), rest
      return i, rest
  return namedtuple(name, ['prefix', 'item'],
                    split=item_optional_prefix_split,
                    extra_attrs=dict(_item=item, _prefix=prefix))

def maxalternative(*args):
  """
  spec1
  spec2
  ...

  that returns smallest remaining part.
  """
  name, specs = _resolve_name_and_specs(args)

  def maxalternative_split(cls, ctx, line):
    specs = cls._grammar_specs
    rest = line

    max_item = None
    min_rest = line
    
    for spec in specs:
      if callable(spec) and spec.__name__ == '<lambda>':
        spec = spec()
      if type(spec) is not tuple:
        spec = spec,
      for s in spec:
        item, rest = s.split(ctx, line)
        if item:
          if len(rest) < len(min_rest):
            min_rest = rest
            max_item = item

    return max_item, min_rest

  return namedtuple(name, ['unused'],
                    split=maxalternative_split,
                    extra_attrs=dict(_grammar_specs=specs))

def _spec_iter(specs):
  for spec in specs:
    if callable(spec) and spec.__name__ == '<lambda>':
      spec = spec()
    if type(spec) is not tuple:
      spec = spec,
    for s in spec:
      yield s

def alternatives(*args, **kwargs):
  """
  spec1
  spec2
  ...

  wrap=True means that the result will be wrapped with the parent
  class.
  """
  wrap = kwargs.pop('wrap', False)
  assert not kwargs, kwargs
  name, specs = _resolve_name_and_specs(args)

  def alternatives_split(cls, ctx, line, wrap=wrap):
    specs = cls._grammar_specs
    rest = line
    for spec in specs:
      if callable(spec) and spec.__name__ == '<lambda>':
        spec = spec()
      if type(spec) is not tuple:
        spec = spec,
      for s in spec:
        item, rest = s.split(ctx, line)
        if item:
          if wrap:
            item = cls(item)

          return item, rest

    #assert 0, line
  return namedtuple(name, ['wrapped'] if wrap else ['unused'],
                    split=alternatives_split,
                    extra_attrs=dict(_grammar_specs=specs))

def sequence(*args):
  """
  spec1 spec2 ...
  """
  name, specs = _resolve_name_and_specs(args)

  def sequence_split(cls, ctx, line):
    rest = line
    lst = []
    for i, spec in enumerate(_spec_iter(cls._grammar_specs)):
      item, rest = spec.split(ctx, rest)
      if item:
        lst.append(item)
      else:
        return
    return cls(tuple(lst)), rest
      
  return namedtuple(name, ['seq'],
                    split=sequence_split,
                    extra_attrs=dict(_grammar_specs=specs))

def _require_and_drop_semicolon(split):
  def require_and_drop_semicolon(cls, ctx, line, *args, **kwargs):
    result = split(cls, ctx, line, *args, **kwargs)
    if type(result) is tuple and len(result) == 2:
      item, rest = result
      if item:
        if rest.startswith(';'):
          return item, rest[1:].lstrip()
        return
    return result
  return require_and_drop_semicolon

def _require_and_drop_colon(split):
  def require_and_drop_colon(cls, ctx, line, *args, **kwargs):
    result = split(cls, ctx, line, *args, **kwargs)
    if type(result) is tuple and len(result) == 2:
      item, rest = result
      if item:
        if startswith_token(rest, ':'):
          return item, rest[1:].lstrip()
        return
    return result
  return require_and_drop_colon

def _split_depth(mth):

  def wrapper_split_depth(cls, ctx, line, *args, **kwargs):
    verbose = cls.__name__ not in {'word'}
    if verbose:
      print(f'>{ctx.tab}<{cls.__name__}({line[:20].tostring()})')
    ctx.split_depth += 1
    r = mth(cls, ctx, line, *args, **kwargs)
    ctx.split_depth -= 1
    if verbose:
      if r is not None and r[0] is not None:
        print(f'!{ctx.tab}{cls.__name__}>item=`{r[0]}` rest={r[1][:20].tostring() if isinstance(r[1], spanstr) else r[1][:20]}')
        assert isinstance(r[1], spanstr), r[1]
      else:
        print(f' {ctx.tab}{cls.__name__}>')
    return r

  return wrapper_split_depth

def _split_cache(mth):

  def wrapper_split_cache(cls, ctx, line, *args, **kwargs):
    if args or kwargs:
      return mth(cls, ctx, line, *args, **kwargs)

    if isinstance(line, spanstr):
      key = cls.__name__, line.span
    elif isinstance(line, str):
      key = cls.__name__, line
    else:
      assert 0, type(line)  # unreachable

    r = ctx.split_cache.get(key, MISSING_KEY)

    if r is not MISSING_KEY:
      return r

    r = mth(cls, ctx, line, *args, **kwargs)

    if type(r) is tuple and r[0] is not None:
      # cache only successful split results
      ctx.split_cache[key] = r
    return r

  return wrapper_split_cache
    
def splitter(mth):
  """Decorator of a classmethod split that a grammar specification type
  may define.

  The class method split is an entry point to parsing a string
  containing C++ grammar specifications.

  When a class method split is applied to a string `line`, it may
  return

  - a pair `(grammar_specification, rest)` where grammar
    specification is constructed by consuming the content of the head
    part of the `line` string and `rest` is the tail part of the line.
  - a pair `(None, line)` when the head of the line does not match
    the grammar specification
  - `None`, equivalent to `(None, line)`
  - `UNEXPECTED`, equivalent to `(None, line)` but with a warning
    message about unexpected mismatch.
  - `NotImplemented`, equivalent to `(None, line)` but with a warning
    message about unimplemented grammar specification support.
  - Anything else will raise a ValueError about unexpected return value.

  """

  @_split_cache
  #@_split_depth
  def wrapper(cls, ctx, line, *args, **kwargs):
    # sanity checks:
    assert line is not None

    if ctx.stop:
      return None, line

    last_line = ctx.detect_recurrence.get(cls.__name__)
    if last_line is not None and last_line == line:
      # print(f'stopped recurrance from {cls.__name__}')
      return None, line

    ctx.detect_recurrence[cls.__name__] = line
    r = mth(cls, ctx, line, *args, **kwargs)
    ctx.detect_recurrence.pop(cls.__name__, None)

    if r is UNEXPECTED:
      print(f'unexpected mismatch when calling {cls.__name__}.split:')
      if ctx.enable_debug_rerun:
        ctx_debug = Context(debug=True)
        mth(cls, ctx_debug, line, *args, **kwargs)
        ctx_debug.report()

      if ctx.raise_on_unexpected:
        raise RuntimeError('unexpected mismatch')
      return (None, line)
    
    if r is None:
      return (None, line)

    if r is NotImplemented:
      short_line = str(line)
      if len(short_line) > 25:
        short_line = short_line[:15] + '...' + short_line[-5:]
      print(f'not implemented match when calling {cls.__name__}.split({repr(short_line)}):')
      if ctx.enable_debug_rerun:
        ctx_debug = Context(debug=True)
        mth(cls, ctx_debug, line, *args, **kwargs)
        ctx_debug.report()

      return (None, line)

    if not (type(r) is tuple and len(r) == 2):
      raise ValueError(f'{cls.__name__}.split is expected to return None, UNEXPECTED, NotImplemented, or 2-tuple, for {type(r).__name__}')
  
    result, rest = r

    if ctx.make_grammar_path and (hasattr(result, '_grammar_path') or isinstance(result, spanstr)):
      result._grammar_path = _compute_grammar_path(result)

    if isinstance(rest, spanstr) and result is not None:
      assert not rest.startswith(' ') or cls in {
        basic_c_char, basic_s_char, c_char, s_char,
        simple_escape_sequence_char,
        simple_escape_sequence, numeric_escape_sequence, conditional_escape_sequence,
        escape_sequence, universal_character_name,
        octal_escape_sequence, hexadecimal_escape_sequence,
      }, cls
      if ctx.longest_match is None or rest.span[0] > ctx.longest_match[1].span[0]:
        ctx.longest_match = result, rest
        ctx.last_lineno = rest.storage[:rest.span[1]].count('\n')

    # postprocessing may undo parsing
    r = cls.postprocess(ctx, result, rest)
    if r is None:
      return None, line
    return r

  #functools.update_wrapper(wrapper, mth)
  return classmethod(wrapper)

def startswith_token(line, token):
  """
preprocessing-operator: one of
#        ##       %:       %:%:
operator-or-punctuator: one of
{        }        [        ]        (        )
<:       :>       <%       %>       ;        :        ...
?        ::       .        .*       ->       ->*      ~
!        +        -        *        /        %        ^        &        |
=        +=       -=       *=       /=       %=       ^=       &=       |=
==       !=       <        >        <=       >=       <=>      &&       ||
<<       >>       <<=      >>=      ++       --       ,
and      or       xor      not      bitand   bitor    compl
and_eq   or_eq    xor_eq   not_eq
  """
  if token == ':':
    return line.startswith(':') and not (line.startswith('::') or line.startswith(':>'))
  elif token == '<:':
    return line.startswith('<:') and not (line.startswith('<::'))
  elif token == '<':
    return line.startswith('<') and not (line.startswith('<<') or startswith_token(line, '<:') or line.startswith('<=') or line.startswith('<%'))
  elif token == '<<':
    return line.startswith('<<') and not (line.startswith('<<='))
  elif token == '>>':
    return line.startswith('>>') and not (line.startswith('>>='))
  elif token == '->':
    return line.startswith('->') and not (line.startswith('->*'))
  elif token == '>':
    return line.startswith('>') and not (line.startswith('>>') or line.startswith('>='))
  elif token == '.':
    return line.startswith('.') and not (line.startswith('..') or line.startswith('.*'))
  elif token == '%':
    return line.startswith('%') and not (line.startswith('%>') or line.startswith('%=') or line.startswith('%:'))
  elif token == '%:':
    return line.startswith('%:') and not (line.startswith('%:%:'))
  elif token == '=':
    return line.startswith('=') and not (line.startswith('=='))
  elif token == '/':
    return line.startswith('/') and not (line.startswith('/='))
  elif token == '^':
    return line.startswith('^') and not (line.startswith('^='))
  elif token == '*':
    return line.startswith('*') and not (line.startswith('*='))
  elif token == '+':
    return line.startswith('+') and not (line.startswith('+=') or line.startswith('++'))
  elif token == '-':
    return line.startswith('-') and not (line.startswith('-=') or line.startswith('--'))
  elif token == '!':
    return line.startswith('!') and not (line.startswith('!='))
  elif token == '&':
    return line.startswith('&') and not (line.startswith('&&') or line.startswith('&='))
  elif token == '|':
    return line.startswith('|') and not (line.startswith('||') or line.startswith('|='))
  elif token == '#':
    return line.startswith('#') and not (line.startswith('##'))
  return line.startswith(token)


def startswith_identifier(s):
  # TODO: XID_Continue
  return s and (s[0].isalnum() or s[0] == '_')


def startswith_identifier0(s):
  # TODO: XID_Start
  return s and (s[0].isalpha() or s[0] == '_')


# todo: deprecate split_until
def split_until(line, marks, require_mark=True, match_all=True, keep_mark=False, keep_mark_rest=False, stop_marks='', pmap=None):
  """Return a pair (left, right) such that

    line == left + <any combination of marks> + right
  """
  stack = []
  if pmap is None:
    if '>' in marks or ',' in marks:
      pmap = {'<': '>', '(': ')', '{': '}', '[': ']'}
    else:
      pmap = {'(': ')', '{': '}', '[': ']'}

  if match_all:
    m = len(marks)
    match = lambda i: str(line[i:i+m]) == marks
    stop_match = lambda i: str(line[i:i+m]) == stop_marks
  else:
    m = 1
    match = lambda i: str(line[i]) in marks
    stop_match = lambda i: str(line[i]) in stop_marks

  m0 = m if keep_mark else 0
  m1 = 0 if keep_mark_rest else m

  for i in range(len(line) - m + 1):
    if line[i] in pmap:
      if line[i:i+2] == '<<' or line[i-1:i+1] == '<<':
        continue
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack and stop_match(i):
      return line[:i+m0-1].rstrip(), line[i+m1-1:].lstrip()
    elif not stack and match(i):
      return line[:i+m0].rstrip(), line[i+m1:].lstrip()

  return (None, line) if require_mark else (line, '')

def process_rest_lstrip_comma(rest):
  if rest.startswith(','):
    rest = rest[1:].lstrip()
  return rest

def process_rest_lstrip_scope_operator(rest):
  if startswith_token(rest, '::'):
    rest = rest[2:]
  return rest

# deprecate consume_to_lits?
def consume_to_list(ctx, split, line, max_nof_items=None, validate_item=None, process_rest=None):
  """Return a pair (left, right) such that

    line == "".join(left) + right

  where left is obtained by appling split to line until first mismatch.
  """
  if validate_item is None:
    validate_item = lambda lst, p, rest: True
  if process_rest is None:
    process_rest = lambda rest: rest
  lst, rest = [], line
  valid_rest = line
  while rest and (max_nof_items is None or len(lst) < max_nof_items):
    p, rest2 = split(ctx, rest)
    if p is not None and validate_item(lst, p, rest2):
      assert p, (p, bool(p))
      lst.append(p)
      valid_rest = rest2
      rest = process_rest(rest2)
    else:
      rest = valid_rest
      break
  if lst:
    return lst, rest
  return None, line

#############################################################
# Grammar specifications
#############################################################


class word(namedtuple('word')):
  """Matches
  [a-zA-Z_][a-zA-Z_0-9]*
  """
  @classmethod
  def skip_debug(cls): return True

  @splitter
  def split(cls, ctx, line, strip=True, require=None):
    """Return a pair (word, rest) such that
      line = word + rest
    where word is maximal.
    """
    # TODO: use re for faster processing
    if line and startswith_identifier0(line):
      word, rest = line, line[len(line):]
      for i in range(1, len(line)):
        if not startswith_identifier(line[i]):
          word = line[:i]
          rest = line[i:]
          break
      if strip:
        rest = rest.lstrip()
      if isinstance(require, str):
        if word != require:
          return
      elif isinstance(require, (tuple, list)):
        if word not in require:
          return
      elif require is None:
        pass
      else:
        assert 0, type(require)  # unreachable     
      return word, rest


# A set of all C++ keywords
keywords = {"alignas", "alignof", "and", "and_eq", "asm",
            "atomic_cancel", "atomic_commit", "atomic_noexcept",
            "auto", "bitand", "bitor", "bool", "break", "case",
            "catch", "char", "char8_t", "char16_t", "char32_t",
            "class", "compl", "concept", "const", "consteval",
            "constexpr", "constinit", "const_cast", "continue",
            "co_await", "co_return", "co_yield", "decltype",
            "default", "delete", "do", "double", "dynamic_cast",
            "else", "enum", "explicit", "export", "extern", "false",
            "float", "for", "friend", "goto", "if", "inline", "int",
            "long", "mutable", "namespace", "new", "noexcept", "not",
            "not_eq", "nullptr", "operator", "or", "or_eq", "private",
            "protected", "public", "reflexpr", "register",
            "reinterpret_cast", "requires", "return", "short",
            "signed", "sizeof", "static", "static_assert",
            "static_cast", "struct", "switch", "synchronized",
            "template", "this", "thread_local", "throw", "true",
            "try", "typedef", "typeid", "typename", "union",
            "unsigned", "using", "virtual", "void", "volatile",
            "wchar_t", "while", "xor", "xor_eq"}

extra_keywords = {'module', 'import'}

# A list of all C++ operators
operators = [">>=", "<<=", "<=>", "->*", "==", "!=", "<=", ">=",
             "&&", "||", "++", "--", "->", "+=", "-=", "*=", "/=",
             "%=", "^=", "&=", "|=", "<<", ">>", ",", "+", "-", "*",
             "/", "%", "^", "&", "|", "~", "!", "=", "<", ">", "()",
             "[]", "new", "delete", "co_wait"]

# deprecate anyidentifier?
class anyidentifier(namedtuple('anyidentifier')):
  """Matches a word as identifier, both keyword and non-keyword.
  """
  @splitter
  def split(cls, ctx, line, strip=True):
    w, rest = word.split(ctx, line, strip=strip)
    if w: # and w not in keywords:
      assert w, (w, rest)
      return cls(w), rest

class identifier(namedtuple('identifier')):
  """Matches a word that is not a C++ keyword.
  """
  @splitter
  def split(cls, ctx, line, strip=True):
    w, rest = word.split(ctx, line, strip=strip)
    if w and w not in keywords:
      assert w, (w, rest)
      return cls(w), rest

class overloaded_operator_name(namedtuple('overloaded_operator_name')):
  """Matches
  `operator` C++-operator
  """
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='operator')
    if w:
      for op in operators:
        if rest.startswith(op):
            if op.isalpha():
              if not startswith_identifier0(rest[len(op):]):
                return cls(f'operator {op}'), rest[len(op):].lstrip()
            else:
              return cls(f'operator{op}'), rest[len(op):].lstrip()

class user_defined_conversation_function_name(namedtuple('user_defined_conversation_function_name')):
  """Matches
  `operator` C++-type-conversion
  """
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='operator')
    if w:
      typ, rest = keyword_type_specifier.split(ctx, rest)
      if typ:
        return cls(f'operator {typ}'), rest

class user_defined_literal_operator_name(namedtuple('user_defined_literal_operator_name')):
  """Matches
  `operator` C++-literal-operator
  """
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='operator')
    if w:
      if rest.startswith('""'):
        name, rest = identifier.split(ctx, rest[2:].lstrip())
        if name:
          return cls(f'operator ""{name}'), rest  # TODO: use spanstr storage

class name_without_template_arguments(namedtuple('name_without_template_arguments')):
  @classmethod
  def alternatives(cls):
    return (
        overloaded_operator_name,
        user_defined_conversation_function_name,
        user_defined_literal_operator_name,
        identifier)

class name(namedtuple('name')):
  """Matches
  identifier ( `<` template-argument-list `>` )?
  C++-operator ( `<` template-argument-list `>` )?
  """
  @splitter
  def split(cls, ctx, line):
    n, rest = name_without_template_arguments.split(ctx, line)
    if n:
      if startswith_token(rest, '<'):
        raw, rest2 = split_until(rest[1:].lstrip(), '>')
        if raw:
          # https://timsong-cpp.github.io/cppwp/temp.names#4
          args, rest3 = template_argument_list.split(ctx, raw)
          if args is not None:
            assert rest3 == '', rest3
            return template_name_with_argument_list(n, args), rest2
      else:
        return cls(n), rest

    
class decltype_specifier(namedtuple('decltype_specifier')):
  """Matches
  decltype ( expression )
  """
  format = 'decltype({0})'

  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='decltype')
    if w and startswith_token(rest, '('):
      e, rest = expression.split(ctx, rest[1:].lstrip())
      if e and startswith_token(rest, ')'):
        return cls(e), rest[1:].lstrip()


class pack_indexing_specifier(namedtuple('pack_indexing_specifier', ['typedef_name', 'constant_expression'])):
  """
  typedef-name ... [ constant-expression ]
  """
  format = '{0}...[ {1} ]'

  @classmethod
  def continue_split(cls, ctx, typedef_name, rest):
    if typedef_name and rest.startswith('...'):
      rest = rest[3:].lstrip()
      if rest.startswith('['):
        e, rest = constant_expression.split(ctx, rest[1:].lstrip())
        if e and startswith_token(rest, ']'):
          return cls(typedef_name, e), rest[1:].lstrip()

  # TODO:
  @splitter
  def split(cls, ctx, line):
    if '...' not in line:
      return
    return NotImplemented


class unqualified_name(namedtuple('unqualified_name')):
  """Matches
  decltype-specifier
  name
  """
  @classmethod
  def alternatives(cls):
    return (decltype_specifier,
            # pack_indexing_specifier,  # it is handled by identifier_expression
            name)

class unqualified_tilde_name(namedtuple('unqualified_tilde_name')):
  """Matches
  `~` unqualified-name
  """
  format = '~{0}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('~'):
      n, rest = unqualified_name.split(ctx, line[1:].lstrip())
      if n:
        return cls(n), rest
    else:
      return unqualified_name.split(ctx, line)

class template_disambiguator(namedtuple('template_disambiguator')):
  # template_disambiguator can be used only after operators `::`, `.`,
  # and `->` as a replacement of name.
  format = 'template {0}'

  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='template')
    if t:
      n, rest = unqualified_tilde_name.split(ctx, rest)
      if n:
        return cls(n), rest
    else:
      return name.split(ctx, line)

class qualified_name_with_template_disambiguator(namedtuple('qualified_name_with_template_disambiguator')):
  @classmethod
  def alternatives(cls):
    return (template_disambiguator, unqualified_tilde_name)

class identifier_expression(namedtuple('identifier_expression', ['scope', 'name'], defaults=[REQUIRED, REQUIRED])):
  # by definition, name in identifier_expression is a qualified identifier
  def __str__(self):
    s = '::'.join(map(str, self.scope))
    return f'{s}::{self.name}'

  @splitter
  def split(cls, ctx, line, level=0, scope_name=None):
    if scope_name is None:
      if level==0:
        scope_name = unqualified_tilde_name
      else:
        scope_name = qualified_name_with_template_disambiguator
    if line.startswith('::'):
      n, rest = cls.split(ctx, line[2:].lstrip(), level=level+1)
      if isinstance(n, cls):
        return cls([''] + [s_ for s_ in n.scope if s_], n.name), rest
      elif n:
        return cls([''], n), rest
    else:
      n, rest = scope_name.split(ctx, line)
      if n:
        if startswith_token(rest, '::'):
          n_, rest = cls.split(ctx, rest, level=level+1)
          if isinstance(n_, cls):
            scope = [n] + n_.scope
            return cls([n] + [s_ for s_ in n_.scope if s_], n_.name), rest
          elif n_:
            return cls([n], n_), rest
        elif rest.startswith('...['):
          return pack_indexing_specifier.continue_split(ctx, n, rest)
        else:
          return n, rest

class type_id_or_constant_expression(maxalternative(lambda: (type_id, constant_expression))):
  """
  constant-expression
  type-id
  """

class template_argument(alternatives('template_argument', type_id_or_constant_expression,  lambda: (id_expression, braced_init_list))):
  """
  constant-expression
  type-id
  id-expression
  braced-init-list
  """
  @classmethod
  def postprocess(cls, ctx, item, rest):
    assert not startswith_token(rest, '<'), rest
    if startswith_token(rest, '('):   # TODO: check if this is still needed
      a, rest2 = abstract_declarator.split(ctx, rest)
    return item, rest
  
class template_argument_dots(namedtuple('template_argument_dots')):
  """
  template-argument ...?
  """
  format = '{0} ...'
  @splitter
  def split(cls, ctx, line):
    c, rest = template_argument.split(ctx, line)
    if c:
      if rest.startswith('...'):
        return cls(c), rest[3:].lstrip()
      return c, rest

class template_argument_list(pair_or_item('template_argument_list', ',', template_argument_dots)):
  """
  template-argument ...?
  template-argument-list , template-argument ...?
  """

##########################################################
#                                                        #
#                  Declarators                           #
#                                                        #
##########################################################

class alignment_specifier(namedtuple('alignment_specifier', ['type_id_or_constant_expression', 'dots'])):
  """
  alignas ( type-id ...? )
  alignas ( constant-expression ...? )
  """
  format = 'alignas({0} {1})'
  @splitter
  def split(cls, ctx, line):
    a, rest = word.split(ctx, line, require='alignas')
    if a and startswith_token(rest, '('):
      raw, rest = split_until(rest[1:].lstrip(), ')')
      i, rest2 = type_id.split(ctx, raw)
      if not i:
        i, rest2 = constant_expression.split(ctx, raw)
      if i:
        if rest2.startswith('...'):
          dots = rest2[:3]
          rest2 = rest2[3:].lstrip()
        else:
          dots = None
        assert rest2 == '', rest2
        return cls(i, dots), rest

class attribute_namespace(namedtuple('attribute_namespace')):
  """
  identifier
  """
  @classmethod
  def alternatives(cls):
    return (identifier,)

class attribute_using_prefix(namedtuple('attribute_using_prefix')):
  """
  using attribute-namespace :
  """
  format = 'using {0} :'
  @splitter
  def split(cls, ctx, line):
    using, rest = word.split(ctx, line, require='using')
    if using:
      ns, rest = attribute_namespace.split(ctx, rest)
      if ns and startswith_token(rest, ':'):
        return cls(ns), rest[1:].lstrip()

class attribute_specifier_with_square_brackets(namedtuple('attribute_specifier_with_square_brackets', ['attribute_using_prefix', 'attribute_list'])):
  format = '[[ {0} {1} ]]'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('[['):
      raw, rest = split_until(line[2:].lstrip(), ']]')
      p, rest2 = attribute_using_prefix.split(ctx, raw)
      lst, rest2 = attribute_list.split(ctx, rest2)
      assert rest2 == '', rest2
      return cls(p, lst), rest

class attribute_scoped_token(namedtuple('attribute_scoped_token', ['attribute_namespace', 'identifier'])):
  """
  attribute-namespace :: identifier
  """
  format = '{0} :: {1}'
  @splitter
  def split(cls, ctx, line):
    ns, rest =  attribute_namespace.split(ctx, line)
    if ns and startswith_token(rest, '::'):
      i, rest = identifier.split(ctx, rest[2:].lstrip())
      if i:
        return cls(ns, i), rest

class attribute_token(namedtuple('attribute_token')):
  """
  identifier
  attribute-scoped-token
  """
  @classmethod
  def alternatives(cls):
    return (attribute_scoped_token, identifier,)

class balanced_token_round(namedtuple('balanced_token_round')):
  format = '({0})'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      raw, rest = split_until(rest[1:].lstrip(), ')')
      if raw == '':
        return cls(None), rest
      seq, rest2 = balanced_token_seq.split(ctx, raw)
      if seq:
        assert rest2 == '', rest2
        return cls(seq), rest

class balanced_token_square(namedtuple('balanced_token_square')):
  format = '[{0}]'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('['):
      raw, rest = split_until(rest[1:].lstrip(), ']')
      if raw == '':
        return cls(None), rest
      seq, rest2 = balanced_token_seq.split(ctx, raw)
      if seq:
        assert rest2 == '', rest2
        return cls(seq), rest

class balanced_token_curly(namedtuple('balanced_token_curly')):
  format = '{{{0}}}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('{'):
      raw, rest = split_until(rest[1:].lstrip(), '}')
      if raw == '':
        return cls(None), rest
      seq, rest2 = balanced_token_seq.split(ctx, raw)
      if seq:
        assert rest2 == '', rest2
        return cls(seq), rest

class keyword(namedtuple('keyword')):
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line)
    if w and (w in keywords or w in extra_keywords):
      return cls(w), rest

class simple_escape_sequence_char(namedtuple('simple_escape_sequence_char')):
  r"""
  one of
  '  "  ?  \ a  b  f  n  r  t  v
  """
  @splitter
  def split(cls, ctx, line):
    c = str(line[0])
    if c == "'" or c in r'"?\abfntv':
      return cls(line[0]), line[1:]

class simple_escape_sequence(namedtuple('simple_escape_sequence')):
  r"""
  \ simple-escape-sequence-char
  """
  format = '\\{0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('\\'):
      c, rest = simple_escape_sequence_char.split(ctx, line[1:])
      if c:
        return cls(c), rest

class octal_escape_sequence(namedtuple('octal_escape_sequence')):
  r"""
  \ octal-digit
  \ octal-digit octal-digit
  \ octal-digit octal-digit octal-digit
  \o{ simple-octal-digit-sequence }
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith('\\'):
      assert 0, line[:30]  # not implemented

class hexadecimal_escape_sequence(namedtuple('hexadecimal_escape_sequence')):
  r"""
  \x simple-hexadecimal-digit-sequence
  \x{ simple-hexadecimal-digit-sequence }
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith('\\'):
      assert 0, line[:30]  # not implemented

class numeric_escape_sequence(alternatives('numeric_escape_sequence',
                                           octal_escape_sequence,
                                           hexadecimal_escape_sequence)):
  """
  octal-escape-sequence
  hexadecimal-escape-sequence
  """

class conditional_escape_sequence_char(namedtuple('conditional_escape_sequence_char')):
  """
  any member of the basic character set that is not an octal-digit, a simple-escape-sequence-char, or the characters N, o, u, U, or x
  """
  @splitter
  def split(cls, ctx, line):
    assert 0, line[:30]  # not implemented

class conditional_escape_sequence(namedtuple('conditional_escape_sequence')):
  r"""
  \ conditional-escape-sequence-char
  """
  format = '\\{0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('\\'):
      c, rest = conditional_escape_sequence_char.split(ctx, line[1:])
      if c:
        return cls(c), rest

class escape_sequence(alternatives('escape_sequence',
                      simple_escape_sequence,
                      numeric_escape_sequence,
                      conditional_escape_sequence)):
  """
  simple-escape-sequence
  numeric-escape-sequence
  conditional-escape-sequence
  """

class basic_c_char(namedtuple('basic_c_char')):
  """
  any member of the translation character set except the U+0027 apostrophe,
  U+005c reverse solidus, or new-line character
  """
  @splitter
  def split(cls, ctx, line):
    c = str(line[0])
    if c == '\n' or c == '\\' or c == "'":
      return
    return cls(line[0]), line[1:]

class named_universal_character(namedtuple('named_universal_character')):
  r"""
  \N{ n-char-sequence }
  """
  format = r'\N{{{0}}}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith(r'\N{'):
      c, rest = n_char_sequence.split(ctx, line[3:])
      if c and startswith_token(rest, '}'):
        return cls(c), rest[1:].lstrip()

class universal_character_name():
  r"""
  \u hex-quad
  \U hex-quad hex-quad
  \u{ simple-hexadecimal-digit-sequence }
  named-universal-character
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith("\\"):
      assert 0, line[:30]  # not implemented

class c_char(alternatives('c_char', basic_c_char, escape_sequence, universal_character_name)):
  """
  basic-c-char
  escape-sequence
  universal-character-name
  """
    
class c_char_sequence(item_sequence('c_char_sequence', c_char)):
  """
  c-char
  c-char-sequence c-char
  """    
  
class character_literal(namedtuple('character_literal', ['encoding_prefix', 'c_char_sequence'])):
  """
  encoding-prefix? ' c-char-sequence '
  """
  format = "{0} '{1}'"
  @splitter
  def split(cls, ctx, line):
    e, rest = encoding_prefix.split(ctx, line)
    if rest.startswith("'"):
      seq, rest = c_char_sequence.split(ctx, rest[1:])
      if seq and rest.startswith("'"):
        return cls(e, seq), rest[1:].lstrip()
      
class digit_sequence(namedtuple('digit_sequence')):
  """
  digit
  digit-sequence '? digit
  """
  @splitter
  def split(cls, ctx, line):
    i = None
    for i_ in range(len(line)):
      if line[i_].isdigit() or (i_ and line[i_].startswith("'")):
        i = i_ + 1
        continue
      break
    if i is not None:
      return cls(line[:i]), line[i:].lstrip()

class fractional_constant(namedtuple('fractional_constant')):
  """
  digit-sequence? . digit-sequence
  digit-sequence .
  """
  @splitter
  def split(cls, ctx, line):
    s, rest = digit_sequence.split(ctx, line)
    if s:
      if startswith_token(rest, '.'):
        p = rest[0]
        rest = rest[1:].lstrip()
        t, rest = digit_sequence.split(ctx, rest)
        if t:
          return cls(str(s.content) + str(p) + str(t.content)), rest
        return cls(str(s.content) + str(p)), rest
    elif startswith_token(rest, '.'):
      p = rest[0]
      t, rest = digit_sequence.split(ctx, rest[1:].lstrip())
      if t:
        return cls(str(p) + str(t.content)), rest

class hexadecimal_fractional_constant(namedtuple('hexadecimal_fractional_constant')):
  """
  hexadecimal-digit-sequence? . hexadecimal-digit-sequence
  hexadecimal-digit-sequence .
  """
  @splitter
  def split(cls, ctx, line):
    s, rest = hexadecimal_digit_sequence.split(ctx, line)
    if s:
      if startswith_token(rest, '.'):
        p = rest[0]
        rest = rest[1:].lstrip()
        t, rest = hexadecimal_digit_sequence.split(ctx, rest)
        if t:
          return cls(str(s.content) + str(p) + str(t.content)), rest
        return cls(str(s.content) + str(p)), rest
    elif startswith_token(rest, '.'):
      p = rest[0]
      t, rest = hexadecimal_digit_sequence.split(ctx, rest[1:].lstrip())
      if t:
        return cls(str(p) + str(t.content)), rest

class exponent_part(namedtuple('exponent_part')):
  """
  e sign? digit-sequence
  E sign? digit-sequence
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith('e') or line.startswith('E'):
      e = line[0]
      rest = line[1:].lstrip()
      if startswith_token(rest, '+') or startswith_token(rest, '-'):
        s = rest[0]
        rest = rest[1:].lstrip()
      else:
        s = rest[:0]
      d, rest = digit_sequence.split(ctx, rest)
      if d:
        return cls(str(e) + str(s) + str(d.content)), rest

class binary_exponent_part(namedtuple('binary_exponent_part')):
  """
  p sign? digit-sequence
  P sign? digit-sequence
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith('p') or line.startswith('P'):
      e = line[0]
      rest = line[1:].lstrip()
      if startswith_token(rest, '+') or startswith_token(rest, '-'):
        s = rest[0]
        rest = rest[1:].lstrip()
      else:
        s = rest[:0]
      d, rest = digit_sequence.split(ctx, rest)
      if d:
        return cls(str(e) + str(s) + str(d.content)), rest

class floating_point_suffix(namedtuple('floating_point_suffix')):
  """
  floating-point-suffix: one of
  """
  symbols = sorted('f l f16 f32 f64 f128 bf16 F L F16 F32 F64 F128 BF16'.split(), reverse=True, key=len)

  @splitter
  def split(cls, ctx, line):
    for s in cls.symbols:
      if line.startswith(s):
        return cls(line[:len(s)]), line[len(s):].lstrip()

class decimal_floating_point_plain_literal(namedtuple('decimal_floating_point_plain_literal', ['fractional_part', 'exponent_part'])):
  """
  fractional-constant exponent-part?

  digit-sequence exponent-part
  """
  format = '{0}{1}'
  @splitter
  def split(cls, ctx, line):
    f, rest = fractional_constant.split(ctx, line)
    if f:
      e, rest = exponent_part.split(ctx, rest)
      return cls(f, e), rest
    else:
      f, rest = digit_sequence.split(ctx, line)
      if f:
        e, rest = exponent_part.split(ctx, rest)
        if e:
          return cls(f, e), rest

class decimal_floating_point_literal(namedtuple('decimal_floating_point_literal', ['literal', 'floating_point_suffix'])):
  """
  fractional-constant exponent-part? floating-point-suffix?

  digit-sequence exponent-part floating-point-suffix?
  """
  format = '{0}{1}'
  @splitter
  def split(cls, ctx, line):
    l, rest = decimal_floating_point_plain_literal.split(ctx, line)
    if l:
      s, rest = floating_point_suffix.split(ctx, rest)
      return cls(l, s), rest
  
class hexadecimal_prefix(namedtuple('hexadecimal_prefix')):
  """
  0x 0X
  """
  @splitter
  def split(cls, ctx, line):
    if line.startswith('0x') or line.startswith('0X'):
      return cls(line[:2]), line[2:]

class hexadecimal_digit_sequence(namedtuple('hexadecimal_digit_sequence')):
  """
  hexadecimal-digit
  hexadecimal-digit-sequence '? hexadecimal-digit
  """

  @splitter
  def split(cls, ctx, line):
    i = None
    for i_ in range(len(line)):
      if (i_ and line[i_].startswith("'")) or str(line[i_]) in 'abcdefABCDEF0123456789':
        i = i_ + 1
        continue
      break
    if i is not None:
      return cls(line[:i]), line[i:].lstrip()

class hexadecimal_floating_point_plain_literal(namedtuple('hexadecimal_floating_point_plain_literal', ['hexadecimal-prefix', 'hexadecimal-fractional-part', 'binary-exponent-part'])):
  """
  hexadecimal-prefix hexadecimal-fractional-constant binary-exponent-part
  hexadecimal-prefix hexadecimal-digit-sequence      binary-exponent-part
  """
  @splitter
  def split(cls, ctx, line):
    p, rest = hexadecimal_prefix.split(ctx, line)
    if p:
      for hcls in [hexadecimal_fractional_constant, hexadecimal_digit_sequence]:
        f, rest = hcls.split(ctx, rest)
        if f:
          e, rest = binary_exponent_part.split(ctx, rest)
          if e:
            return cls(p, f, e)

class hexadecimal_floating_point_literal(namedtuple('hexadecimal_floating_point_literal')):
  """
  hexadecimal-prefix hexadecimal-fractional-constant binary-exponent-part floating-point-suffix?
  hexadecimal-prefix hexadecimal-digit-sequence      binary-exponent-part floating-point-suffix?
  """
  @splitter
  def split(cls, ctx, line):
    l, rest = hexadecimal_floating_point_plain_literal.split(ctx, line)
    if l:
      s, rest = floating_point_suffix.split(ctx, rest)
      return cls(l, s), rest

class floating_point_literal(alternatives('floating_point_literal',
                                          decimal_floating_point_literal,
                                          hexadecimal_floating_point_literal)):
  """
  decimal-floating-point-literal
  hexadecimal-floating-point-literal
  """

class base_literal:
  # this will be decorated with splitter and turned to classmethod
  def split(cls, ctx, line):
    for p in cls.prefixes:
      if line.startswith(p):
        i = len(p)
        if cls.required_digits and (i >= len(line) or str(line[i]) not in cls.required_digits):
          continue
        while i < len(line) and str(line[i]) in cls.digits:
          i += 1
        return cls(line[:i]), line[i:].lstrip()

class binary_literal(namedtuple('binary_literal', base=base_literal,
                                extra_attrs=dict(prefixes=['0b', '0B'],
                                                 required_digits='01',
                                                 digits="01'"))):
  """
  0b binary-digit
  0B binary-digit
  binary-literal '? binary-digit

  binary-digit: one of
  0  1
  """

class octal_literal(namedtuple('octal_literal', base=base_literal,
                               extra_attrs=dict(prefixes=['0'],
                                                required_digits=None,
                                                digits="01234567'"))):
  """
  0
  octal-literal '? octal-digit

  octal-digit: one of
  0  1  2  3  4  5  6  7
  """

class decimal_literal(namedtuple('decimal_literal', base=base_literal,
                               extra_attrs=dict(prefixes=[''],
                                                required_digits='123456789',
                                                digits="0123456789'"))):
  """
  nonzero-digit
  decimal-literal '? digit
  """

class hexadecimal_literal(namedtuple('hexadecimal_literal', base=base_literal,
                               extra_attrs=dict(prefixes=['0x', '0X'],
                                                required_digits='0123456789abcdefABCDEF',
                                                digits="0123456789abcdefABCDEF'"))):
  """
  hexadecimal-prefix hexadecimal-digit-sequence

  hexadecimal-prefix: one of
  0x  0X

  hexadecimal-digit-sequence:
    hexadecimal-digit
    hexadecimal-digit-sequence '? hexadecimal-digit

  hexadecimal-digit: one of
  0 1 2 3 4 5 6 7 8 9
  a b c d e f
  A B C D E F
  """

class integer_suffix(namedtuple('integer_suffix')):
  """
  unsigned-suffix long-suffix?
  unsigned-suffix long-long-suffix?
  unsigned-suffix size-suffix?
  long-suffix unsigned-suffix?
  long-long-suffix unsigned-suffix?
  size-suffix unsigned-suffix?

  unsigned-suffix: one of
  u U
  long-suffix: one of
  l L
  long-long-suffix: one of
  ll LL
  size-suffix: one of
  z  Z
  """
  @classmethod
  def split_keywords(cls):
    return (
      'llu', 'LLu', 'llU', 'LLU',
      'ull', 'Ull', 'uLL', 'ULL',
      'ul', 'Ul', 'uL', 'UL',
      'uz', 'Uz', 'uZ', 'UZ',
      'lu', 'Lu', 'lU', 'LU',
      'zu', 'Zu', 'zU', 'ZU',
      'll', 'LL',
      'u', 'U',
      'l', 'L',
      'z', 'Z',
    )

  
class integer_literal(namedtuple('integer_literal', ['literal', 'integer_suffix'])):
  """
  binary-literal integer-suffix?
  octal-literal integer-suffix?
  decimal-literal integer-suffix?
  hexadecimal-literal integer-suffix?
  """
  @splitter
  def split(cls, ctx, line):
    for lcls in [binary_literal, hexadecimal_literal, octal_literal, decimal_literal]:
      i, rest = lcls.split(ctx, line)
      if i:
        s, rest = integer_suffix.split(ctx, rest)
        return cls(i, s), rest

class boolean_literal(namedtuple('boolean_literal')):
  """
  false
  true
  """
  @classmethod
  def split_keywords(cls):
    return ('false', 'true')

class pointer_literal(namedtuple('pointer_literal')):
  """
  nullptr
  """
  @classmethod
  def split_keywords(cls):
    return ('nullptr',)

class ud_suffix(sequence('ud_suffix', identifier)):
  """
  identifier
  """

class user_defined_integer_literal(namedtuple('user_defined_integer_literal', ['literal', 'ud_suffix'])):
  """
  decimal-literal ud-suffix
  octal-literal ud-suffix
  hexadecimal-literal ud-suffix
  binary-literal ud-suffix
  """
  @splitter
  def split(cls, ctx, line):
    for lcls in [binary_literal, hexadecimal_literal, octal_literal, decimal_literal]:
      i, rest = lcls.split(ctx, line)
      if i:
        s, rest = ud_suffix.split(ctx, rest)
        if s:
          return cls(i, s), rest

class user_defined_floating_point_literal(namedtuple('user_defined_floating_point_literal', ['literal', 'ud_suffix'])):
  """
  fractional-constant exponent-part? ud-suffix
  digit-sequence exponent-part ud-suffix
  hexadecimal-prefix hexadecimal-fractional-constant binary-exponent-part ud-suffix
  hexadecimal-prefix hexadecimal-digit-sequence binary-exponent-part ud-suffix
  """
  format = '{0}{1}'
  @splitter
  def split(cls, ctx, line):
    l, rest = decimal_floating_point_plain_literal.split(ctx, line)
    if not l:
      l, rest = hexadecimal_floating_point_plain_literal.split(ctx, line)
    if l:
      s, rest = ud_suffix.split(ctx, rest)
      if s:
        return cls(l, s), rest

class user_defined_string_literal(namedtuple('user_defined_string_literal', ['string_literal', 'ud_suffix'])):
  """
  string-literal ud-suffix
  """
  format = '{0}{1}'
  @splitter
  def split(cls, ctx, line):
    l, rest = string_literal.split(ctx, line)
    if l:
      s, rest = ud_suffix.split(ctx, line)
      if s:
        return cls(l, s), rest

class user_defined_character_literal(namedtuple('user_defined_character_literal', ['character-literal', 'ud-suffix'])):
  """
  character-literal ud-suffix
  """
  format = '{0}{1}'
  @splitter
  def split(cls, ctx, line):
    l, rest = character_literal.split(ctx, line)
    if l:
      s, rest = ud_suffix.split(ctx, line)
      if s:
        return cls(l, s), rest

class user_defined_literal(alternatives('user_defined_literal',
                                        user_defined_integer_literal,
                                        user_defined_floating_point_literal,
                                        user_defined_string_literal,
                                        user_defined_character_literal)):
  """
  user-defined-integer-literal
  user-defined-floating-point-literal
  user-defined-string-literal
  user-defined-character-literal
  """

class literal(namedtuple('literal')):
  """
  integer-literal
  character-literal
  floating-point-literal
  string-literal
  boolean-literal
  pointer-literal
  user-defined-literal
  """
  @classmethod
  def alternatives(cls):
    return (
      character_literal,
      floating_point_literal,
      integer_literal,
      string_literal,
      boolean_literal,
      pointer_literal,
      user_defined_literal,
      )

class preprocessing_operator(namedtuple('preprocessing_operator')):
  """
  preprocessing-operator: one of     #        ##       %:       %:%:
  """
  @splitter
  def split(cls, ctx, line):
    for op in ('%:%:', '%:', '##', '#'):
      if line.startswith(op):
        return cls(line[:len(op)]), line[len(op):].lstrip()

class operator_or_punctuator(namedtuple('operator_or_punctuator')):
  """
  operator-or-punctuator: one of
  """
  symbols = sorted('''
{        }        [        ]        (        )
<:       :>       <%       %>       ;        :        ...
?        ::       .        .*       ->       ->*      ~
!        +        -        *        /        %        ^        &        |
=        +=       -=       *=       /=       %=       ^=       &=       |=
==       !=       <        >        <=       >=       <=>      &&       ||
<<       >>       <<=      >>=      ++       --       ,'''.strip().split(), reverse=True, key=len)

  @splitter
  def split(cls, ctx, line):
    for op in cls.symbols:
      if line.startswith(op):
        return cls(line[:len(op)]), line[len(op):].lstrip()
    w, rest = word.split(ctx, line)
    if w in {
        'and', 'or', 'xor', 'not', 'bitand', 'bitor', 'compl', 'and_eq', 'or_eq', 'xor_eq', 'not_eq'
    }:
      return cls(w), rest

class operator_or_punctuator(alternatives('operator_or_punctuator',
                                          preprocessing_operator,
                                          operator_or_punctuator)):
  """
    preprocessing-operator
    operator-or-punctuator
  """

class token(namedtuple('token')):
  """
  identifier
  keyword
  literal
  operator-or-punctuator
  """
  @classmethod
  def alternatives(cls):
    return (
      keyword,
      literal,
      operator_or_punctuator,
      identifier)

class balanced_token(namedtuple('balanced_token')):
  """
  ( balanced-token-seq? )
  [ balanced-token-seq? ]
  { balanced-token-seq? }
  any token other than a parenthesis, a bracket, or a brace
  """
  @classmethod
  def alternatives(cls):
    return (balanced_token_round, balanced_token_square, balanced_token_curly, token)


class balanced_token_seq(namedtuple('balanced_token_seq')):
  """
  balanced-token
  balanced-token-seq balanced-token
  """
  @splitter
  def split(cls, ctx, line):
    if not line:
      return
    t, rest = balanced_token.split(ctx, line)
    if t:
      if rest:
        seq, rest = cls.split(ctx, rest)
        if seq:
          return cls((t,)+seq.content), rest
      return cls((t,)), rest

class attribute_argument_clause(namedtuple('attribute_argument_clause')):
  """
  ( balanced-token-seq? )
  """
  format = '( {0} )'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      raw, rest = split_until(line[1:].lstrip(), ')')
      if raw == '':
        s = None
      else:
        s, rest2 = balanced_token_seq.split(ctx, raw)
        if s:
          assert rest2 == '', rest2
      return cls(s), rest

class attribute(namedtuple('attribute', ['attribute_token', 'attribute_argument_clause'])):
  """
  attribute-token attribute-argument-clause?
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    if not line:
      return
    t, rest = attribute_token.split(ctx, line)
    if t:
      a, rest = attribute_argument_clause.split(ctx, rest)
      return cls(t, a), rest

    
class attribute_with_dots(namedtuple('attribute_with_dots')):
  format = '{0} ...'
  @splitter
  def split(cls, ctx, line):
    assert 0 # unreachable

class attribute_list(namedtuple('attribute_list')):
  """
  attribute?
  attribute-list , attribute?
  attribute ...
  attribute-list , attribute ...
  """
  @splitter
  def split(cls, ctx, line):
    if line == '':
      return cls(()), line

    a, rest = attribute.split(ctx, line)
    if a:
      if rest.startswith('...'):
        dots = rest[:3]
        rest = rest[3:].lstrip()
        a = attribute_with_dots(a)

      if rest.startswith(','):
        rest = rest[1:].lstrip()
        lst, rest = cls.split(ctx, rest)
        if lst:
          return cls((a,) + lst.content), rest
      return cls((a,)), rest


class attribute_specifier(namedtuple('attribute_specifier')):
  """
  [ [ attribute-using-prefix? attribute-list ] ]
  alignment-specifier
  """
  @classmethod
  def alternatives(cls):
    return (attribute_specifier_with_square_brackets,
            alignment_specifier)
  
class attribute_specifier_seq(namedtuple('attribute_specifier_seq')):
  """
  attribute-specifier-seq? attribute-specifier
  """
  @splitter
  def split(cls, ctx, line):
    if not line:
      return
    a, rest = attribute_specifier.split(ctx, line)
    if a:
      if rest:
        lst, rest = cls.split(ctx, rest)
      else:
        lst = None
      if lst:
        return cls((a,) + lst.content), rest
      return cls((a,)), rest

class parameter_pack_declarator(namedtuple('parameter_pack_declarator', ['identifier', 'attr'])):
  format = '...{0} {1}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('...'):
      i, rest = identifier.split(ctx, line[len('...'):].lstrip())
      if i:
        attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
        return cls(i, attr_seq), rest

class identifier_declarator(namedtuple('identifier_declarator', ['identifier', 'attr_seq'])):
  format = '{0} {1}'

  @splitter
  def split(cls, ctx, line):
    i, rest = identifier_expression.split(ctx, line)
    if i:
      attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
      return cls(i, attr_seq), rest

class cv_qualifier(namedtuple('cv_qualifier')):
  @classmethod
  def split_keywords(cls):
    return ('volatile', 'const')

class cv_qualifier_seq(namedtuple('cv_qualifiler_seq')):
  @splitter
  def split(cls, ctx, line):
    q, rest = cv_qualifier.split(ctx, line)
    if q:
      s, rest = cls.split(ctx, rest)
      if s:
        return cls((q,) + s[0]), rest
      return cls((q,)), rest
  

class pointer_declarator(namedtuple('pointer_declarator', ['attr', 'cv', 'declarator'])):
  format = '* {0} {1} {2}'

  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '*'):
      attr_seq, rest = attribute_specifier_seq.split(ctx, line[1:].lstrip())
      cv, rest = cv_qualifier.split(ctx, rest)
      decl, rest = declarator.split(ctx, rest)
      if decl:
        return cls(attr_seq, cv, decl), rest


class lvalue_reference_declarator(namedtuple('lvalue_reference_declarator', ['attr', 'declarator'])):
  format = '& {0} {1}'

  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '&'):
      attr_seq, rest = attribute_specifier_seq.split(ctx, line[1:].lstrip())
      decl, rest = declarator.split(ctx, rest)
      if decl:
        return cls(attr_seq, decl), rest

class rvalue_reference_declarator(namedtuple('rvalue_reference_declarator', ['attr', 'declarator'])):
  format = '&& {0} {1}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('&&'):
      attr_seq, rest = attribute_specifier_seq.split(ctx, line[2:].lstrip())
      decl, rest = declarator.split(ctx, rest)
      if decl:
        return cls(attr_seq, decl), rest

class namespace_name(namedtuple('namespace_name')):
  """
  identifier
  namespace-alias
    identifier   # from `namespace identifier = qualified-namespace-specifier ;` statement
  """
  format = '{0}'
  @splitter
  def split(cls, ctx, line):
    i, rest = identifier.split(ctx, line)
    if i:
      # TODO: ensure that i is a namespace name or namespace alias.
      return i, rest

class nested_name_specifier(namedtuple('nested_name_specifier')):
  """
  ::
  type-name ::
  namespace-name ::
  computed-type-specifier ::
  nested-name-specifier identifier ::
  nested-name-specifier template? simple-template-id ::

  https://timsong-cpp.github.io/cppwp/expr.prim.id.qual#nt:nested-name-specifier
  """
  def __str__(self):
    lst = []
    for c in map(str, self[0]):
      if lst and lst[-1] == 'template':
        lst[-1] += ' ' + c
      else:
        lst.append(c)
    return '::'.join(lst) + '::'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('::'):
      return cls(('',)), line[2:].lstrip()
    else:
      for scls in [computed_type_specifier, namespace_name, type_name]:
        n, rest2 = scls.split(ctx, line)
        if n and rest2.startswith('::'):
          return cls((n,)), rest2[2:].lstrip()

  @classmethod
  def postprocess(cls, ctx, item, rest):

    for scls in [template_simple_template_id, identifier]:
      i, rest2 = scls.split(ctx, rest)
      if i and rest2.startswith('::'):
        return cls.postprocess(ctx, cls(item.content + (i,)), rest2[2:].lstrip())

    return item, rest

class pointer_to_member_declarator(namedtuple('pointer_to_member_declarator', ['nested_name_specifier', 'attr_seq', 'cv', 'declarator'])):
  format = '{0}::* {1} {2} {3}'

  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_specifier.split(ctx, line)
    if spec and startswith_token(rest, '*'):
      attr_seq, rest = attribute_specifier_seq.split(ctx, rest[1:].lstrip())
      cv, rest = cv_qualifier.split(ctx, rest)
      decl, rest = declarator.split(ctx, rest)
      if decl:
        return cls(spec, attr_seq, cv, decl), rest

class constexpr(namedtuple('constexpr')):
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='constexpr')
    if w:
      return cls(w), rest

class consteval(namedtuple('consteval')):
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='consteval')
    if w:
      return cls(w), rest

class dynamic_exception_specification(namedtuple('dynamic_exception_specification')):
  format = 'throw({0})'

  @splitter
  def split(cls, ctx, line):
    k, rest = word.split(ctx, line, require='throw')
    if k and startswith_token(rest, '('):
      raw, rest = split_until(rest[1:].lstrip(), ')')
      if raw is not None:
        if raw:
          # TODO: parse type-id-list when needed
          print(f'{cls.__name__}.split(ctx, {line.splitlines()[0]})  <- NOT IMPLEMENTED')
        return cls(raw), rest

class noexcept_specifier(namedtuple('noexcept_specifier')):
  format = 'noexcept({0})'

  @splitter
  def split(cls, ctx, line):
    k, rest = word.split(ctx, line, require='noexcept')
    if k:
      if startswith_token(rest, '('):
        raw, rest = split_until(rest[1:].lstrip(), ')')
        if raw is not None:
          if raw:
            print(f'{cls.__name__}.split(ctx, {line.splitlines()[0]})  <- NOT IMPLEMENTED')
          return cls(raw), rest
      else:
        return cls(''), rest

class exception_specification(namedtuple('exception_specification')):
  @classmethod
  def alternatives(cls):
    return (dynamic_exception_specification, noexcept_specifier)

class parameter_declaration(namedtuple('parameter_declaration', ['attribute_specifier_seq', 'this', 'decl_specifier_seq', 'declarator', 'initializer_clause'])):
  """
  attribute-specifier-seq? this? decl-specifier-seq declarator
  attribute-specifier-seq?       decl-specifier-seq declarator = initializer-clause
  attribute-specifier-seq? this? decl-specifier-seq abstract-declarator?
  attribute-specifier-seq?       decl-specifier-seq abstract-declarator? = initializer-clause
  """
  @property
  def format(self):
    if self.initializer_clause:
      return '{0} {1} {2} {3} = {4}'
    return '{0} {1} {2} {3}'

  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    this, rest = word.split(ctx, rest, require='this')
    seq, rest = decl_specifier_seq.split(ctx, rest)
    if seq:
      # abstract and non-abstract declarators can be mixed within
      # parameter declaration list. We try non-abstract declarator first:
      decl, rest = declarator.split(ctx, rest)
      if not decl:# and ctx.enable_abstract_declarator:
        decl, rest = abstract_declarator.split(ctx, rest)        

      i = None
      if ctx.enable_abstract_declarator or decl:
        if startswith_token(rest, '='):
          i, rest = initializer_clause.split(ctx, rest[1:].lstrip())
      return cls(a, this, seq, decl, i), rest

    decl, rest = declarator.split(ctx, rest)

class parameter_list(namedtuple('parameter_list')):
  # must_match_all = True
  @splitter
  def split(cls, ctx, line):
    if line == '':
      return cls([]), ''

    lst, rest = consume_to_list(ctx, parameter_declaration.split, line, process_rest=process_rest_lstrip_comma)
    if lst is not None:
      return cls(lst), rest

class function_declarator(namedtuple('function_declarator', ['declarator', 'parameter_list', 'cv', 'ref', 'exc', 'attr_seq'])):

  format = '{0}({1}) {2} {3} {4} {5}'

  @splitter
  def split(cls, ctx, line, head=None):
    assert head is not None
    return cls.continue_split(ctx, head, line)

  @classmethod
  def continue_split(cls, ctx, declarator, rest):
    if declarator and startswith_token(rest, '('):
      raw, rest = split_until(rest[1:].lstrip(), ')')
      if raw is not None:
        param_lst, rest2 = parameter_list.split(ctx, raw)
        if param_lst:
          cv, rest = cv_qualifier.split(ctx, rest)
          ref = None
          if startswith_token(rest, '&&'):
            ref = rest[:2]
            rest = rest[2:].lstrip()
          elif startswith_token(rest, '&'):
            ref = rest[:1]
            rest = rest[1:].lstrip()
          exc, rest = exception_specification.split(ctx, rest)
          attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
          return cls(declarator, param_lst, cv, ref, exc, attr_seq), rest

class declarator_with_parenthesis(namedtuple('declarator_with_parenthesis')):
  """
  ( declarator )
  """
  format = '({0})'

  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      decl, rest = declarator.split(ctx, line[1:].lstrip())
      if decl and startswith_token(rest, ')'):
        return cls(decl), rest[1:].lstrip()

class constructor_declarator(namedtuple('constructor_declarator', ['class_name', 'parameter_list', 'except_', 'attr_seq'])):
  """
  class-name ( parameter-list ﻿(optional) ) except ﻿(optional) attr ﻿(optional)
  """
  format = '{0}( {1} ) {2} {3}'

  @splitter
  def split(cls, ctx, line):
    n, rest = class_name.split(ctx, line)
    if n:
      if startswith_token(rest, '('):
        raw, rest = split_until(rest, ')')
        lst = None
        if raw is not None:
          lst, rest2 = parameter_list.split(ctx, raw)
        exc, rest = except_.split(ctx, rest)
        attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
        return cls(n, lst, exc, attr_seq), rest

class ptr_operator(namedtuple('ptr_operator', ['nested_name_specifier', 'operator', 'attribute_specifier_seq', 'cv_qualifier_seq'])):
  """
  * attribute-specifier-seq? cv-qualifier-seq?
  & attribute-specifier-seq?
  && attribute-specifier-seq?
  nested-name-specifier * attribute-specifier-seq? cv-qualifier-seq?

  https://timsong-cpp.github.io/cppwp/dcl.decl.general#nt:ptr-operator
  """
  @property
  def format(self):
    if self[0] is not None:
      return '{0} {1} {2} {3}'
    return '{1} {2} {3}'

  @splitter
  def split(cls, ctx, line):
    n, rest = nested_name_specifier.split(ctx, line)
    if n:
      if startswith_token(rest, '*'):
        rest = rest[1:].lstrip()
        a, rest = attribute_specifier_seq.split(ctx, rest)
        cv, rest = cv_qualifier_seq.split(ctx, rest)
        return cls(n, '*', a, cv), rest
    else:
      for op in ['&&', '&', '*']:
        if rest.startswith(op):
          rest = rest[len(op):].lstrip()
          a, rest = attribute_specifier_seq.split(ctx, rest)
          if op == '*':
            cv, rest = cv_qualifier_seq.split(ctx, rest)
          else:
            cv = None
          return cls(None, op, a, cv), rest
  
class ptr_operator_declarator(namedtuple('ptr_operator_declarator', ['ptr_operator', 'ptr_declarator'])):
  """
  ptr-operator ptr-declarator
  ptr-operator ptr-abstract-declarator?
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    o, rest = ptr_operator.split(ctx, line)
    if o:
      decl, rest = ptr_declarator.split(ctx, rest)
      if decl or ctx.enable_abstract_declarator:
        return cls(o, decl), rest

      
class noptr_declarator_id(namedtuple('noptr_declarator_id', ['declarator_id', 'attribute_specifier_seq'])):
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    i, rest = declarator_id.split(ctx, line)
    if i:
      # assert not startswith_token(rest, '::'), rest
      a, rest = attribute_specifier_seq.split(ctx, rest)
      return cls(i, a), rest

class noptr_declarator_parameters(namedtuple('noptr_declarator_parameters', ['noptr_declarator', 'parameters_and_qualifiers'])):
  """
  noptr-declarator parameters-and-qualifiers
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line, decl=None):
    if decl is None:
      decl, rest = noptr_declarator.split(ctx, line)
    else:
      rest = line
    if decl:
      p, rest = parameters_and_qualifiers.split(ctx, rest)
      if p:
        return cls(decl, p), rest

  
class noptr_declarator_array(namedtuple('noptr_declarator_array', ['noptr_declarator', 'constant_expression', 'attribute_specifier_seq'])):
  format = '{0} [ {1} ] {2}'

  @splitter
  def split(cls, ctx, line, decl=None):
    if decl is None:
      decl, rest = noptr_declarator.split(ctx, line)
    else:
      rest = line
    if decl and startswith_token(rest, '['):
      raw, rest = split_until(rest[1:].lstrip(), ']')
      if raw == '':
        e = None
      else:
        e, rest2 = constant_expression.split(ctx, raw)
        if e:
          assert rest2 == '', rest2
      a, rest = attribute_specifier_seq.split(ctx, rest)
      return cls(decl, e, a), rest

class noptr_declarator_parenthesis(namedtuple('noptr_declarator_parenthesis')):
  format = '( {0} )'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      d, rest = ptr_declarator.split(ctx, line[1:].lstrip())
      if d and startswith_token(rest, ')'):
        return cls(d), rest[1:].lstrip()

class pack_index_expression(namedtuple('pack_index_expression', ['id_expression', 'constant_expression'])):
  """
  id-expression ... [ constant-expression ]
  https://timsong-cpp.github.io/cppwp/expr.prim.pack.index#nt:pack-index-expression
  """
  format = '{0} ...[{1}]'
  @splitter
  def split(cls, ctx, line):
    i, rest = id_expression.split(ctx, line)
    if i and rest.startswith('...'):
      rest = rest[3:].lstrip()
      if startswith_token(rest, '['):
        raw, rest = split_until(rest[1:].lstrip(), ']')
        if raw == '':
          return cls(i, None), rest
        e, rest2 = constant_expression.split(ctx, raw)
        if e:
          assert rest2 == '', rest2
          return cls(i, e), rest

      
class id_expression(namedtuple('id_expression')):
  """
  unqualified-id
  qualified-id
  pack-index-expression

  https://timsong-cpp.github.io/cppwp/expr.prim.id.general#nt:id-expression
  """
  @classmethod
  def alternatives(cls):
    return (
      qualified_id,
      unqualified_id,
      pack_index_expression,
    )

  @classmethod
  def postprocess(cls, ctx, item, rest):
    #assert not startswith_token(rest, '::'), rest
    return item, rest
  
class declarator_id(namedtuple('declarator_id', ['dots', 'id_expression'])):
  """
  ...? id-expression
  https://timsong-cpp.github.io/cppwp/dcl.decl.general#nt:declarator-id
  """
  @property
  def format(self):
    if self[0]: return '... {1}'
    return '{1}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('...'):
      dots = line[:3]
      rest = line[3:].lstrip()
    else:
      dots = None
      rest = line
    e, rest = id_expression.split(ctx, rest)
    if e:
      # assert not startswith_token(rest, '::'), rest
      return cls(dots, e), rest

class declarator_id_with_optional_attribute_specifier_seq(item_optional_suffix(declarator_id, attribute_specifier_seq)):
  """
  declarator-id attribute-specifier-seq?
  """
    
class noptr_declarator(namedtuple('noptr_declarator')):
  """
  declarator-id attribute-specifier-seq?
  noptr-declarator parameters-and-qualifiers
  noptr-declarator [ constant-expression? ] attribute-specifier-seq?
  ( ptr-declarator )

  noptr-abstract-declarator? parameters-and-qualifiers
  noptr-abstract-declarator? [ constant-expression? ] attribute-specifier-seq?
  ( ptr-abstract-declarator )

  https://timsong-cpp.github.io/cppwp/dcl.decl.general#nt:noptr-declarator
  """
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      d, rest = noptr_declarator_parenthesis.split(ctx, line)
      if d:
        return d, rest
    else:
      d =  None
    if ctx.enable_abstract_declarator:
      if startswith_token(line, '('):
        p, rest = parameters_and_qualifiers.split(ctx, line)
        if p:
          return noptr_declarator_parameters(None, p), rest
      elif line.startswith('['):
        rest = line[1:].lstrip()
        if startswith_token(rest, ']'):
          rest = rest[1:].lstrip()
          e = None
        else:
          e, rest = constant_expression.split(ctx, rest)
          if not e:
            return
          assert startswith_token(rest, ']')
          rest = rest[1:].lstrip()
        a, rest = attribute_specifier_seq.split(ctx, rest)
        return noptr_declarator_array(None, e, a), rest        
    else:
      d, rest = declarator_id_with_optional_attribute_specifier_seq.split(ctx, line)
      if d:
        return d, rest

  @classmethod
  def postprocess(cls, ctx, item, rest):

    def worker(item, rest):
      if startswith_token(rest, '('):
        item2, rest2 = noptr_declarator_parameters.split(ctx, rest, decl=item)
        if item2:
          return worker(item2, rest2)
      elif startswith_token(rest, '['):
        item2, rest2 = noptr_declarator_array.split(ctx, rest, decl=item)
        if item2:
          return worker(item2, rest2)
      return item, rest

    return worker(item, rest)

class ptr_declarator(alternatives('ptr_declarator', ptr_operator_declarator, noptr_declarator)):
  """
  noptr-declarator
  ptr-operator ptr-declarator
  """

class parameter_declaration_list(pair_or_item("parameter_declaration_list", ',', parameter_declaration)):
  """
  parameter-declaration
  parameter-declaration-list , parameter-declaration
  """

class parameter_declaration_clause(namedtuple('parameter_declaration_clause', ['parameter_declaration_list', 'dots'])):
  """
  parameter-declaration-list? ...?
  parameter-declaration-list , ...
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    lst, rest = parameter_declaration_list.split(ctx, line)
    if lst:
      if rest.startswith(','):
        rest = rest[1:].lstrip()
        if rest.startswith('...'):
          rest = rest[3:].lstrip()
          return cls(lst, ',...'), rest
      elif rest.startswith('...'):
        rest = rest[3:].lstrip()
        return cls(lst, '...'), rest
      else:
        return cls(lst, None), rest
    else:
      if rest.startswith('...'):
        rest = rest[3:].lstrip()
        return cls(None, '...'), rest
      else:
        return cls(None, None), rest

class ref_qualifier(namedtuple('ref_qualifier')):
  @splitter
  def split(cls, ctx, line):
    if line.startswith('&&'):
      return cls('&&'), line[2:].lstrip()
    if startswith_token(line, '&'):
      return cls('&'), line[1:].lstrip()

class parameters_and_qualifiers(namedtuple('parameters_and_qualifiers', ['parameter_declaration_clause', 'cv_qualifier_seq', 'ref_qualifier', 'noexcept_specifier', 'attribute_specifier_seq'])):
  """
  ( parameter-declaration-clause ) cv-qualifier-seq? ref-qualifier? noexcept-specifier? attribute-specifier-seq?
  """
  format = '( {0} ) {1} {2} {3} {4}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      c, rest = parameter_declaration_clause.split(ctx, line[1:].lstrip())
      if c:
        if not startswith_token(rest, ')'):
          return
        assert startswith_token(rest, ')'), rest[:50]
        rest = rest[1:].lstrip()
        cv, rest = cv_qualifier_seq.split(ctx, rest)
        q, rest = ref_qualifier.split(ctx, rest)
        s, rest = noexcept_specifier.split(ctx, rest)
        a, rest = attribute_specifier_seq.split(ctx, rest)
        return cls(c, cv, q, s, a), rest

class trailing_return_type(namedtuple('trailing_return_type')):
  format = '-> {0}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '->'):
      t, rest = type_id.split(ctx, line[2:].lstrip())
      if t:
        return cls(t), rest

class noptr_declarator_with_returntype(namedtuple('noptr_declarator_with_returntype', ['noptr_declarator', 'parameters_and_qualifiers', 'trailing_return_type'])):
  """
  noptr-declarator parameters-and-qualifiers trailing-return-type
  """
  format = '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    decl, rest = noptr_declarator.split(ctx, line)
    if isinstance(decl, noptr_declarator_parameters):
      # noptr_declarator.post_process is greedy
      t, rest = trailing_return_type.split(ctx, rest)
      if t:
        return cls(decl.noptr_declarator, decl.parameters_and_qualifiers, t), rest
    elif decl:
      lst, rest = parameters_and_qualifiers.split(ctx, rest)
      if lst:
        t, rest = trailing_return_type.split(ctx, rest)
        if t:
          return cls(decl, lst, t), rest

def declarator_split(ctx, line):
  for dcls in (noptr_declarator_with_returntype, ptr_declarator):
    decl, rest = dcls.split(ctx, line)
    if decl:
      if ctx.enable_abstract_declarator:
        decl = abstract_declarator(decl)
      else:
        decl = declarator(decl)

      if 0 and startswith_token(rest, '('):
        # TODO: there is no function declarator
        decl2, rest2 = function_declarator.split(ctx, rest, head=decl)
        if decl2:
          decl, rest = decl2, rest2

      return decl, rest

class abstract_declarator(namedtuple('abstract_declarator')):
  """
  ptr-abstract-declarator
  noptr-abstract-declarator parameters-and-qualifiers trailing-return-type
  """
  @splitter
  def split(cls, ctx, line):
    with ctx.abstract_declarator(enable=True):
      return declarator_split(ctx, line)

class declarator(namedtuple('declarator')):
  """
  ptr-declarator
  noptr-declarator parameters-and-qualifiers trailing-return-type
  """
  @splitter
  def split(cls, ctx, line):
    with ctx.abstract_declarator(enable=False):
      return declarator_split(ctx, line)

class ptr_declarator_constructor(namedtuple('ptr_declarator_constructor')):
  """
  """
  @splitter
  def split(cls, ctx, line):
    i, rest = qualified_id.split(ctx, line)
    if i:
      return cls(i), rest
    i, rest = class_name.split(ctx, line)
    if i:
      return cls(i), rest

  
class constructor(namedtuple('constructor', ['ptr-declarator', 'parameter-declaration-clause', 'noexcept-specifier', 'attribute-specifier-seq'])):
  """[class.ctor.general]:
    A declarator declares a constructor if it is a function declarator ([dcl.fct]) of the form

      ptr-declarator ( parameter-declaration-clause ) noexcept-specifier? attribute-specifier-seq?

    where the ptr-declarator consists solely of an id-expression, an
    optional attribute-specifier-seq, and optional surrounding
    parentheses, and the id-expression has one of the following forms:

      (1.1) in a friend declaration ([class.friend]), the
      id-expression is a qualified-id that names a constructor
      ([class.qual]);

      (1.2) otherwise, in a member-declaration that belongs to the
      member-specification of a class or class template, the
      id-expression is the injected-class-name ([class.pre]) of the
      immediately-enclosing entity;

      (1.3) otherwise, the id-expression is a qualified-id whose
      unqualified-id is the injected-class-name of its lookup context.

  """
  format = '{0}({1}) {2} {3}'

  @splitter
  def split(cls, ctx, line):
    d, rest = ptr_declarator_constructor.split(ctx, line)
    if d and startswith_token(rest, '('):
      c, rest = parameter_declaration_clause.split(ctx, rest[1:].lstrip())
      if c and startswith_token(rest, ')'):
        rest = rest[1:].lstrip()
        s, rest = noexcept_specifier.split(ctx, rest)
        a, rest = attribute_specifier_seq.split(ctx, rest)
        return cls(d, c, s, a), rest

##########################################################
#                                                        #
#                  Type specifiers                       #
#                                                        #
##########################################################


class type_id(namedtuple('type_id', ['type_specifier_seq', 'abstract_declarator'])):
  """
  type-specifier-seq abstract-declarator?
  """
  format = '{0} {1}'

  @splitter
  def split(cls, ctx, line):
    seq, rest = type_specifier_seq.split(ctx, line)
    if seq:
      decl, rest = abstract_declarator.split(ctx, rest)
      return cls(seq, decl), rest

  @classmethod
  def postprocess(cls, ctx, item, rest):
    # assert not startswith_token(rest, '('), rest[:50]
    return item, rest

def specifier_seq_split(cls, ctx, type_specifier, specifier, line, has_type_specifier = False):
  """
  specifier attribute-specifier-seq?
  specifier specifier-seq
  """
  rest = line
  lst = []
  # https://timsong-cpp.github.io/cppwp/dcl.type.general#2
  #   at most one type-specifier (that is not a cv_qualifier) is allowed in a type-specifier-seq
  while True:
    t, rest_ = specifier.split(ctx, rest)
    if t:
      if isinstance(t, type_specifier):
        if has_type_specifier:
          break
        has_type_specifier = True
      rest = rest_
      lst.append(t)
      a, rest = attribute_specifier_seq.split(ctx, rest)
      if a:
        lst.append(a)
    else:
      break
  if lst:
    return cls(tuple(lst)), rest

  
class type_specifier_seq(namedtuple('type_specifier_seq')):
  """
  type-specifier attribute-specifier-seq?
  type-specifier type-specifier-seq
  """

  @splitter
  def split(cls, ctx, line):
    return specifier_seq_split(cls, ctx, type_specifier, type_specifier, line)

class type_specifier(alternatives('type_specifier',
                                  cv_qualifier,
                                  lambda: simple_type_specifier,
                                  lambda: typename_specifier,
                                  lambda: elaborated_type_specifier,
                                  )):
  """
  simple-type-specifier
  elaborated-type-specifier
  typename-specifier
  cv-qualifier
  """
  @classmethod
  def postprocess(cls, ctx, item, rest):
    if not isinstance(item, cv_qualifier) and item:
      item = cls(item)
    return item, rest

class access_specifier(namedtuple('access_specifier')):
  @classmethod
  def split_keywords(cls):
    return ('private', 'public', 'protected')

class nullptr_t(namedtuple('nullptr_t')):
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line)
    if w == 'nullptr_t':
      return cls(w)

class pointer_types(namedtuple('pointer_types')):
  @splitter
  def split(cls, ctx, line):
    print(f'{cls.__name__}.split(ctx, `{line.splitlines()[0]}`) <- NOT IMPLEMENTED (what is a pointer type?)')
    return
    return NotImplemented


class integer_types(namedtuple('integer_types')):
  @splitter
  def split(cls, ctx, line):
    t, rest = keyword_type_specifier.split(ctx, line)
    if t:
      for it in ['int', 'char', 'short', 'signed', 'unsigned']:
        if it in t.content:
          return t, rest
      if 'long' in t.content and 'double' not in t.content:
        return t, rest

class floating_types(namedtuple('floating_types')):
  @splitter
  def split(cls, ctx, line):
    t, rest = keyword_type_specifier.split(ctx, line)
    if t and t.content[-1] in {'float', 'double'}:
      return t, rest

# NOT USED??
class arithmetic_types(alternatives('arithmetic_types', integer_types, floating_types)):
  """
  """

class scalar_types(alternatives('scalar_types', arithmetic_types, pointer_types, nullptr_t)):
  pass

class void(namedtuple('void')):
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='void')
    if w:
      return cls(w), rest

class enum_name(identifier):
  pass

class class_name(alternatives('class_name', lambda: simple_template_id, identifier)):
  """
  """

class typedef_name(namedtuple('typedef_name')):
  @classmethod
  def alternatives(cls):
    return (
        simple_template_id,
        identifier
    )

class type_name(namedtuple('type_name')):
  @classmethod
  def alternatives(cls):
    return (
        class_name,
        enum_name,
        typedef_name
    )

nested_name_spec = nested_name_specifier
  
class type_name_with_opt_nested_name_spec(namedtuple("type_name_with_opt_nested_name_spec", ['nested_name_spec', 'type_name'])):

  @property
  def format(self):
    if self[0]:
      return '{0}::{1}'
    return '{1}'

  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_spec.split(ctx, line)
    tname, rest = type_name.split(ctx, rest)
    if not tname:
      tname, rest = identifier.split(ctx, rest)
    if tname:
      return cls(spec, tname), rest

class simple_template_id(namedtuple('simple_template_id', ['template_name', 'template_argument_list'])):
  """
  template-name < template-argument-list? >
  """
  format = '{0}<{1}>'
  @splitter
  def split(cls, ctx, line):
    o, rest = template_name.split(ctx, line)
    if o and startswith_token(rest, '<'):
      rest = rest[1:].lstrip()
      if startswith_token(rest, '>'):
        return cls(o, None), rest[1:].lstrip()

      # https://timsong-cpp.github.io/cppwp/temp.names#4 : When parsing
      # a template-argument-list, the first non-nested > is taken
      # as the ending delimiter rather than a greater-than operator.
      raw, rest = split_until(rest, '>')
      if not raw:
        return
      lst, rest2 = template_argument_list.split(ctx, raw)
      if lst:
        if rest2 != '':
          return
        assert rest2 == '', rest2
        return cls(o, lst), rest


class template_simple_template_id(namedtuple('template_simple_template_id', ['template', 'simple_template_id'])):
  """Helper type

  template? simple-template-id
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='template')
    i, rest = simple_template_id.split(ctx, rest)
    if i:
      return cls(w, i), rest

class simple_template_id_with_nested_name_spec(namedtuple('simple_template_id_with_nested_name_spec', ['nested_name_spec', 'simple_template_id'])):
  format = '{0}::template {1}'

  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_spec.split(ctx, line)
    if spec:
      w, rest = word.split(ctx, rest)
      if w == 'template':
        t, rest = simple_template_id.split(ctx, rest)
        if t:
          return cls(spec, t), rest

class pack_index_specifier(namedtuple('pack_index_specifier')):
  """
  typedef-name ... [ constant-expression ]
  """
  @splitter
  def split(cls, ctx, line):
    n, rest = typedef_name.split(ctx, line)
    if rest.startswith('...'):
      rest = rest[3:].lstrip()
      if startswith_token(rest, '['):
        raw, rest = split_until(rest[1:].lstrip(), ']')
        if raw:
          return cls(n, constant_expression(raw)), rest


class computed_type_specifier(alternatives('computed_type_specifier',
                                           decltype_specifier,
                                           pack_index_specifier)):
  """
  decltype-specifier
  pack-index-specifier
  """

class class_or_decltype_type_name(namedtuple('class_or_decltype_type_name', ['nested_name_specifier', 'type_name'])):
  @splitter
  def split(cls, ctx, line):
    # TODOOOOOOOOOOOOOOO infinite recursion
    s, rest = nested_name_specifier.split(ctx, line)
    t, rest = type_name.split(ctx, rest)
    if t:
      return cls(s, t), rest

class class_or_decltype_template(namedtuple('class_or_decltype_template', ['nested_name_specifier', 'simple_template_id'])):
  format = '{0}template {1}'
  @splitter
  def split(cls, ctx, line):
    # TODOOOOOOOOOOOOOOO infinite recursion
    s, rest = nested_name_specifier.split(ctx, line)
    if s:
      t, rest = word.split(ctx, rest, require='template')
      if t:
        i, rest = simple_template_id.split(ctx, rest)
        if i:
          return cls(s, i), rest

class class_or_decltype(alternatives('class_or_decltype',
                                     class_or_decltype_type_name,
                                     class_or_decltype_template,
                                     computed_type_specifier)):
  """
  nested-name-specifier? type-name
  nested-name-specifier template simple-template-id
  computed-type-specifier
  """

  
class base_specifier(namedtuple('base_specifier', ['attribute_specifier_seq', 'specifier1', 'specifier2', 'class_or_decltype'])):
  """
  attribute-specifier-seq?                           class-or-decltype
  attribute-specifier-seq? virtual access-specifier? class-or-decltype
  attribute-specifier-seq? access-specifier virtual? class-or-decltype
  """
  @splitter
  def split(cls, ctx, line):
    seq, rest = attribute_specifier_seq.split(ctx, line)
    virtual, rest = word.split(ctx, rest, require='virtual')
    if virtual:
      a, rest = access_specifier.split(ctx, rest)
      s1, s2 = virtual, a
    else:
      a, rest = access_specifier.split(ctx, rest)
      virtual, rest = word.split(ctx, rest, require='virtual')
      s1, s2 = a, virtual

    c, rest = class_or_decltype.split(ctx, rest)
    if c:
      return cls(seq, s1, s2, c), rest
    
class base_specifier_dots(item_optional_dots(base_specifier)):
  """
  base-specifier ...?
  """
    
class base_specifier_list(pair_or_item('base_specifier_list', ',', base_specifier_dots)):
  """
  base-specifier ...?
  base-specifier-list , base-specifier ...?
  """

class base_clause(namedtuple('base_clause')):
  """
  : base-specifier-list
  """
  format = ': {0}'

  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, ':'):
      lst, rest = base_specifier_list.split(ctx, line[1:].lstrip())
      if lst:
        return cls(lst), rest

class member_declaration_with_semicolon(namedtuple('member_declaration', ['attr_seq', 'decl_specifier_seq', 'member_declarator_list'])):
  """
  attr ﻿(optional) decl-specifier-seq ﻿(optional) member-declarator-list ﻿(optional) ;
  """
  format = '{0} {1} {2};'

  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    attr_seq, rest = attribute_specifier_seq.split(ctx, line)
    if 1:
      #  First detect constructor declarations:
      seq, rest_ = decl_specifier_seq.split(ctx, rest, has_type_specifier=True)
      ctr, rest_ = constructor.split(ctx, rest_)
      if ctr and rest_.startswith(';'):
        return cls(attr_seq, seq, ctr), rest_
    decl_seq, rest = decl_specifier_seq.split(ctx, rest)
    member_lst, rest = member_declarator_list.split(ctx, rest)
    return cls(attr_seq, decl_seq, member_lst), rest


class friend_type_declaration(namedtuple('friend_type_declaration')):
  """
  friend friend-type-specifier-list ;

  https://timsong-cpp.github.io/cppwp/class.mem.general#nt:friend-type-declaration
  """
  format = 'friend {0};'

  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='friend')
    if w:
      return friend_type_specifier_list.split(ctx, rest)


class explicit_specialization(namedtuple('explicit_specialization')):
  """
  template < > declaration
  """
  format = 'template <> {0}'
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='template')
    if w:
      if startswith_token(rest, '<'):
        rest = rest[1:].lstrip()
        if startswith_token(rest, '>'):
          rest = rest[1:].lstrip()
          decl, rest = declaration.split(ctx, rest)
          if decl:
            return ctx(decl), rest

class explicit_specifier(namedtuple('explicit_specifier')):
  """
  explicit ( constant-expression )
  explicit
  """
  @property
  def format(self):
    if self[0]:
      return 'explict({0})'
    return 'explict'
  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require='explicit')
    if w:
      if startswith_token(rest, '('):
        raw, rest = split_until(rest[1:].lstrip(), ')')
        e, rest2 = constant_expression.split(ctx, rest)
        if rest2:
          return UNEXPECTED
        return cls(e), rest
      return cls(None), rest

  
class deduction_guide(namedtuple('deduction_guide', ['explicit_specifier', 'template_name', 'parameter_declaration_clause', 'requires_clause', 'simple_template_id'])):
  """
  explicit-specifier? template-name ( parameter-declaration-clause ) requires-clause? -> simple-template-id ;
  """
  format = '{0} {1} ( {2} ) {3} -> {4};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    spec, rest = explicit_specifier.split(ctx, line)
    n, rest = template_name.split(ctx, rest)
    if n and startswith_token(rest, '('):
      c, rest = parameter_declaration_clause.split(ctx, rest[1:].lstrip())
      if c and startswith_token(rest, ')'):
        r, rest = requires_clause.split(ctx, rest[1:].lstrip())
        if startswith_token(rest, '->'):
          i, rest = simple_template_id.split(ctx, rest[2:].lstrip())
          if i:
            return cls(spec, n, c, r, i), rest

  
class member_declaration(alternatives('member_declaration',
                                      lambda:
                                      (
                                        alias_declaration,
                                        member_declaration_with_semicolon,
                                        using_declaration,
                                        friend_type_declaration,
                                        using_enum_declaration,
                                        static_assert_declaration,
                                        template_declaration,
                                        explicit_specialization,
                                        deduction_guide,
                                        opaque_enum_declaration,
                                        function_definition,
                                        empty_declaration))):
  """
  function-definition
  friend-type-declaration
  using-declaration
  using-enum-declaration
  static_assert-declaration
  template-declaration
  explicit-specialization
  deduction-guide
  alias-declaration
  opaque-enum-declaration
  empty-declaration

  https://timsong-cpp.github.io/cppwp/class.mem.general#nt:member-declaration
  """

class access_specifier_with_colon(namedtuple('access_specifier_with_colon')):
  """
  private :
  protected :
  public :
  https://timsong-cpp.github.io/cppwp/class.derived.general#nt:access-specifier
  https://timsong-cpp.github.io/cppwp/class.mem.general#nt:member-specification
  """
  format = '{0}:'

  @splitter
  def split(cls, ctx, line):
    w, rest = word.split(ctx, line, require=['public', 'protected', 'private'])
    if startswith_token(rest, ':'):
      return cls(w), rest[1:].lstrip()

class class_declaration(namedtuple('class_declaration')):
  """
  class-specifier ;
  """
  format = '{0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    c, rest = class_specifier.split(ctx, line)
    if c:
      return cls(c), rest

class class_forward_declaration(namedtuple('class_forward_declaration', ['class_key', 'attr', 'identifier'])):
  """
  class-key attr? identifier ;
  """
  format = '{0} {1} {2};'
  @splitter
  def split(cls, ctx, line):
    key, rest = word.split(ctx, line, require=['class', 'struct', 'union'])
    if key:
      attr, rest = attribute_specifier_seq.split(ctx, rest)
      i, rest = identifier.split(ctx, rest)
      if i and rest.startswith(';'):
        return cls(key, attr, i), rest[1:].lstrip()

class class_template_declaration(namedtuple('class_template_declaration', ['template_parameter_list', 'requires', 'class_declaration'])):
  """
  template < parameter-list > class-declaration	(1)	
  template < parameter-list > requires constraint class-declaration	(2)
  export template < parameter-list > class-declaration	(3)	  removed in C++11
  """
  f = '{0} {1} {2}'
  def ____str__(self):
    r = f'{self.template_parameter_list}'
    if self.requires is not None:
      r += f' {self.requires}'
    r += f'{self.class_declaration}'
    return r
  @splitter
  def split(cls, ctx, line):
    if line.startswith('export template'):
      return NotImplemented
    lst, rest = template_template_parameter_list.split(ctx, line)
    if lst is not None:

      req, rest = requires_clause.split(ctx, rest)
      decl, rest = class_declaration.split(ctx, rest)
      if decl is not None:
        return cls(lst, req, decl), rest


class function_declaration(namedtuple('function_declaration')):
  @classmethod
  def alternatives(cls):
    return (function_definition,)
    
class function_template_declaration(namedtuple('function_template_declaration', ['template_parameter_list', 'requires', 'function_declaration'])):
  """
  template < parameter-list > function-declaration	(1)	
  template < parameter-list > requires constraint function-declaration	(2)
  function-declaration-with-placeholders	(3)
  export template < parameter-list > function-declaration	(4)  (removed in C++11)
  """
  def __str__(self):
    r = f'{self.template_parameter_list}'
    if self.requires is not None:
      r += f' {self.requires}'
    r += f'{self.function_declaration}'
    return r
  @splitter
  def split(cls, ctx, line):
    if line.startswith('export template'):
      return NotImplemented

    lst, rest = template_template_parameter_list.split(ctx, line)
    if lst is not None:
      if 'auto' in str(lst):
        # TODO: (3), same as function-declaration but one template parameter uses auto or Concept auto
        print(f'WARNING: {cls.__name__}.split does not implement function-template-declaration-with-placeholders')
      req, rest = requires_clause.split(ctx, rest)
      decl, rest = function_declaration.split(ctx, rest)
      if decl is not None:
        return cls(lst, req, decl), rest

class variable_declaration(namedtuple('variable_declaration')):
  @classmethod
  def alternatives(cls):
    return (simple_declaration,)

    
class variable_template_declaration(namedtuple('variable_template_declaration', ['template_parameter_list', 'requires', 'variable_declaration'])):
  """
  template < parameter-list > variable-declaration	(1)	
  template < parameter-list > requires constraint variable-declaration	(2)	
  """
  def __str__(self):
    r = f'{self.template_parameter_list}'
    if self.requires is not None:
      r += f' {self.requires}'
    r += f'{self.variable_declaration}'
    return r
  @splitter
  def split(cls, ctx, line):
    lst, rest = template_template_parameter_list.split(ctx, line)
    if lst is not None:
      req, rest = requires_clause.split(ctx, rest)
      decl, rest = variable_declaration.split(ctx, rest)
      if decl is not None:
        return cls(lst, req, decl), rest

class member_template_declaration(namedtuple('member_template_declaration')):
  @classmethod
  def alternatives(cls):
    return (
        class_template_declaration,
        function_template_declaration,
        variable_template_declaration,
    )

class explicit_keyword(namedtuple('explicit_keyword')):
  @classmethod
  def split_keywords(cls):
    return ('explict',)

class template_name(alternatives('template_name', identifier)):
  """
  """

class function_deduction_guide(namedtuple('function_deduction_guide', ['explicit', 'template_name', 'template_parameter_list', 'requires_clause', 'simple_template_id'])):
  """
  explicit ﻿(optional) template-name ( parameter-list ) requires-clause ﻿(optional) -> simple-template-id ;	(1)
  """
  def __str__(self):
    r = '{self.explicit or ""}'
    r += (' ' if r else '') + f'{self.template_name} ( {self.template_parameter_list} )'
    if self.requires_clause is not None:
      r += f' {self.reduction_clause}'
    r += f' -> {self.simple_template_id}'
    return r

  @splitter
  def split(cls, ctx, line):
    exp, rest = explicit_keyword.split(ctx, line)
    n, rest = template_name.split(ctx, rest)
    if n and startswith_token(rest, '('):
      raw, rest = split_until(rest[1:].lstrip(), ')')
      lst, rest2 = template_parameter_list.split(ctx, raw)
      if lst is not None:
        req, rest = requires_clause.split(ctx, rest)
        if startswith_token(rest, '->'):
          i, rest = simple_template_id.split(ctx, rest[2:].lstrip())
          if i and rest.startswith(';'):
            return cls(exp, n, lst, req, i), rest
  
class function_template_deduction_guide(namedtuple('function_template_deduction_guide', ['template_parameter_list', 'requires_clause', 'function_deduction_guide'])):
  """
  template <template-parameter-list ﻿> requires-clause ﻿(optional) explicit ﻿(optional) template-name ( parameter-list ) requires-clause ﻿(optional) -> simple-template-id ;	(2)
  """
  @splitter
  def split(cls, ctx, line):
    tmpl, rest = template_template_parameter_list.split(ctx, line)
    if tmpl:
      req, rest = requires_clause.split(ctx, rest)
      guide, rest = function_deduction_guide.split(ctx, rest)
      if guide is not None:
        return cls(tmpl, req, guide), rest


class user_defined_deduction_guide(namedtuple('user_defined_deduction_guide')):
  @classmethod
  def alternatives(cls):
    return (
        function_deduction_guide,
        function_template_deduction_guide,
    )

class initializer_clause_dots(namedtuple('initializer_clause_dots')):
  """
  initializer-clause ...?
  """
  format = '{0} ...'
  @splitter
  def split(cls, ctx, line):
    i, rest = initializer_clause.split(ctx, line)
    if i:
      if rest.startswith('...'):
        return cls(i), rest[3:].lstrip()
      return i, rest

class initializer_list(pair_or_item('initializer_list', ',', initializer_clause_dots)):
  """
  initializer-clause ...?
  initializer-list , initializer-clause ...?
  """

expression_list = initializer_list

class parameter_pack(identifier):
  pass
    
class member_initialize_multiple(namedtuple('member_initialize_multiple')):
  def __str__(self):
    return f'{self[0]}...'

  @splitter
  def split(cls, ctx, line):
    p, rest = parameter_pack.split(ctx, line)
    if p is not None:
      return cls(p), rest
  
class mem_initializer_id(namedtuple('mem_initializer_id')):
  @classmethod
  def alternatives(cls):
    return (class_or_decltype, identifier)

  @classmethod
  def postprocess(cls, ctx, item, rest):
    #assert isinstance(item, identifier), (cls, item, item.type_name)
    return item, rest
  
class mem_initializer_expr_list(namedtuple('mem_initializer_expr_list', ['mem_initializer_id', 'expression_list'])):
  """
  mem-initializer-id ( expression-list? )
  """
  format = '{0}({1})'
  @splitter
  def split(cls, ctx, line):
    i, rest = mem_initializer_id.split(ctx, line)
    if i:
      if startswith_token(rest, '('):
        rest = rest[1:].lstrip()
        if startswith_token(rest, ')'):
          return cls(i, None), rest[1:].lstrip()
        lst, rest = expression_list.split(ctx, rest)
        if lst:
          assert startswith_token(rest, ')'), rest
          return cls(i, lst), rest[1:].lstrip()

class mem_initializer_init_list(namedtuple('mem_initializer_init_list', ['mem_initializer_id', 'braced_init_list'])):
  """
  mem-initializer-id braced-init-list
  """
  @splitter
  def split(cls, ctx, line):
    i, rest = mem_initializer_id.split(ctx, line)
    if i:
      lst, rest = braced_init_list.split(ctx, rest)
      if lst:
        return cls(i, lst)

class mem_initializer(namedtuple('mem_initializer')):
  @classmethod
  def alternatives(cls):
    return (mem_initializer_expr_list, mem_initializer_init_list)
  

class equal_initializer(namedtuple('equal_initializer')):
  format = '= {0}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '='):
      i, rest = initializer_clause.split(ctx, line[1:].lstrip())
      if i:
        return cls(i), rest

class braced_init_list(namedtuple('braced_init_list')):
  """
  { initializer-list ,? }
  { designated-initializer-list ,? }
  { }
  """
  format = '{{ {0} }}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('{'):
      rest = line[1:].lstrip()
      if startswith_token(rest, '}'):
        return cls(None), rest[1:].lstrip()
      for lcls in [initializer_list, designated_initializer_list]:
        lst, rest2 = lcls.split(ctx, rest)
        if lst:
          if rest2.startswith(','):
            rest2 = rest2[1:].lstrip()
          if not rest2.startswith('}'):
            continue
          assert rest2.startswith('}'), rest2
          return cls(lst), rest2[1:].lstrip()

class brace_or_equal_initializer(namedtuple('brace_or_equal_initializer')):
  """
  = initializer-clause
  braced-init-list
  """
  @classmethod
  def alternatives(self):
    return (
      equal_initializer,
      braced_init_list
      )

class bit_field_declaration(namedtuple('bit_field_declaration', ['identifier', 'attr_seq', 'size', 'brace_or_equal_initializer'])):
  """
  identifier ﻿(optional) attr ﻿(optional) : size	(1)	
  identifier ﻿(optional) attr ﻿(optional) : size brace-or-equal-initializer	(2)
  """
  def __str__(self):
    lst = []
    if self.identifier:
      lst.append(str(self.identifier))
    if self.attr_seq:
      lst.append(str(self.attr_seq))
    lst.append(f' : {self.size}')
    if self.brace_or_equal_initializer:
      lst.append(str(self.brace_or_equal_initializer))
    return ' '.join(lst)
  @splitter
  def split(cls, ctx, line):
    i, rest = identifier.split(ctx, line)
    attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
    if startswith_token(rest, ':'):
      rest = rest[1:].lstrip()
      sz, rest = size.split(ctx, rest)
      if sz:
        init, rest = brace_or_equal_initializer.split(ctx, rest)
        return cls(i, attr_seq, sz, init), rest

class pure_specifier(namedtuple('pure_specifier')):
  format = '{0}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '='):
      rest = line[1:].lstrip()
      if rest.startswith('0'):
        rest = rest[1:].lstrip()
        if not startswith_identifier(rest):  # TODO: is this accurate enough?
          return cls('=0'), rest.lstrip()

class member_declarator_simple(namedtuple('member_declarator_simple', ['declarator', 'virt_specifier_seq', 'pure_specifier'])):
  format = '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    decl, rest = declarator.split(ctx, line)
    if decl:
      seq, rest = virt_specifier_seq.split(ctx, rest)
      spec, rest = pure_specifier.split(ctx, rest)
      return cls(decl, seq, spec), rest

class member_declarator_with_requires_clause(namedtuple('member_declarator_with_requires_clause', ['declarator', 'requires_clause'])):
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    decl, rest = declarator.split(ctx, line)
    if decl:
      req, rest = requires_clause.split(ctx, rest)
      if req:
        return cls(decl, req), rest

class member_declarator_with_initializer(namedtuple('member_declarator_with_initializer', ['declarator', 'brace_or_equal_initializer'])):
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    decl, rest = declarator.split(ctx, line)
    if decl:
      i, rest = brace_or_equal_initializer.split(ctx, rest)
      if i:
        return cls(decl, i), rest

class member_declarator_with_expression(namedtuple('member_declarator_with_expression', ['identifier', 'attribute_specifier_seq', 'constant_expression', 'brace_or_equal_initializer'])):
  format = '{0} {1} : {2} {3}'
  @splitter
  def split(cls, ctx, line):
    i, rest = identifier.split(ctx, line)
    attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
    if startswith_token(rest, ':'):
      e, rest = constant_expression.split(ctx, rest[1:].lstrip())
      if e:
        init, rest = brace_or_equal_initializer.split(ctx, rest)
        return cls(i, attr_seq, e, init), rest

class member_declarator(namedtuple('member_declarator')):
  """
  declarator virt-specifier-seq? pure-specifier?
  declarator requires-clause
  declarator brace-or-equal-initializer
  identifier? attribute-specifier-seq? : constant-expression brace-or-equal-initializer?
  """
  @classmethod
  def alternatives(cls):
    return (
      member_declarator_with_requires_clause,
      member_declarator_with_initializer,
      member_declarator_with_expression,
      member_declarator_simple
    )

class member_declarator_list(pair_or_item('member_declarator_list', ',', member_declarator)):
  """
  member-declarator
  member-declarator-list , member-declarator
  """

class member_declaration_or_access_specifier(alternatives('member_declaration_or_access_specifier', member_declaration, access_specifier_with_colon)):
  """
  member-declaration
  access-specifier :
  """
  
class member_specification(namedtuple('member_specification')):
  """
  member-declaration member-specification?
  access-specifier : member-specification?

  https://timsong-cpp.github.io/cppwp/class.mem.general#nt:member-specification
  """
  @splitter
  def split(cls, ctx, line, head=None):
    m, rest = member_declaration_or_access_specifier.split(ctx, line)
    if m:
      return cls((m,)), rest

  @classmethod
  def postprocess(cls, ctx, item, rest):
    assert item is not None
    item2, rest2 = cls.split(ctx, rest)
    if item2:
      item, rest = cls(item.content + item2.content), rest2
    return item, rest


class class_head_name(namedtuple('class_head_name', ['nested_name_specifier', 'class_name'])):
  """
  nested-name-specifier? class-name
  https://timsong-cpp.github.io/cppwp/class.pre#nt:class-head-name
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_specifier.split(ctx, line)
    n, rest = class_name.split(ctx, rest)
    if n:
      return cls(spec, n), rest

class class_virt_specifier(namedtuple('class_virt_specifier')):
  @classmethod
  def split_keywords(cls):
    return ('final',)
  
class class_key(namedtuple('class_key')):
  @classmethod
  def split_keywords(cls):
    return ('class', 'struct', 'union')

class class_head_named(namedtuple('class_head_named', ['class_key', 'attr_seq', 'class_head_name', 'class_virt_specifier', 'base_clause'])):
  """
  See class_head.
  """
  format = '{0} {1} {2} {3} {4}'
  @splitter
  def split(cls, ctx, line):
    key, rest = class_key.split(ctx, line)
    if key:
      attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
      n, rest = class_head_name.split(ctx, rest)
      if n:
        s, rest = class_virt_specifier.split(ctx, rest)
        b, rest = base_clause.split(ctx, rest)
        return cls(key, attr_seq, n, s, b), rest

class class_head_unnamed(namedtuple('class_head_named', ['class_key', 'attr_seq', 'base_clause'])):
  """
  See class_head.
  """
  format = '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    key, rest = class_key.split(ctx, line)
    if key:
      attr_seq, rest = attribute_specifier_seq.split(ctx, rest)
      b, rest = base_clause.split(ctx, rest)
      return cls(key, attr_seq, b), rest

class class_head(alternatives('class_head', class_head_named, class_head_unnamed)):
  """
  class-key attribute-specifier-seq? class-head-name class-virt-specifier? base-clause?
  class-key attribute-specifier-seq? base-clause?

  https://timsong-cpp.github.io/cppwp/class.pre#nt:class-head
  """

def _report_unexpected_block_end(cls, head_lines, rest):
  print(f'{cls.__name__}: unexpected return when parsing the following block:')
  print('v'*120)
  print(head_lines.rstrip())
  print('...... <SNIP LINES> ......')
  raw, rest_ = split_until(rest, '}', keep_mark=True, require_mark=False)
  lines = str(raw).splitlines()
  if len(lines) > 25:
    lines = lines[:15] + [f'...... <SNIP {len(lines) - 25} LINES> ......'] + lines[-5:]
  print('\n'.join(lines))
  print('^'*120)
  

class class_specifier(namedtuple('class_specifier', ['class_head', 'member_specification'])):
  """
  class-head { member-specification? }

  https://timsong-cpp.github.io/cppwp/class.pre#nt:class-specifier
  """
  @property
  def format(self):
    return '{0} {{ {1} }}' if self[1].content else '{0} {{}}'

  @splitter
  def split(cls, ctx, line):
    h, rest = class_head.split(ctx, line)
    assert rest is not None
    if h:
      head_lines = line[:len(line) - len(rest)]
      if startswith_token(rest, '{'):
        rest = rest[1:].lstrip()
        if startswith_token(rest, '}'):
          return cls(h, None), rest[1:].lstrip()
        m, rest = member_specification.split(ctx, rest)
        if m:
          if not startswith_token(rest, '}'):
            _report_unexpected_block_end(cls, head_lines, rest)
            raise RuntimeError(f'unexpected return when parsing class member specifications (see output above)')
          return cls(h, m), rest[1:].lstrip()

class enumerator(namedtuple('enumerator', ['enumerator', 'constant_expression'])):
  def __str__(self):
    if self.constant_expression:
      return f'{self.enumerator} = {self.constant_expression}'
    return str(self.enumerator)
  @splitter
  def split(cls, ctx, line):
    n, rest = identifier.split(ctx, line)
    if n:
      if startswith_token(rest, '='):
        e, rest = split_until(rest[1:].lstrip(), ',', require_mark=False)
        if e:
          return cls(n, e), rest
      else:
        if rest.startswith(','):
          rest = rest[1:].lstrip()
        return cls(n, None), rest

class enumerator(item_optional_suffix(identifier, attribute_specifier_seq)):
  """
  identifier attribute-specifier-seq?
  """

class enumerator_with_value(namedtuple('enumerator_with_value', ['enumerator', 'constant-expression'])):
  format = '{0} = {1}'
  @splitter
  def split(cls, ctx, line):
    e, rest = enumerator.split(ctx, line)
    if e:
      if rest.startswith('='):
        v, rest_ = constant_expression.split(ctx, rest[1:].lstrip())
        if v:
          return cls(e, v), rest_
      else:
        return e, rest

class enumerator_definition(alternatives('enumerator_definition', enumerator_with_value)):
  """
  enumerator
  enumerator = constant-expression
  """

class enumerator_list(pair_or_item('enumerator_list', ',', enumerator_definition)):
  """
  enumerator-definition
  enumerator-list , enumerator-definition
  """

class enum_key(namedtuple('enum_key')):
  """
  enum
  enum class
  enum struct
  """
  @splitter
  def split(cls, ctx, line):
    e, rest = word.split(ctx, line, require='enum')
    if e:
      k, rest = word.split(ctx, rest, require='class')
      if k:
        return cls('enum class'), rest
      k, rest = word.split(ctx, rest, require='struct')
      if k:
        return cls('enum struct'), rest
      return cls(e), rest

    
class enum_head_name(item_optional_prefix(identifier, nested_name_specifier)):
  """
  nested-name-specifier? identifier
  """

class enum_base(namedtuple('enum_base')):
  """
  : type-specifier-seq
  """
  format = ': {0}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, ':'):
      s, rest = type_specifier_seq.split(ctx, line[1:].lstrip())
      if s:
        return cls(s), rest

class enum_head(namedtuple('enum_head', ['enum-key', 'attribute-specifier-seq', 'enum-head-name', 'enum-base'])):
  """
  enum-key attribute-specifier-seq? enum-head-name? enum-base?
  """
  format = '{0} {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    k, rest = enum_key.split(ctx, line)
    if k:
      a, rest = attribute_specifier_seq.split(ctx, rest)
      n, rest = enum_head_name.split(ctx, rest)
      b, rest = enum_base.split(ctx, rest)
      return cls(k, a, n, b), rest

class enum_specifier(namedtuple('enum_specifier', ['enum-head', 'enumerator-list'])):
  """
  enum-head { enumerator-list? }
  enum-head { enumerator-list , }
  """
  format = '{0} {{{1}}}'
  @splitter
  def split(cls, ctx, line):
    h, rest = enum_head.split(ctx, line)
    if h and rest.startswith('{'):
      head_lines = line[:len(line) - len(rest)]
      rest = rest[1:].lstrip()
      if rest.startswith('}'):
        return cls(h, None), rest[1:].lstrip()
      lst, rest = enumerator_list.split(ctx, rest)
      if lst:
        if rest.startswith(','):
          rest = rest[1:].strip()
        if rest.startswith('}'):
          return cls(h, lst), rest[1:].lstrip()
        _report_unexpected_block_end(cls, head_lines, rest)
        raise RuntimeError(f'unexpected return when parsing {cls.__name__} (see output above)')


class elaborated_type_specifier_class_identifier(namedtuple('elaborated_type_specifier_class_identifier',
                                                            ['class-key', 'attribute-specifier-seq', 'nested-name-specifier', 'identifier'])):
  """
  class-key attribute-specifier-seq? nested-name-specifier?          identifier
  """
  format = '{0} {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    key, rest = class_key.split(ctx, line)
    if key:
      a, rest = attribute_specifier_seq.split(ctx, rest)
      s, rest = nested_name_specifier.split(ctx, rest)
      i, rest = identifier.split(ctx, rest)
      if i:
        return cls(key, a, s, i), rest

class elaborated_type_specifier_class_template_id(namedtuple('elaborated_type_specifier_class_template_id', ['class-key','simple-template-id'])):
  """
  class-key                                                          simple-template-id
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    key, rest = class_key.split(ctx, line)
    if key:
      i, rest = simple_template_id.split(ctx, rest)
      if i:
        return cls(key, i), rest
  
class elaborated_type_specifier_class_nested_template_id(namedtuple('elaborated_type_specifier_class_nested_template_id',
                                                                    ['class-key', 'nested-name-specifier', 'template', 'simple-template-id'])):
  """
  class-key                          nested-name-specifier template? simple-template-id
  """
  format = '{0} {1}{2} {3}'
  @splitter
  def split(cls, ctx, line):
    key, rest = class_key.split(ctx, line)
    if key:
      s, rest = nested_name_specifier.split(ctx, rest)
      if s:
        template, rest = word.split(ctx, line, require='template')
        i, rest = simple_template_id.split(ctx, rest)
        if i:
          return cls(key, s, template, i), rest

class elaborated_type_specifier_enum_identifier(namedtuple('elaborated_type_specifier_enum_identifier', ['nested-name-specifier', 'identifier'])):
  """
  enum                               nested-name-specifier?          identifier
  """
  format = 'enum {0} {1}'
  @splitter
  def split(cls, ctx, line):
    enum, rest = word.split(ctx, line, require='enum')
    if enum:
      s, rest = nested_name_specifier.split(ctx, rest)
      i, rest = identifier.split(ctx, rest)
      if i:
        return cls(s, i), rest

class elaborated_type_specifier(alternatives('elaborated_type_specifier',
    elaborated_type_specifier_class_template_id,
    elaborated_type_specifier_class_nested_template_id,
    elaborated_type_specifier_class_identifier,
    elaborated_type_specifier_enum_identifier)):
  """
  class-key attribute-specifier-seq? nested-name-specifier?          identifier
  class-key                                                          simple-template-id
  class-key                          nested-name-specifier template? simple-template-id
  enum                               nested-name-specifier?          identifier
  """

class typename_specifier_identifier(namedtuple('typename_specifier_identifier', ['nested-name-specifier', 'identifier'])):
  """
  typename nested-name-specifier identifier
  """
  format = 'typename {0}{1}'
  @splitter
  def split(cls, ctx, line):
    typename, rest = word.split(ctx, line, require='typename')
    if typename:
      ns, rest = nested_name_specifier.split(ctx, rest)
      if ns:
        i, rest = identifier.split(ctx, rest)
        if i:
          return cls(ns, i), rest

class typename_specifier_template_id(namedtuple('typename_specifier_template_id', ['nested-name-specifier', 'template', 'simple-template-id'])):
  """
  typename nested-name-specifier template? simple-template-id
  """
  format = 'typename {0}{1} {2}'
  @splitter
  def split(cls, ctx, line):
    typename, rest = word.split(ctx, line, require='typename')
    if typename:
      ns, rest = nested_name_specifier.split(ctx, rest)
      if ns:
        template, rest = word.split(ctx, rest, require='template')
        i, rest = simple_template_id.split(ctx, rest)
        if i:
          return cls(ns, template, i), rest

class typename_specifier(alternatives('typename_specifier', typename_specifier_template_id, typename_specifier_identifier)):
  """
  typename nested-name-specifier identifier
  typename nested-name-specifier template? simple-template-id
  """

class simple_type_specifier_type_name(namedtuple('simple_type_specifier_type_name', ['nested_name_specifier', 'type_name'])):
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_specifier.split(ctx, line)
    n, rest = type_name.split(ctx, rest)
    if n:
      return cls(spec, n), rest

class simple_type_specifier_template_name(namedtuple('simple_type_specifier_template_name', ['nested_name_specifier', 'template_name'])):
  """
  nested-name-specifier? template-name
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_specifier.split(ctx, line)
    n, rest = template_name.split(ctx, rest)
    if n:
      return cls(spec, n), rest

class simple_type_specifier_template_id(namedtuple('simple_type_specifier_template_id', ['nested_name_specifier', 'simple_template_id'])):
  format = '{0}template {1}'
  @splitter
  def split(cls, ctx, line):
    spec, rest = nested_name_specifier.split(ctx, line)
    if spec:
      template, rest = word.split(ctx, rest, require='template')
      if template:
        i, rest = simple_template_id.split(ctx, rest)
        if i:
          return cls(spec, i), rest

class simple_type_specifier(maxalternative('simple_type_specifier',
                                         simple_type_specifier_template_name,
                                         simple_type_specifier_template_id,
                                         lambda: placeholder_type_specifier,
                                         computed_type_specifier,
                                         lambda: keyword_type_specifier,
                                         simple_type_specifier_type_name,                                           
                                         )):
  """
  nested-name-specifier? type-name
  nested-name-specifier template simple-template-id
  computed-type-specifier
  placeholder-type-specifier
  nested-name-specifier? template-name

  keyword-type-specifier
    char
    char8_t
    char16_t
    char32_t
    wchar_t
    bool
    short
    int
    long
    signed
    unsigned
    float
    double
    void
  """


class friend_type_specifier(alternatives('friend_type_specifier',
                                         simple_type_specifier,
                                         elaborated_type_specifier,
                                         typename_specifier)):
  """
  simple-type-specifier
  elaborated-type-specifier
  typename-specifier
  """

class friend_type_specifier_dots(item_optional_dots(friend_type_specifier)):
  """
  friend-type-specifier ...?
  """

class friend_type_specifier_list(pair_or_item('friend_type_specifier_list', ',', friend_type_specifier_dots)):
  """
  friend-type-specifier ...?
  friend-type-specifier-list , friend-type-specifier ...?
  """  

  
class concept_name(namedtuple('concept_name')):
  @splitter
  def split(cls, ctx, line):
    n, rest = identifier.split(ctx, line)
    if n:
      return cls(n), rest

class type_constraint_template_arguments(namedtuple('type_constraint_template_arguments', ['nested_name_specifier', 'concept_name', 'template_argument_list'])):
  """
  nested-name-specifier? concept-name < template-argument-list? >
  """
  format = '{0} {1} <{2}>'
  @splitter
  def split(cls, ctx, line):
    s, rest = nested_name_specifier.split(ctx, line)
    n, rest = concept_name.split(ctx, rest)
    if n and startswith_token(rest, '<'):
      rest = rest[1:].lstrip()
      if startswith_token(rest, '>'):
        return cls(s, n, None), rest[1:].lstrip()
      # https://timsong-cpp.github.io/cppwp/temp.names#4
      raw, rest = split_until(rest[1:].lstrip(), '>')
      if raw:
        lst, rest2 = template_argument_list.split(ctx, raw)
        if lst and rest2 == '':
          return cls(s, n, lst), rest

class type_constraint_simple(namedtuple('type_constraint_simple', ['nested_name_specifier', 'concept_name'])):
  """
  nested-name-specifier? concept-name
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    s, rest = nested_name_specifier.split(ctx, line)
    n, rest = concept_name.split(ctx, rest)
    if n:
      return cls(s, n), rest

class type_constraint(namedtuple('type_constraint')):
  """
  nested-name-specifier? concept-name
  nested-name-specifier? concept-name < template-argument-list? >
  """
  @classmethod
  def alternatives(cls):
    return (
      type_constraint_template_arguments,
      type_constraint_simple,
      )

class placeholder_type_specifier_auto(namedtuple('placeholder_type_specifier_auto', ['unused'])):
  """
  auto
  """
  format = 'auto'
  @splitter
  def split(cls, ctx, line):
    auto, rest = word.split(ctx, line, require='auto')
    if auto:
      return cls(None), rest

class placeholder_type_specifier_decltype_auto(namedtuple('placeholder_type_specifier_decltype_auto')):
  """
  decltype(auto)
  """
  format = 'decltype(auto)'
  @splitter
  def split(cls, ctx, line):
    decltype, rest = word.split(ctx, line, require='decltype')
    if decltype and startswith_token(rest, '('):
      auto, rest = word.split(ctx, rest, require='auto')
      if auto and startswith_token(rest, ')'):
        return cls(None), rest[1:].lstrip()

class placeholder_type_specifier_item(alternatives('placeholder_type_specifier_item',
                                                   placeholder_type_specifier_auto,
                                                   placeholder_type_specifier_decltype_auto,
                                                   )):
  """
  auto
  decltype(auto)
  """

    
class placeholder_type_specifier(item_optional_prefix(placeholder_type_specifier_item, type_constraint)):
  """
  type-constraint ﻿? auto
  type-constraint ﻿? decltype(auto)
  """

class keyword_type_specifier(namedtuple('keyword_type_specifier')):

  keyword_types = [
    ('bool',),
    ('char',),
    ('char8_t',),
    ('char16_t',),
    ('char32_t',),
    ('wchar_t',),
    ('signed',),
    ('signed', 'char'),
    ('signed', 'long'),
    ('signed', 'long', 'long'),
    ('signed', 'long', 'long', 'int'),
    ('signed', 'int'),
    ('signed', 'short'),
    ('signed', 'short', 'int'),
    ('unsigned',),
    ('unsigned', 'char'),
    ('unsigned', 'long'),
    ('unsigned', 'long', 'long'),
    ('unsigned', 'long', 'long', 'int'),
    ('unsigned', 'int'),
    ('unsigned', 'short'),
    ('unsigned', 'short', 'int'),
    ('short',),
    ('short', 'int'),
    ('short', 'unsigned'),
    ('short', 'signed'),
    ('short', 'unsigned', 'int'),
    ('short', 'signed', 'int'),
    ('long',),
    ('long', 'int'),
    ('long', 'unsigned'),
    ('long', 'signed'),
    ('long', 'unsigned', 'int'),
    ('long', 'signed', 'int'),
    ('long', 'double'),
    ('long', 'long'),
    ('long', 'long', 'int'),
    ('long', 'long', 'unsigned'),
    ('long', 'long', 'signed'),
    ('long', 'long', 'unsigned', 'int'),
    ('long', 'long', 'signed', 'int'),
    ('int',),
    ('float',),
    ('double',),
    ('void',),
  ]
    
  @splitter
  def split(cls, ctx, line):
    tname, rest = word.split(ctx, line)
    if tname:
      t = (tname,)
      if t in cls.keyword_types:
        while True:
          tname2, rest2 = word.split(ctx, rest)
          t2 = t + (tname2,)
          if tname2 and t2 in cls.keyword_types:
            t, rest = t2, rest2
          else:
            break
        return cls(t), rest

class decl_keyword_specifiers(namedtuple('decl_keyword_specifiers')):
  @classmethod
  def split_keywords(cls):
    return ('inline', 'virtual', 'explicit', 'friend', 'constexpr', 'constinit', 'consteval', 'typedef')

class storage_class_specifier(namedtuple('storage_class_specifier')):
  """
  static
  thread_local
  extern
  mutable

  https://timsong-cpp.github.io/cppwp/dcl.stc#nt:storage-class-specifier

  register
  """
  @classmethod
  def split_keywords(cls):
    return ('register', 'static', 'thread_local', 'extern', 'mutable')

class defining_type_specifier(alternatives('defining_type_specifier',
                                           cv_qualifier,
                                           class_specifier,
                                           enum_specifier,
                                           lambda: typename_specifier,
                                           lambda: elaborated_type_specifier,
                                           lambda: simple_type_specifier,
                                           )):
  """
  type-specifier
  class-specifier
  enum-specifier
  """
  @classmethod
  def postprocess(cls, ctx, item, rest):
    if not isinstance(item, cv_qualifier) and item:
      item = cls(item)
    return item, rest
  
class function_specifier(alternatives('function_specifier', explicit_specifier, lambda: virt_specifier)):
  """
  virtual
  explicit-specifier
  """

class decl_specifier(alternatives('decl_specifier',
                                  storage_class_specifier,
                                  function_specifier,
                                  defining_type_specifier,
                                  decl_keyword_specifiers,)):
  """
  storage-class-specifier
  defining-type-specifier
  function-specifier
    virtual
    explicit
    explicit (constant-expression)  # NOT IMPL
  friend
  typedef
  constexpr
  consteval
  constinit
  inline

  https://timsong-cpp.github.io/cppwp/dcl.spec.general#nt:decl-specifier-seq
  """

def _is_defining_type_specifier(item):
  return 'defining_type_specifier' in getattr(item, "_alt_path", ()) and not isinstance(item, cv_qualifier)

def _is_noptr_declarator(item):
  return 'noptr_declarator' in getattr(item, "_alt_path", ())

def _is_cv_qualifier(item):
  return isinstance(item, cv_qualifier)


class decl_specifier_seq(namedtuple('decl_specifier_seq')):
  """
  decl-specifier attribute-specifier-seq?
  decl-specifier decl-specifier-seq
  """

  @splitter
  def split(cls, ctx, line, has_type_specifier=False):
    return specifier_seq_split(cls, ctx, defining_type_specifier, decl_specifier, line, has_type_specifier=has_type_specifier)

  @splitter
  def __split(cls, ctx, line, parent=None):
    def validate_item(lst, p, rest):

      if _is_defining_type_specifier(p):
        # https://timsong-cpp.github.io/cppwp/dcl.spec.general#3
        for item in lst:
          if _is_defining_type_specifier(item):
            return False

        # detect constructors, if found, return False:
        if parent in {parameter_declaration, structured_binding_declaration, simple_declaration_1}:
          # TODO: what if constructor declarator is defined outside class definition?
          pass
        elif lst and [item for item in lst if isinstance(item, decl_keyword_specifiers) and item[0] == 'typedef']:
          # typedef does not declare constructors
          pass
        elif startswith_token(rest, '('):
          # look ahead for function declarators
          fdecl, rest_ = ptr_operator_declarator.split(ctx, rest[1:].lstrip())
          if fdecl and rest_.startswith(')') and rest_[1:].strip().startswith('('):
            pass
          else:
            # p is likely a constructor declarator name
            # TODO: test
            print(f'NOTOK: {lst=} {p=} {parent.__name__} {rest=}')
            return False
  
        #if lst and [item for item in lst if isinstance(item, decl_keyword_specifiers) and item[0] == 'typedef']:
        #  # typedef does not declare constructors
        #  return p is not None

        if 1:
          pass
        elif parent in {parameter_declaration, structured_binding_declaration, simple_declaration_1}:
          pass
        elif isinstance(p, type_specifier) and not isinstance(p.wrapped, cv_qualifier):
          # p cannot be a constructor
          print(f'{lst=} {p=} {parent.__name__} {rest=}')
          pass
        elif startswith_token(rest, '('):
          print(f'{lst=} {p=} {parent.__name__} {rest=}')
          # here we just want to detect constructors
          return False
      print(f'OK: {lst=} {p=} {parent.__name__} {rest=}')
      return p is not None

    lst, rest = consume_to_list(ctx, decl_specifier.split, line, validate_item=validate_item)
    if lst is not None:
      print(f'{lst=}')
      return cls(tuple(lst)), rest

##########################################################
#                                                        #
#                  Declarations                          #
#                                                        #
##########################################################

class nodeclspec_function_declaration(namedtuple('nodeclspec_function_declaration', ['attribute_specifier_seq', 'declarator'])):
  """
  attribute-specifier-seq? declarator ;
  """
  format = '{0} {1};'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    d, rest = declarator.split(ctx, rest)
    if d and rest.startswith(';'):
      return cls(a, d), rest[1:].lstrip()

class enclosing_namespace_specifier(namedtuple('enclosing_namespace_specifier')):
  """
  identifier
  enclosing-namespace-specifier :: inline? identifier
  """
  @classmethod
  def alternatives(cls):
    return (
        identifier,)

  
class module_import_declaration(namedtuple('module_import_declaration', ['name', 'attribute_specifier_seq'])):
  """
  import-keyword module-name attribute-specifier-seq? ;
  import-keyword module-partition attribute-specifier-seq? ;
  import-keyword header-name attribute-specifier-seq? ;
  """
  format = 'import {0} {1};'
  @splitter
  def split(cls, ctx, line):
    imp, rest = word.split(ctx, line, require='import')
    if imp:
      for ncls in [module_name, module_partition, header_name]:
        n, rest2 = ncls.split(ctx, rest)
        if n:
          a, rest2 = attribute_specifier_seq.split(ctx, rest2)
          if rest2.startswith(';'):
            return cls(n, a), rest2[1:].lstrip()


class name_declaration(namedtuple('name_declaration')):
  """
  block-declaration
  nodeclspec-function-declaration
  function-definition
  friend-type-declaration
  template-declaration
  deduction-guide
  linkage-specification
  namespace-definition
  empty-declaration
  attribute-declaration
  module-import-declaration
  """
  @classmethod
  def alternatives(cls):
    return (
      friend_type_declaration,
      block_declaration,
      nodeclspec_function_declaration,
      template_declaration,
      function_definition,
      deduction_guide,
      linkage_specification,
      namespace_definition,
      empty_declaration,
      attribute_declaration,
      module_import_declaration,
      )

class explicit_instantiation(namedtuple('explicit_instantiation', ['extern', 'declaration'])):
  """
  extern? template declaration
  """
  format = '{0} template {1}'
  @splitter
  def split(cls, ctx, line):  
    extern, rest = word.split(ctx, line, require='extern')
    template, rest = word.split(ctx, rest, require='template')
    if template:
      d, rest = declaration.split(ctx, rest)
      if d:
        return cls(extern, d), rest

class explicit_specialization(namedtuple('explicit_specialization')):
  format = 'template<> {0}'
  @splitter
  def split(cls, ctx, line):
    template, rest = word.split(ctx, line, require='template')
    if template and startswith_token(rest, '<'):
      rest = rest[1:].lstrip()
      if startswith_token(rest, '>'):
        d, rest = declaration.split(ctx, rest[1:].lstrip())
        if d:
          return cls(d), rest

class export_declaration_name(namedtuple('export_declaration_name')):
  format = 'export {0}'
  @splitter
  def split(cls, ctx, line):
    export, rest = word.split(ctx, line, require='export')
    if export:
      n, rest = name_declaration.split(ctx, rest)
      if n:
        return cls(n), rest

class export_declaration_seq(namedtuple('export_declaration_seq')):
  format = 'export { {0} }'
  @splitter
  def split(cls, ctx, line):
    export, rest = word.split(ctx, line, require='export')
    if export and startswith_token(rest, '{'):
      raw, rest = split_until(rest[1:].lstrip(), '}')
      s, rest2 = declaration_seq.split(ctx, raw)
      if s:
        assert rest2 == '', rest2
        return cls(s), rest

class export_declaration_module_import(namedtuple('export_declaration_module_import')):
  format = 'export {0}'
  @splitter
  def split(cls, ctx, line):
    export, rest = word.split(ctx, line, require='export')
    if export:
      n, rest = module_import.split(ctx, rest)
      if n:
        return cls(n), rest

      
class export_declaration(namedtuple('export_declaration')):
  """
  export name-declaration
  export { declaration-seq }
  export module-import-declaration
  """
  @classmethod
  def alternatives(cls):
    return (
      export_declaration_name,
      export_declaration_seq,
      export_declaration_module_import
    )

class special_declaration(namedtuple('special_declaration')):
  """
  explicit-instantiation
  explicit-specialization
  export-declaration
  """
  @classmethod
  def alternatives(cls):
    return (
      explicit_instantiation,
      explicit_specialization,
      export_declaration,
      )
  
class declaration(alternatives('declaration',
                               name_declaration,
                               special_declaration,)):
  """
  name-declaration
  special-declaration
  """

class asm_declaration(namedtuple('asm_declaration', ['attribute-specifier-seq', 'balanced-token-seq'])):
  """
  attribute-specifier-seq? asm ( balanced-token-seq ) ;
  """
  format = '{0} asm ({1});'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    asm, rest = word.split(ctx, line, require='asm')
    if asm and startswith_token(rest, '('):
      seq, rest = balanced_token_seq.split(ctx, rest[1:].lstrip())
      if seq and startswith_token(rest, ')'):
        return cls(a, seq), rest[1:].lstrip()

class qualified_namespace_specifier(item_optional_prefix(namespace_name, nested_name_specifier)):
  """
  nested-name-specifier?
  namespace-name
  """

class namespace_alias_definition(namedtuple('namespace_alias_definition', ['identifier', 'qualified-namespace-specifier'])):
  """
  namespace identifier = qualified-namespace-specifier ;
  """
  format = 'namespace {0} = {1};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    ns, rest = word.split(ctx, line, require='namespace')
    if ns:
      i, rest = identifier.split(ctx, rest)
      if i and startswith_token(rest, '='):
        s, rest = qualified_namespace_specifier.split(ctx, rest[1:].lstrip())
        if s:
          return cls(i, s), rest


class template_template_parameter_list(namedtuple('template_template_parameter_list')):
  """
  template < template-parameter-list >
  """
  def __str__(self):
    return f'template < {self.content} >'
  @splitter
  def split(cls, ctx, line):
    template, rest = word.split(ctx, line, require='template')
    if template and startswith_token(rest, '<'):
      raw, rest = split_until(rest[1:].lstrip(), '>')
      if raw is not None:
        tparams, rest2 = template_parameter_list.split(ctx, raw)
        if tparams is not None:
          return cls(tparams), rest

class lvalue_reference_type(namedtuple('lvalue_reference_type')):
  pass

class integral_type(namedtuple('integral_type')):
  @splitter
  def split(cls, ctx, line):
    return integer_types.split(ctx, line)

class pointer_type(namedtuple('pointer_type')):
  pass

class pointer_to_member_type(namedtuple('pointer_to_member_type')):
  pass

class enumeration_type(namedtuple('enumeration_type')):
  pass

class null_ptr_t(namedtuple('null_ptr_t')):
  pass

class floating_point_type(namedtuple('floating_point_type')):
  pass

class lambda_closure_type(namedtuple('lambda_closure_type')):
  pass

class non_closure_literal_class_type(namedtuple('non_closure_literal_class_type')):
  pass

class structural_type(namedtuple('structural_type')):
  @classmethod
  def alternatives(cls):
    return (
        integral_type,
        lvalue_reference_type,
        pointer_type,
        pointer_to_member_type,
        enumeration_type,
        null_ptr_t,
        floating_point_type,
        lambda_closure_type,
        non_closure_literal_class_type,
    )[:1]

class contains_placeholder_type(namedtuple('contains_placeholder_type')):
  pass

class placeholder_for_deduced_class_type(namedtuple('placeholder_for_deduced_class_type')):
  @classmethod
  def alternatives(cls):
    return (identifier,)

class non_type_template_type(namedtuple('non_type_template_type')):
  @classmethod
  def alternatives(cls):
    return (
        structural_type,
        placeholder_for_deduced_class_type,
        contains_placeholder_type,

    )[:2]

class default_template_argument(namedtuple('default_template_argument')):
  @classmethod
  def alternatives(cls):
    return (
        template_parameter,
        constant_expression,
    )

class type_template_parameter_name(namedtuple('type_template_parameter', ['kind', 'name', 'default'])):
  """
  name ﻿(optional)	(1)	
  name ﻿(optional) = default	(2)	
  ... name ﻿(optional)	(3)	(since C++11)
  """

  @property
  def format(self):
    if self.kind == '(1)':
      return '{1}'
    elif self.kind == '(2)':
      return '{1} = {2}'
    elif self.kind == '(3)':
      return '... {1}'
    else:
      assert 0  # unreachable

  @splitter
  def split(cls, ctx, line):
    d = None
    if line.startswith('...'):
      kind = '(3)'
      n, rest = identifier.split(ctx, line[3:].lstrip())
    else:
      n, rest = identifier.split(ctx, line.lstrip())
      if startswith_token(rest, '='):
        d, rest = default_template_argument.split(ctx, rest[1:].lstrip())
        kind = '(2)'
      else:
        kind = '(1)'
    return cls(kind, n, d), rest

class non_type_template_parameter(namedtuple('non_type_template_parameter', ['type', 'name'])):
  """
  type name ﻿(optional)	(1)	
  type name ﻿(optional) = default	(2)	
  type ... name ﻿(optional)	(3)
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    key, rest = non_type_template_type.split(ctx, line)
    if key:
      n, rest = type_template_parameter_name.split(ctx, rest)
      return cls(key, n), rest


class type_parameter_key(namedtuple('type_parameter_key')):

  @classmethod
  def split_keywords(cls):
    return ('typename', 'class')


class type_template_parameter(namedtuple('type_template_parameter', ['type_parameter_key', 'name'])):
  """
  type-parameter-key name ﻿(optional)	(1)	
  type-parameter-key name ﻿(optional) = default	(2)	
  type-parameter-key ... name ﻿(optional)	(3)	(since C++11)
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    key, rest = type_parameter_key.split(ctx, line)
    if key:
      n, rest = type_template_parameter_name.split(ctx, rest)
      return cls(key, n), rest

class constraint_type_template_parameter(namedtuple('constraint_type_template_parameter', ['type_constraint', 'name'])):
  """
  type-constraint name ﻿(optional)	(4)	(since C++20)
  type-constraint name ﻿(optional) = default	(5)	(since C++20)
  type-constraint ... name ﻿(optional)	(6)	
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    key, rest = type_contraint.split(ctx, line)
    if key:
      n, rest = type_template_parameter_name.split(ctx, rest)
      return cls(key, n), rest

class template_template_parameter(namedtuple('template_template_parameter')):
  pass

def _type_parameter_id_split(ctx, rest, id_split):
  """
  ...? identifier?
  identifier? = type-id
  """
  if rest.startswith('...'):
    dots = rest[:3]
    rest = rest[3:].lstrip()
  else:
    dots = None
  i, rest = identifier.split(ctx, rest)
  if i and startswith_token(rest, '='):
    assert dots is None
    t, rest = id_split(ctx, rest[1:].lstrip())
  else:
    if startswith_token(rest, '='):
      t, rest = id_split(ctx, rest[1:].lstrip())
    else:
      t = None
  return dots, i, t, rest

  
class type_parameter_with_key(namedtuple('type_parameter_with_key', ['type_parameter_key', 'dots', 'identifier', 'type_id'])):
  """See type_parameter.
  """
  @property
  def format(self):
    if self.typeid:
      return '{0} {2} = {3}'
    return '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    k, rest = type_parameter_key.split(ctx, line)
    if k:
      dots, i, t, rest = _type_parameter_id_split(ctx, rest, type_id.split)
      return cls(k, dots, i, t), rest


class type_parameter_with_constraint(namedtuple('type_parameter_with_key', ['type_constraint', 'dots', 'identifier', 'type_id'])):
  """See type_parameter.
  """
  @property
  def format(self):
    if self.typeid:
      return '{0} {2} = {3}'
    return '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    k, rest = type_constraint.split(ctx, line)
    if k:
      dots, i, t, rest = _type_parameter_id_split(ctx, rest, type_id.split)
      return cls(k, dots, i, t), rest


class type_parameter_with_template_key(namedtuple('type_parameter_with_template_key', ['template_head', 'type_parameter_key', 'dots', 'identifier', 'type_id'])):
  """See type_parameter.
  """
  @property
  def format(self):
    if self.typeid:
      return '{0} {1} {2} = {4}'
    return '{0} {1} {2} {3}'

  @splitter
  def split(cls, ctx, line):
    h, rest = template_head.split(ctx, line)
    if h:
      k, rest = type_parameter_key.split(ctx, rest)
      if k:
        dots, i, t, rest = _type_parameter_id_split(ctx, rest, id_expression.split)
        return cls(h, k, dots, i, t), rest

class type_parameter(namedtuple('type_parameter')):
  """
  type-parameter-key ...? identifier?
  type-parameter-key identifier? = type-id

  type-constraint ...? identifier?
  type-constraint identifier? = type-id

  template-head type-parameter-key ...? identifier?
  template-head type-parameter-key identifier? = id-expression
  """
  @classmethod
  def alternatives(cls):
    return (
      type_parameter_with_key,
      type_parameter_with_template_key,
      type_parameter_with_constraint,
      
    )

class non_type_parameter(namedtuple('non_type_parameter', ['decl_specifier_seq', 'abstract_declarator', 'initializer_clause'])):
  """non-type template parameter support

  - a structural type
    - a scalar type
    - an lvalue reference type
    - a literal class type with the following properties:
      - all base classes and non-static data members are public and non-mutable
      - the types of all bases classes and non-static data members are structural types or (possibly multidimensional) array thereof.
  - a type that contains a placeholder type ([dcl.spec.auto])
  - a placeholder for a deduced class type ([dcl.type.class.deduct]).

  https://timsong-cpp.github.io/cppwp/temp.arg.nontype#ntref:template-parameter

  type name ﻿(optional)	(1)	
  type name ﻿(optional) = default	(2)	
  type ... name ﻿(optional)	(3)

  https://en.cppreference.com/w/cpp/language/template_parameters

  Using parameter_declaration analogy:
    decl-specifier-seq abstract-declarator?
    decl-specifier-seq abstract-declarator? = initializer-clause
  """
  @property
  def format(self):
    if self.initializer_clause:
      return '{0} {1} = {2}'
    return '{0} {1}'

  @splitter
  def split(cls, ctx, line):
    seq, rest = decl_specifier_seq.split(ctx, line)

    if seq:
      if startswith_token(rest, '='):
        i, rest = initializer_clause.split(ctx, rest[1:].lstrip())
        if i:
          return cls(seq, None, i), rest
      else:
        d, rest = declarator.split(ctx, rest)
        if not d:
          d, rest = abstract_declarator.split(ctx, rest)

        if startswith_token(rest, '='):
          i, rest = initializer_clause.split(ctx, rest[1:].lstrip())
        else:
          i = None

        return cls(seq, d, i), rest

class template_parameter(namedtuple('template_parameter')):
  """
  See https://en.cppreference.com/w/cpp/language/template_parameters

  type-parameter
  parameter-declaration
  """
  @classmethod
  def alternatives(cls):
    return (
      non_type_parameter,
      type_parameter,
      parameter_declaration,

    )
  
class template_parameter_list(pair_or_item('template_parameter_list', ',', template_parameter)):
  """
  template-parameter
  template-parameter-list , template-parameter
  """
  # TODO: https://timsong-cpp.github.io/cppwp/temp.param#note-1

class defining_type_specifier_seq(namedtuple("defining_type_specifier_seq")):
  """
  defining-type-specifier attribute-specifier-seq?
  defining-type-specifier defining-type-specifier-seq
  """
  @splitter
  def split(cls, ctx, line):
    return specifier_seq_split(cls, ctx, defining_type_specifier, defining_type_specifier, line)


class defining_type_id(namedtuple('defining_type_id', ['defining_type_specifier_seq', 'abstract_declarator'])):
  """
  defining-type-specifier-seq abstract-declarator?
  """
  @splitter
  def split(cls, ctx, line):
    seq, rest = defining_type_specifier_seq.split(ctx, line)
    if seq:
      d, rest = abstract_declarator.split(ctx, rest)
      return cls(seq, d), rest
    
class alias_declaration(namedtuple('alias_declaration', ['identifier', 'attribute_specifier_seq', 'defining_type_id'])):
  """
  using identifier attribute-specifier-seq? = defining-type-id ;
  """
  format = 'using {0} {1} = {2} ;'

  @splitter
  def split(cls, ctx, line):
    using, rest = word.split(ctx, line, require='using')
    if using:
      i, rest = identifier.split(ctx, rest)
      if i:
        a, rest = attribute_specifier_seq.split(ctx, rest)
        if startswith_token(rest, '='):
          t, rest = defining_type_id.split(ctx, rest[1:].lstrip())
          if t:
            return cls(i, a, t), rest

class qualified_id(namedtuple('qualified_id', ['nested_name_specifier', 'template', 'unqualified_id'])):
  """
  nested-name-specifier template? unqualified-id
  """
  format = '{0}{1} {2}'
  @splitter
  def split(cls, ctx, line):
    s, rest = nested_name_specifier.split(ctx, line)
    if s:
      template, rest = word.split(ctx, rest, require='template')
      i, rest = unqualified_id.split(ctx, rest)
      if i:
        return cls(s, template, i), rest

class operator_function_id(namedtuple('operator_function_id')):
  """
  operator operator
  """
  format = 'operator {0}'
  @splitter
  def split(cls, ctx, line):
    op_, rest = word.split(ctx, line, require='operator')
    if op_:
      for op in operators:
        if rest.startswith(op):
          rest = rest[len(op):].lstrip()
          if op in {'new', 'delete'}:
            if startswith_token(rest, '['):
              rest = rest[1:].lstrip()
              if startswith_token(rest, ']'):
                rest = rest[1:].lstrip()
                op = op + '[]'
              else:
                assert 0  # unreachable
          return cls(op), rest
      if startswith_token(rest, '('):
        rest = rest[1:].lstrip()
        if startswith_token(rest, ')'):
          rest = rest[1:].lstrip()
          return cls('()'), rest
      if startswith_token(rest, '['):
        rest = rest[1:].lstrip()
        if startswith_token(rest, ']'):
          rest = rest[1:].lstrip()
          return cls('[]'), rest

class conversion_declarator(namedtuple('conversion_declarator', ['ptr_operator', 'conversion_declarator'])):
  """
  ptr-operator conversion-declarator?
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    p, rest = ptr_operator.split(ctx, line)
    if p:
      d, rest = conversion_declarator.split(ctx, rest)
      return cls(p, d), rest

class conversion_type_id(namedtuple('conversion_type_id', ['type_specifier_seq', 'conversion_declarator'])):
  """
  type-specifier-seq conversion-declarator?
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    s, rest = type_specifier_seq.split(ctx, line)
    if s:
      d, rest = conversion_declarator.split(ctx, rest)
      return cls(s, d), rest
  
class conversion_function_id(namedtuple('conversion_function_id')):
  """
  operator conversion-type-id
  """
  format = 'operator {0}'
  @splitter
  def split(cls, ctx, line):
    op_, rest = word.split(ctx, line, require='operator')
    if op_:
      i, rest = conversion_type_id.split(ctx, rest)
      if i:
        return cls(i), rest

class literal_operator_id(namedtuple('literal_operator_id', ['string_or_literal', 'identifier'])):
  """
  operator unevaluated-string identifier
  operator user-defined-string-literal
  """
  format = 'operator {0} {1}'
  @splitter
  def split(cls, ctx, line):
    op_, rest = word.split(ctx, line, require='operator')
    if op_:
      s, rest = string_literal.split(ctx, rest)
      if s:
        i, rest = identifier.split(ctx, rest)
        if i:
          return cls(s, i)
      else:
        s, rest = user_defined_string_literal.split(ctx, rest)
        if s:
          return cls(s, None), rest

class type_name_with_tilde(namedtuple('type_name_with_tilde')):
  format = '~{0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('~'):
      rest = line[1:].lstrip()
      n, rest = type_name.split(ctx, rest)
      if n:
        return cls(n), rest

class computed_type_specifier_with_tilde(namedtuple('computed_type_specifier_with_tilde')):
  format = '~{0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('~'):
      rest = line[1:].lstrip()
      n, rest = computed_type_specifier.split(ctx, rest)
      if n:
        return cls(n), rest

class operator_function_template_id(namedtuple('operator_function_template_id', ['operator_function_id', 'template_argument_list'])):
  format = '{0}<{1}>'
  @splitter
  def split(cls, ctx, line):
    o, rest = operator_function_id.split(ctx, line)
    if o and startswith_token(rest, '<'):
      # https://timsong-cpp.github.io/cppwp/temp.names#4
      raw, rest = split_until(rest[1:].lstrip(), '>')
      lst, rest2 = template_argument_list.split(ctx, raw)
      if lst:
        assert rest2 == '', rest2
        return cls(o, lst), rest

class literal_operator_template_id(namedtuple('literal_operator_template_id', ['literal_operator_id', 'template_argument_list'])):
  format = '{0}<{1}>'
  @splitter
  def split(cls, ctx, line):
    o, rest = literal_operator_id.split(ctx, line)
    if o and startswith_token(rest, '<'):
      # https://timsong-cpp.github.io/cppwp/temp.names#4
      raw, rest = split_until(rest[1:].lstrip(), '>')
      lst, rest2 = template_argument_list.split(ctx, raw)
      if lst:
        assert rest2 == '', rest2
        return cls(o, lst), rest
      
class template_id(namedtuple('template_id')):
  """
  simple-template-id
  operator-function-id < template-argument-list? >
  literal-operator-id < template-argument-list? >

  https://timsong-cpp.github.io/cppwp/temp.names#nt:template-id
  """
  @classmethod
  def alternatives(cls):
    return (simple_template_id,
            operator_function_template_id,
            literal_operator_template_id
            )

  @classmethod
  def postprocess(cls, ctx, item, rest):
    # How to avoid matching `bool a = x < 0 && a > y` as `bool a = x<0 && a>` + `y`
    return item, rest
    
  
class unqualified_id(namedtuple('unqualified_id')):
  """
  identifier
  operator-function-id
  conversion-function-id
  literal-operator-id
  ~ type-name
  ~ computed-type-specifier
  template-id

  https://timsong-cpp.github.io/cppwp/expr.prim.id.unqual#nt:unqualified-id
  """
  @classmethod
  def alternatives(cls):
    return (
      conversion_function_id,
      operator_function_id,
      literal_operator_id,
      type_name_with_tilde,
      computed_type_specifier_with_tilde,
      template_id,
      identifier,  # anyidentifier
    )

class using_declarator(namedtuple('using_declarator', ['typename', 'nested_name_specifier', 'unqualified_id'])):
  """
  typename? nested-name-specifier unqualified-id
  """
  format = '{0} {1} {2}'

  @splitter
  def split(cls, ctx, line):
    typename, rest = word.split(ctx, line, require='typename')
    spec, rest = nested_name_specifier.split(ctx, rest)
    if spec:
      i, rest = unqualified_id.split(ctx, rest)
      if i:
        return cls(typename, spec, i), rest

class using_declarator_dots(item_optional_dots(using_declarator)):
  """
  using-declarator ...?
  """

class using_declarator_list(pair_or_item('using_declarator_list', ',', using_declarator_dots)):
  """
  using-declarator ...?
  using-declarator-list , using-declarator ...?
  """
      
class using_declaration(namedtuple('using_declaration')):
  """
  using using-declarator-list ;
  """
  format = 'using {0} ;'

  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    using, rest = word.split(ctx, line, require='using')
    if using:
      lst, rest = using_declarator_list.split(ctx, rest)
      if lst:
        return cls(lst), rest

class using_directive(namedtuple('using_directive', ['attribute_specifier_seq', 'nested_name_specifier', 'namespace_name'])):
  """
  attribute-specifier-seq? using namespace nested-name-specifier? namespace-name ;
  """
  format = '{0} using namespace {1} {2} ;'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    using, rest = word.split(ctx, rest, require='using')
    namespace, rest = word.split(ctx, rest, require='namespace')
    if using and namespace:
      ns, rest = nested_name_specifier.split(ctx, rest)
      n, rest = namespace_name.split(ctx, rest)
      if n and rest.startswith(';'):
        return cls(a, ns, n), rest[1:].lstrip()

class using_enum_declarator(namedtuple('using_enum_declarator')):
  """
  nested-name-specifier? identifier
  nested-name-specifier? simple-template-id
  """
  @splitter
  def split(cls, ctx, line):
    s, rest = nested_name_specifier.split(ctx, line)
    for icls in (simple_template_id, identifier):
      i, rest = icls.split(ctx, rest)
      if i:
        return cls(s, i), rest

class using_enum_declaration(namedtuple('using_enum_declaration')):
  """
  using enum using-enum-declarator ;
  """
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    using, rest = word.split(ctx, line, require='using')
    enum, rest = word.split(ctx, rest, require='enum')
    if using and enum:
      return using_enum_declarator.split(ctx, rest)

class basic_s_char(namedtuple('basic_s_char')):
  """
  any member of the translation character set except the U+0022
  quotation mark, U+005c reverse solidus, or new-line character
  """
  @splitter
  def split(cls, ctx, line):
    c = str(line[0])
    if c == '\n' or c == '\\' or c == '"':
      return
    return cls(line[0]), line[1:]
    
class s_char(alternatives('s_char',
                          basic_s_char,
                          escape_sequence,
                          universal_character_name)):
  """
  basic-s-char
  escape-sequence
  universal-character-name
  """
    
class s_char_sequence(item_sequence('s_char_sequence', s_char)):
  """
  s-char
  s-char-sequence s-char
  """

class ordinary_string_literal_quotes(namedtuple('ordinary_string_literal_quotes')):
  '''
  " s-char-sequence? "
  '''
  format = '"{0}"'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('"'):
      rest = line[1:]
      if startswith_token(rest, '"'):
        return cls(None), rest[1:].lstrip()
      s, rest = s_char_sequence.split(ctx, rest)
      if startswith_token(rest, '"'):
        return cls(s), rest[1:].lstrip()

  @classmethod
  def postprocess(cls, ctx, item, rest):
    if startswith_token(rest, '"'):
      item2, rest = cls.split(ctx, rest)
      if item2:
        return cls(item.content + item2.content), rest
    return item, rest
      
class raw_string(namedtuple("raw_string", ['d-char-sequence-head', 'r-char-sequence', 'd-char-sequence-tail'])):
  '''
  " d-char-sequence? ( r-char-sequence? ) d-char-sequence? "
  '''
  format = '"{0}({1}){2}"'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('"'):
      rest = line[1:]
      h, rest = d_char_sequence.split(ctx, rest)
      if startswith_token(rest, '('):
        rest = rest[1:]
        r, rest = r_char_sequence.split(ctx, rest)
        if startswith_token(rest, ')'):
          rest = rest[1:]
          t, rest = d_char_sequence.split(ctx, rest)
          if startswith_token(rest, '"'):
            return cls(h, r, t), rest[1:].lstrip()


  
class ordinary_string_literal_raw(namedtuple('ordinary_string_literal_raw')):
  """
  R raw-string
  """
  format = 'R{0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('R'):
      rest = line[1:]
      s, rest = raw_string.split(ctx, line)
      if s:
        return cls(s), rest.lstrip()

class ordinary_string_literal_variants(alternatives(ordinary_string_literal_raw, ordinary_string_literal_quotes)):
  '''
  " s-char-sequence? "
  R raw-string
  '''

class encoding_prefix(namedtuple('encoding_prefix')):
  format = '{0}'
  @splitter
  def split(cls, ctx, line):
    for p in ['u8', 'u', 'U', 'L']:
      if line.startswith(p):
        return cls(p), line[len(p):].lstrip()

class ordinary_string_literal(item_optional_prefix(ordinary_string_literal_variants, encoding_prefix)):
  
  @splitter
  def __split(cls, ctx, line):
    if line.startswith('"'):
      i = line.find('"', 1)
      while line[i - 1].startswith('\\'):
        i = line.find('"', i + 1)
        if i == -1:
          break

      if i != -1:
        while True:
          j = i + 1
          while j < len(line) and line[j].isspace():
            j += 1
          if j < len(line) and line[j].startswith('"'):
            k = line.find('"', j + 1)
            while line[k - 1].startswith('\\'):
              k = line.find('"', k + 1)
              if k == -1:
                break
            if k != -1:
              i = k
              continue
          break
      if i != -1:
        return cls(line[:i + 1]), line[i+1:].lstrip()
    elif line.startswith('R"') and '(' in line:
      p = line[2:line.index('(')]
      i = line.find(')' + p + '"')
      if i != -1:
        return cls(line[:i + 2 + len(p)]), line[i+2 + len(p):].lstrip()

class string_literal(item_optional_prefix(ordinary_string_literal_variants, encoding_prefix)):
  """
  encoding-prefix? " s-char-sequence? "
  encoding-prefix? R raw-string
  """

class unevaluated_string(namedtuple('unevaluated_string')):
  @classmethod
  def alternatives(cls):
    return (string_literal, )

class ud_suffix(namedtuple('ud_suffix')):

  @classmethod
  def alternatives(cls):
    return (identifier, )


class user_defined_string_literal(namedtuple('user_defined_string_literal', ['string_literal', 'ud_suffix'])):
  """
  string-literal ud-suffix
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    s, rest = string_literal.split(ctx, line)
    if s:
      ud, rest = ud_suffix.split(ctx, rest)
      if ud:
        return cls(s, ud), rest

class static_assert_message(alternatives('static_assert_message',
                                         unevaluated_string,
                                         lambda: constant_expression)):
  """
  unevaluated-string
  constant-expression
  """
      
class static_assert_declaration(namedtuple('static_assert_declaration', ['constant_expression', "static_assert_message"])):
  """
  static_assert ( constant-expression ) ;
  static_assert ( constant-expression , static_assert-message ) ;


  static_assert( bool-constexpr , unevaluated-string )	(1)	
  static_assert( bool-constexpr )	(2)
  static_assert( bool-constexpr , constant-expression )	(3)
  """
  @property
  def format(self):
    if self[1] is None:
      return 'static_assert({0});'
    return 'static_assert({0}, {1});'

  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    n, rest = word.split(ctx, line, require='static_assert')
    if n and startswith_token(rest, '('):
      e, rest = constant_expression.split(ctx, rest[1:].lstrip())
      if e:
        if rest.startswith(','):
          m, rest = static_assert_message.split(ctx, rest[1:].lstrip())
        else:
          m = None
        if startswith_token(rest, ')'):
          return cls(e, m), rest[1:].lstrip()
    return
    
    if n and startswith_token(rest, '('):
      bool_constexpr = constant_expression
      raw, rest = split_until(rest[1:].lstrip(), ')')
      if raw is not None:
        string_or_expr = None
        raw_with_comma, raw2 = split_until(raw, ',')
        if raw_with_comma:
          bexpr, rest = bool_constexpr.split(ctx, raw_with_comma)
          s, rest2 = unevaluated_string.split(ctx, raw2)
          if s and rest2 == '':
            string_or_expr = s
          else:
            e, rest2 = constant_expression.split(ctx, raw2)
            if e:
              if rest2 == '':
                string_or_expr = s
              else:
                return UNEXPECTED
          if string_or_expr is None:
            return UNEXPECTED
        else:
          bexpr, rest = bool_constexpr.split(ctx, raw)
        if bexpr is not None:
          return cls(bexpr, string_or_expr), rest


class opaque_enum_declaration(namedtuple('opaque_enum_declaration', ['enum-key', 'attribute-specifier-seq', 'enum-head-name', 'enum-base'])):
  """
  enum-key attribute-specifier-seq? enum-head-name enum-base? ;
  """
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    k, rest = enum_key.split(ctx, line)
    if k:
      a, rest = attribute_specifier_seq.split(ctx, rest)
      h, rest = enum_head_name.split(ctx, rest)
      if h:
        b, rest = enum_base.split(ctx, rest)
        return cls(k, a, h, b), rest

class block_declaration(alternatives('block_declaration',
                                     lambda : (
                                       alias_declaration,
                                       simple_declaration,
                                       asm_declaration,
                                       namespace_alias_definition,
                                       using_declaration,
                                       using_enum_declaration,
                                       using_directive,
                                       static_assert_declaration,
                                       opaque_enum_declaration))):
  """
  simple-declaration
  asm-declaration
  namespace-alias-definition
  using-declaration
  using-enum-declaration
  using-directive
  static_assert-declaration
  alias-declaration
  opaque-enum-declaration
  """

class designator(namedtuple('designator')):
  """
  . identifier
  """
  format = '. {0}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('.'):
      i, rest = identifier.split(ctx, line[1:].lstrip())
      if i:
        return cls(i), rest

  
class designated_initializer_clause(namedtuple('designated_initializer_clause', ['designator', 'brace_or_equal_initializer'])):
  """
  designator brace-or-equal-initializer
  """
  @splitter
  def split(cls, ctx, line):
    d, rest = designator.split(ctx, line)
    if d:
      i, rest = brace_or_equal_initializer.split(ctx, rest)
      if i:
        return cls(d, i), rest


########################################################
#    Expressions
########################################################


class this_expression(namedtuple('this_expression')):
  @classmethod
  def split_keywords(cls):
    return ('this',)

class parenthesis_expression(namedtuple('parenthesis_expression')):
  """
  ( expression )
  """
  format = '({0})'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      e, rest = expression.split(ctx, line[1:].lstrip())
      if e and startswith_token(rest, ')'):
        return cls(e), rest[1:].lstrip()

class capture_default(namedtuple('capture_default')):
  """
  &
  =
  """
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '&') or startswith_token(line, '='):
      return cls(line[0]), line[1:].lstrip()

class simple_capture(namedtuple('simple_capture', ['prefix', 'identifier_or_this', 'dots'])):
  """
    identifier ...?
  & identifier ...?
    this
  * this
  """
  format = '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '&'):
      prefix = line[0]
      rest = line[1:].lstrip()
      i, rest = identifier.split(ctx, rest)
      if i:
        if rest.startswith('...'):
          return cls(prefix, i, rest[:3]), rest[3:].lstrip()
        else:
          return cls(prefix, i, None), rest
    elif startswith_token(line, '*'):
      prefix = line[0]
      rest = line[1:].lstrip()
      this, rest = word.split(ctx, line, require='this')
      if this:
        return cls(prefix, this, None), rest
    else:
      rest = line
      this, rest = word.split(ctx, line, require='this')
      if this:
        return cls(None, this, None), rest
      i, rest = identifier.split(ctx, rest)
      if i:
        if rest.startswith('...'):
          return cls(None, i, rest[:3]), rest[3:].lstrip()
        return cls(None, i, None), rest

class init_capture(namedtuple('init_capture', ['ref', 'dots', 'identifier', 'initializer'])):
  """
    ...? identifier initializer
  & ...? identifier initializer
  """
  format = '{0} {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '&'):
      ref = line[0]
      rest = line[1:].lstrip()
    else:
      ref = None
      rest = line
    if rest.startswith('...'):
      dots = rest[:3]
      rest = rest[3:].lstrip()
    else:
      dots = None
    i, rest = identifier.split(ctx, rest)
    if i:
      init, rest = initializer.split(ctx, rest)
      if init:
        return cls(ref, dots, i, init), rest

class capture(alternatives('capture', init_capture, simple_capture)):
  """
  simple-capture
  init-capture
  """
  
class capture_list(pair_or_item('capture_list', ',', capture)):
  """
  capture
  capture-list , capture
  """

class lambda_capture_default_and_list(namedtuple('lambda_capture_default_and_list', ['capture-default', 'capture-list'])):
  """
  capture-default , capture-list
  """
  format = '{0}, {1}'
  @splitter
  def split(cls, ctx, line):
    d, rest = capture_default.split(ctx, line)
    if d and rest.startswith(','):
      l, rest = capture_list.split(ctx, rest[1:].lstrip())
      if l:
        return cls(d, l), rest

class lambda_capture(alternatives('lambda_capture', capture_list, lambda_capture_default_and_list, capture_default)):
  """
  capture-default
  capture-list
  capture-default , capture-list
  """

class lambda_introducer(namedtuple('lambda_introducer')):
  """
  [ lambda-capture? ]
  """
  format = '[{0}]'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('['):
      rest = line[1:].lstrip()
      if startswith_token(rest, ']'):
        return cls(None), rest[1:].lstrip()
      c, rest = lambda_capture.split(ctx, rest)
      if c:
        assert startswith_token(rest, ']'), rest[:50].tostring()
        return cls(c), rest[1:].lstrip()

class lambda_introducer_template(namedtuple('lambda_introducer_template', ['lambda_introducer', 'template-parameter-list', 'requires-clause'])):
  """
  lambda-introducer < template-parameter-list > requires-clause?
  """
  format = '{0} <{1}> {2}'
  @splitter
  def split(cls, ctx, line):
    i, rest = lambda_introducer.split(ctx, line)
    if i and startswith_token(rest, '<'):
      rest = rest[1:].lstrip()
      raw, rest = split_until(rest, '>')
      lst, rest2 = template_parameter_list.split(ctx, raw)
      if lst:
        assert rest2 == '', rest2[:50]
        r, rest = requires_clause.split(ctx, rest)
        return cls(i, lst, r), rest
        
class lambda_expression_head(alternatives('lambda_expression_head', lambda_introducer_template, lambda_introducer)):
  """
  lambda-introducer
  lambda-introducer < template-parameter-list > requires-clause?
  """

class lambda_expression_head_optional_attribute_specifier_seq(item_optional_suffix(lambda_expression_head, attribute_specifier_seq)):
  """
  lambda_expression_head attribute-specifier-seq?
  """

class lambda_specifier_seq_with_parameter_declaration_clause_and_tails(
    namedtuple('lambda_specifier_seq_with_parameter_declaration_clause_and_tails',
               ['parameter-declaration-clause', 'lambda-specifier-seq', 'noexcept-specifier', 'attribute-specifier-seq', 'trailing-return-type', 'requires-clause'])):
  """
  ( parameter-declaration-clause ) lambda-specifier-seq? noexcept-specifier? attribute-specifier-seq? trailing-return-type? requires-clause?
  """
  format = '({0}) {1} {2} {3} {4} {5}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      c, rest = parameter_declaration_clause.split(ctx, line[1:].lstrip())
      if startswith_token(rest, ')'):
        rest = rest[1:].lstrip()
        seq, rest =  lambda_specifier_seq.split(ctx, rest)
        noexc, rest =  noexcept_specifier.split(ctx, rest)
        a, rest =  attribute_specifier_seq.split(ctx, rest)
        t, rest =  trailing_return_type.split(ctx, rest)
        r, rest =  requires_clause.split(ctx, rest)
        return cls(c, seq, noexc, a, t, r), rest

class lambda_specifier(namedtuple('lambda_specifier')):
  """
  consteval
  constexpr
  mutable
  static
  """
  @classmethod
  def split_keywords(cls):
    return (
      'consteval',
      'constexpr',
      'mutable',
      'static'
    )

class lambda_specifier_seq(pair_or_item('lambda_specifier_seq', '', lambda_specifier)):
  """
  lambda-specifier
  lambda-specifier lambda-specifier-seq
  """
  
class lambda_specifier_seq_with_tails(namedtuple('lambda_specifier_seq_with_tails',
                                      ['lambda-specifier-seq', 'noexcept-specifier', 'attribute-specifier-seq', 'trailing-return-type'])):
  """
  lambda-specifier-seq  noexcept-specifier? attribute-specifier-seq? trailing-return-type?
  """
  format = '{0} {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    seq, rest =  lambda_specifier_seq.split(ctx, line)
    if seq:
      noexc, rest =  noexcept_specifier.split(ctx, rest)
      a, rest =  attribute_specifier_seq.split(ctx, rest)
      t, rest =  trailing_return_type.split(ctx, rest)
      return cls(seq, noexc, a, t), rest

class noexcept_specifier_with_tails(namedtuple('noexcept_specifier_with_tails', ['noexcept-specifier', 'attribute-specifier-seq', 'trailing-return-type'])):
  """
  noexcept-specifier attribute-specifier-seq?  trailing-return-type?
  """
  format = '{0} {1} {2}'
  @splitter
  def split(cls, ctx, line):
    noexc, rest =  noexcept_specifier.split(ctx, line)
    if noexc:
      a, rest =  attribute_specifier_seq.split(ctx, rest)
      t, rest =  trailing_return_type.split(ctx, rest)
      return cls(noexc, a, t), rest

class lambda_declarator(alternatives('lambda_declarator',
                                     lambda_specifier_seq_with_parameter_declaration_clause_and_tails,
                                     lambda_specifier_seq_with_tails,
                                     noexcept_specifier_with_tails,
                                     trailing_return_type
                                     )):
  """
                                   lambda-specifier-seq  noexcept-specifier? attribute-specifier-seq? trailing-return-type?
                                                         noexcept-specifier attribute-specifier-seq?  trailing-return-type?
                                                                                                      trailing-return-type?
  ( parameter-declaration-clause ) lambda-specifier-seq? noexcept-specifier? attribute-specifier-seq? trailing-return-type? requires-clause?
  """

class lambda_declarator_compound_statement(namedtuple('lambda_declarator_compound_statement', ['lambda_declarator', 'compound_statement'])):
  """
  lambda-declarator? compound-statement

  Note that single `trailing-return-type?` makes lambda-declarator optional.
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    d, rest = lambda_declarator.split(ctx, line)
    s, rest = compound_statement.split(ctx, rest)
    if s:
      return cls(d, s), rest

class lambda_expression(sequence('lambda_expression', lambda_expression_head_optional_attribute_specifier_seq, lambda_declarator_compound_statement)):
  """
  lambda-introducer                                              attribute-specifier-seq? lambda-declarator compound-statement
  lambda-introducer < template-parameter-list > requires-clause? attribute-specifier-seq? lambda-declarator compound-statement
  """

class fold_expression_12(namedtuple('fold_expression_12', ['cast-expression', 'fold-operator', 'fold-operator2', 'cast-expression2'])):
  """
  ( cast-expression fold-operator ... fold-operator cast-expression )
  """
  format = '({0} {1} ... {2} {3})'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      rest = line[1:].lstrip()
      c1, rest = cast_expression.split(ctx, rest)
      if c1:
        o1, rest = fold_operator.split(ctx, rest)
        if o1 and rest.startswith('...'):
          o2, rest = fold_operator.split(ctx, rest[3:].lstrip())
          if o2:
            c2, rest = cast_expression.split(ctx, rest)
            if c2 and startswith_token(rest, ')'):
              return cls(c1, o1, o2, c2), rest[1:].lstrip()

class fold_expression_1(namedtuple('fold_expression_1', ['cast-expression', 'fold-operator'])):
  """
  ( cast-expression fold-operator ... )
  """
  format = '({0} {1} ...)'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      rest = line[1:].lstrip()
      c1, rest = cast_expression.split(ctx, rest)
      if c1:
        o1, rest = fold_operator.split(ctx, rest)
        if o1 and rest.startswith('...'):
          rest = rest[3:].lstrip()
          if startswith_token(rest, ')'):
            return cls(c1, o1), rest[1:].lstrip()

class fold_expression_2(namedtuple('fold_expression_2', ['fold-operator2', 'cast-expression2'])):
  """
  ( ... fold-operator cast-expression )
  """
  format = '(... {0} {1})'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      rest = line[1:].lstrip()
      if rest.startswith('...'):
        o2, rest = fold_operator.split(ctx, rest[3:].lstrip())
        if o2:
          c2, rest = cast_expression.split(ctx, rest)
          if c2 and startswith_token(rest, ')'):
            return cls(o2, c2), rest[1:].lstrip()

class fold_operator(namedtuple('fold_operator')):
  """
  one of
  """
  symbols = sorted('''
  +   -   *   /   %   ^   &   |   <<   >> 
  +=  -=  *=  /=  %=  ^=  &=  |=  <<=  >>=  =
  ==  !=  <   >   <=  >=  &&  ||  ,    .*   ->*
  '''.strip().split(), reverse=True, key=len)
  @splitter
  def split(cls, ctx, line):
    for s in cls.symbols:
      if line.startswith(s):
        return cls(line[:len(s)]), line[len(s):].lstrip()

class fold_expression(alternatives('fold_expression', fold_expression_12, fold_expression_2, fold_expression_1)):
  """
  ( cast-expression fold-operator ... )
  ( ... fold-operator cast-expression )
  ( cast-expression fold-operator ... fold-operator cast-expression )
  """

class requires_expression(namedtuple('requires_expression', ['requirement-parameter-list', 'requirement-body'])):
  """
  requires requirement-parameter-list? requirement-body
  """
  format = 'requires {0} {1}'
  @splitter
  def split(cls, ctx, line):
    requires, rest = word.split(ctx, line, require='requires')
    if requires:
      lst, rest = requirement_parameter_list.split(ctx, line)
      b, rest = requirement_body.split(ctx, line)
      if b:
        return cls(lst, b), rest

class primary_expression(alternatives('primary_expression',
                                      parenthesis_expression,
                                      literal,
                                      this_expression,
                                      lambda_expression,
                                      fold_expression,
                                      requires_expression,
                                      id_expression,
                                      )):
  """
  literal
  this
  ( expression )
  id-expression
  lambda-expression
  fold-expression
  requires-expression
  """
  
class postfix_expression_getitem(namedtuple('postfix_expression_getitem', ['postfix_expression', 'expression_list'])):
  """
  postfix-expression [ expression-list? ]
  """
  format = '{0}[{1}]'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      return
      head, rest = postfix_expression.split(ctx, line)
    else:
      rest = line

    if head and startswith_token(rest, '['):
      rest = rest[1:].lstrip()
      if startswith_token(rest, ']'):
        return cls(head, None), rest[1:].lstrip()

      lst, rest = expression_list.split(ctx, rest)
      if lst:
        if not startswith_token(rest, ']'):
          #assert 0, rest
          return
        assert startswith_token(rest, ']'), rest
        return cls(head, lst), rest[1:].lstrip()

class postfix_expression_call(namedtuple('postfix_expression_call', ['postfix_expression', 'expression_list'])):
  """
  postfix-expression ( expression-list? )
  """
  format = '{0}({1})'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      return
      head, rest = postfix_expression.split(ctx, line)
    else:
      rest = line

    if head and startswith_token(rest, '('):
      rest = rest[1:].lstrip()
      if startswith_token(rest, ')'):
        return cls(head, None), rest[1:].lstrip()

      lst, rest = expression_list.split(ctx, rest)
      if lst:
        if not startswith_token(rest, ')'):
          #assert 0, rest
          return
        assert startswith_token(rest, ')'), rest
        return cls(head, lst), rest[1:].lstrip()

class postfix_expression_proto(namedtuple('postfix_expression_init', ['simple_type_specifier', 'expression_list'])):
  """
  simple-type-specifier ( expression-list? )
  """
  format = '{0} ({1})'
  @splitter
  def split(cls, ctx, line):
    s, rest = simple_type_specifier.split(ctx, line)
    if s and startswith_token(rest, '('):
      rest = rest[1:].lstrip()
      if startswith_token(rest, ')'):
        return cls(s, None), rest[1:].lstrip()
      lst, rest = expression_list.split(ctx, rest)

      if lst and startswith_token(rest, ')'):
        return cls(s, lst), rest[1:].lstrip()



class postfix_expression_construct(namedtuple('postfix_expression_construct', ['typename_specifier', 'expression_list'])):
  """
  typename-specifier ( expression-list? )
  """
  format = '{0} ({1})'
  @splitter
  def split(cls, ctx, line):
    s, rest = typename_specifier.split(ctx, line)
    if s and startswith_token(rest, '('):
      rest = rest[1:].lstrip()
      if startswith_token(rest, ')'):
        return cls(s, None), rest[1:].lstrip()
      lst, rest = expression_list.split(ctx, rest)
      if startswith_token(rest, ')'):
        return cls(s, lst), rest[1:].lstrip()
  
class postfix_expression_braced_init(sequence('postfix_expression_braced_init', simple_type_specifier, braced_init_list)):
  """
  simple-type-specifier braced-init-list
  """
  
class postfix_expression_member(namedtuple('postfix_expression_member', ['postfix-expression', 'template', 'id-expression'])):
  """
  postfix-expression . template? id-expression
  """
  format = '{0}.{1} {2}'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      return
      head, rest = postfix_expression.split(ctx, line)
    else:
      rest = line
    if head and startswith_token(rest, '.'):
      t, rest = word.split(ctx, rest[1:].lstrip(), require='template')
      e, rest = id_expression.split(ctx, rest)
      if e:
        return cls(head, t, e), rest

class postfix_expression_ptrmember(namedtuple('postfix_expression_ptrmember', ['postfix-expression', 'template', 'id-expression'])):
  """
  postfix-expression -> template? id-expression
  """
  format = '{0}->{1} {2}'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      # avoid recurrsion, ptrmember is parsed in postprocess
      return
    rest = line
    if head and startswith_token(rest, '->'):
      t, rest = word.split(ctx, rest[2:].lstrip(), require='template')
      e, rest = id_expression.split(ctx, rest)
      if e:
        return cls(head, t, e), rest

  
class postfix_expression_incr(namedtuple('postfix_expression_incr')):
  """
  postfix-expression ++
  """
  format = '{0} ++'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      # avoid recurrsion, ptrmember is parsed in postprocess
      return
    rest = line
    if head and rest.startswith('++'):
      return cls(head), rest[2:].lstrip()

class postfix_expression_decr(namedtuple('postfix_expression_decr')):
  """
  postfix-expression --
  """
  format = '{0} --'
  @splitter
  def split(cls, ctx, line, head=None):
    if head is None:
      # avoid recurrsion, ptrmember is parsed in postprocess
      return
    rest = line
    if head and rest.startswith('--'):
      return cls(head), rest[2:].lstrip()

class pointer_cast_expression(namedtuple('cast_expression', ['kind', 'type_id', 'expression'])):
  """
  dynamic_cast < type-id > ( expression )
  static_cast < type-id > ( expression )
  reinterpret_cast < type-id > ( expression )
  const_cast < type-id > ( expression )
  """
  @splitter
  def split(cls, ctx, line):
    for k_ in ['dynamic_cast', 'static_cast', 'reinterpret_cast', 'const_cast']:
      k, rest = word.split(ctx, line, require=k_)
      if k:
        break
    else:
      return
    if startswith_token(rest, '<'):
      rest = rest[1:].lstrip()
      raw, rest = split_until(rest, '>')
      t, rest2 = type_id.split(ctx, raw)
      if t:
        if rest2:
          return
        assert rest2 == '', rest2[:100]
        if startswith_token(rest, '('):
          e, rest = expression.split(ctx, rest[1:].lstrip())
          if e:
            assert startswith_token(rest, ')'), rest[:100]
            return cls(k, t, e), rest[1:].lstrip()

class typeid_expression(namedtuple('typeid_expression')):
  """
  typeid ( expression )
  typeid ( type-id )
  """
  @splitter
  def split(cls, ctx, line):
    typeid, rest = word.split(ctx, line, require='typeid')
    if typeid and startswith_token(rest, '('):
      rest = rest[1:].lstrip()
      for ecls in (type_id, expression):
        a, rest = ecls.split(ctx, rest)
        if a:
          assert startswith_token(rest, ')'), rest[:100]
          return cls(a), rest[1:].lstrip()

class postfix_expression(alternatives('postfix_expression',
                                      postfix_expression_braced_init,

                                      postfix_expression_getitem,
                                      postfix_expression_call,
                                      postfix_expression_construct,
                                      postfix_expression_proto,

                                      postfix_expression_member,
                                      postfix_expression_ptrmember,
                                      postfix_expression_incr,
                                      postfix_expression_decr,
                                      pointer_cast_expression,
                                      typeid_expression,
                                      primary_expression,
                                      )):
  """
  primary-expression
  postfix-expression [ expression-list? ]
  postfix-expression ( expression-list? )
  simple-type-specifier ( expression-list? )
  typename-specifier ( expression-list? )
  simple-type-specifier braced-init-list
  typename-specifier braced-init-list
  postfix-expression . template? id-expression
  postfix-expression -> template? id-expression
  postfix-expression ++
  postfix-expression --
  dynamic_cast < type-id > ( expression )
  static_cast < type-id > ( expression )
  reinterpret_cast < type-id > ( expression )
  const_cast < type-id > ( expression )
  typeid ( expression )
  typeid ( type-id )
  """

  @classmethod
  def postprocess(cls, ctx, item, rest):
    if startswith_token(rest, '('):
      item2, rest2 = postfix_expression_call.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)

    elif startswith_token(rest, '['):
      item2, rest2 = postfix_expression_getitem.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)

    elif startswith_token(rest, '.'):
      item2, rest2 = postfix_expression_member.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)

    elif startswith_token(rest, '->'):
      item2, rest2 = postfix_expression_ptrmember.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)

    elif rest.startswith('++'):
      item2, rest2 = postfix_expression_incr.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)

    elif rest.startswith('--'):
      item2, rest2 = postfix_expression_decr.split(ctx, rest, head=item)
      if item2:
        return cls.postprocess(ctx, item2, rest2)
      
    return item, rest
  
class unary_operator_expression(namedtuple('unary_operator_expression', ['uop', 'cast_expression'])):
  """
  unary-operator cast-expression
  ++ cast-expression
  -- cast-expression

  unary-operator: one of
  *  &  +  -  !  ~
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):

    for uop in ['++', '--', '*', '&', '+', '-', '!', '~']:
      if line.startswith(uop):
        e, rest = cast_expression.split(ctx, line[len(uop):].lstrip())
        if e:
          return cls(line[:len(uop)], e), rest

class await_expression(namedtuple('await_expression')):
  """
  co_await cast-expression
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    a, rest = word.split(ctx, line, require='co_await')
    if a:
      e, rest = cast_expression.split(ctx, rest)
      if e:
        return cls(e), rest

class sizeof_unary_expression(namedtuple('sizeof_unary_expression')):
  """
  sizeof unary-expression
  """
  format = 'sizeof {0}'
  @splitter
  def split(cls, ctx, line):
    sizeof, rest = word.split(ctx, line, require='sizeof')
    if sizeof:
      e, rest = unary_expression.split(ctx, rest)
      if e:
        return cls(e), rest

class sizeof_expression_typeid(namedtuple('sizeof_expression_typeid')):
  """
  sizeof ( type-id )
  """
  format = 'sizeof({0})'
  @splitter
  def split(cls, ctx, line):
    sizeof, rest = word.split(ctx, line, require='sizeof')
    if sizeof and startswith_token(rest, '('):
      t, rest = type_id.split(ctx, rest[1:].lstrip())
      if t and startswith_token(rest, ')'):
        return cls(t), rest[1:].lstrip()

class sizeof_expression_identifier(namedtuple('sizeof_expression_identifier')):
  """
  sizeof ... ( identifier )
  """
  format = 'sizeof ... ({0})'
  @splitter
  def split(cls, ctx, line):
    sizeof, rest = word.split(ctx, line, require='sizeof')
    if sizeof and rest.startswith('...'):
      rest = rest[3:].lstrip()
      if startswith_token(rest, '('):
        t, rest = identifier.split(ctx, rest[1:].lstrip())
        if t and startswith_token(rest, ')'):
          return cls(t), rest[1:].lstrip()

class sizeof_expression(alternatives('sizeof_expression', sizeof_expression_typeid, sizeof_expression_identifier, sizeof_unary_expression)):
  """
  sizeof unary-expression
  sizeof ( type-id )
  sizeof ... ( identifier )
  """
        
class alignof_expression(namedtuple('alignof_expression')):
  """
  alignof ( type-id )
  """
  format = 'alignof({0})'
  @splitter
  def split(cls, ctx, line):
    a, rest = word.split(ctx, line, require='alignof')
    if a:
      if startswith_token(rest, '('):
        e, rest = type_id.split(ctx, rest[1:].lstrip())
        if e and startswith_token(rest, ')'):
          return cls(e), rest[1:].lstrip()

class noexcept_expression(namedtuple('noexcept_expression')):
  """
  noexcept ( expression )
  """
  format = 'noexpect({0})'
  @splitter
  def split(cls, ctx, line):
    a, rest = word.split(ctx, line, require='noexpect')
    if a:
      if startswith_token(rest, '('):
        e, rest = expression.split(ctx, rest[1:].lstrip())
        if e and startswith_token(rest, ')'):
          return cls(e), rest[1:].lstrip()

class new_placement(namedtuple('new_placement')):
  """
  ( expression-list )
  """
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      lst, rest = expression_list.split(ctx, line[1:].lstrip())
      if lst and startswith_token(rest, ')'):
        return cls(lst), rest[1:].lstrip()

class noptr_new_declarator_1(namedtuple('noptr_new_declarator_1')):
  """
  [ expression? ]
  """
  formar = '[{0}]'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('['):
      rest = line[1:].lstrip()
      if startswith_token(rest, ']'):
        return cls(None), rest[1:].lstrip()
      e, rest = expression.split(ctx, rest)
      if e and startswith_token(rest, ']'):
        return cls(e), rest[1:].lstrip()
  
class noptr_new_declarator_2(namedtuple('noptr_new_declarator_2', ['noptr-new-declarator', 'constant-expression'])):
  """
  noptr-new-declarator [ constant-expression ]
  """
  formar = '{0} [{1}]'
  @splitter
  def split(cls, ctx, line):
    d, rest = noptr_new_declarator.split(ctx, line)
    if d and startswith_token(rest, '['):
      e, rest = constant_expression.split(ctx, rest[1:].lstrip())
      if e and startswith_token(rest, ']'):
        return cls(e), rest[1:].lstrip()

class noptr_new_declarator_head(alternatives('noptr_new_declarator_head', noptr_new_declarator_1, noptr_new_declarator_2)):
  """
  [ expression? ]
  noptr-new-declarator [ constant-expression ]
  """
  
class noptr_new_declarator(item_optional_suffix(noptr_new_declarator_head, attribute_specifier_seq)):
  """
  [ expression? ] attribute-specifier-seq?
  noptr-new-declarator [ constant-expression ] attribute-specifier-seq?
  """

class new_declarator(alternatives('new_declarator', lambda: ptr_operator_optional_new_declarator, noptr_new_declarator)):
  """
  ptr-operator new-declarator?
  noptr-new-declarator
  """

class ptr_operator_optional_new_declarator(item_optional_suffix(ptr_operator, new_declarator)):
  """
  ptr-operator new-declarator?
  """

class new_type_id(item_optional_suffix(type_specifier_seq, new_declarator)):
  """
  type-specifier-seq new-declarator?
  """

class type_id_with_parenthesis(namedtuple('type_id_with_parenthesis')):
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      t, rest = type_id.split(ctx, line[1:].lstrip())
      if t and startswith_token(rest, ')'):
        return cls(lst), rest[1:].lstrip()

class new_type_id_or_parenthesis(alternatives('new_type_id_or_parenthesis', type_id_with_parenthesis, new_type_id)):
  pass

class expression_list_with_parenthesis(namedtuple('expression_list_with_parenthesis')):
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      rest = line[1:].lstrip()
      if startswith_token(rest, ')'):
        return cls(None), rest[1:].lstrip()
      e, rest = expression_list.split(ctx, rest)
      if e:
        assert startswith_token(rest, ')'), rest
        return cls(e), rest[1:].lstrip()

class new_initializer(alternatives('new_initializer', expression_list_with_parenthesis, braced_init_list)):
  """
  ( expression-list? )
  braced-init-list
  """

class new_expression(namedtuple('new_expression', ['scope', 'new_placement', 'type_id_part', 'new_initializer'])):
  """
  ::? new new-placement? new-type-id new-initializer?
  ::? new new-placement? ( type-id ) new-initializer?
  """
  format = '{0} new {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    s = None
    if line.startswith('::'):
      s = line[:2]
      rest = line[2:].lstrip()
    else:
      rest = line
    new, rest = word.split(ctx, rest, require='new')
    if new:
      p, rest = new_placement.split(ctx, rest)
      t, rest = new_type_id_or_parenthesis.split(ctx, rest)
      if t:
        i, rest = new_initializer.split(ctx, rest)
        return cls(s, p, t, i), rest

class delete_expression(namedtuple('delete_expression', ['scope', 'braces', 'cast_expression'])):
  """
  ::? delete cast-expression
  ::? delete [ ] cast-expression
  """
  format = '{0} delete {1} {2}'
  @splitter
  def split(cls, ctx, line):
    if line.startswith('::'):
      s = line[:2]
      rest = line[2:].lstrip()
    else:
      s = None
      rest = line
    delete, rest = word.split(ctx, rest, require='delete')
    if delete:
      if startswith_token(rest, '['):
        rest = rest[1:].lstrip()
        if startswith_token(rest, ']'):
          rest = rest[1:].lstrip()
          e, rest = cast_expression.split(ctx, rest)
          if e:
            return cls(s, '[]', e), rest
      else:
        e, rest = cast_expression.split(ctx, rest)
        if e:
          return cls(s, None, e), rest      

class unary_expression(alternatives('unary_expression',
                                    unary_operator_expression,
                                    await_expression,
                                    sizeof_expression,
                                    alignof_expression,
                                    noexcept_expression,
                                    new_expression,
                                    delete_expression,
                                    postfix_expression,)):
  """
  postfix-expression
  unary-operator cast-expression
  ++ cast-expression
  -- cast-expression
  await-expression
  sizeof unary-expression
  sizeof ( type-id )
  sizeof ... ( identifier )
  alignof ( type-id )
  noexcept-expression
  new-expression
  delete-expression
  """


class cast_expression(namedtuple('cast_expression', ['type_id', 'cast_expression'])):
  """
  unary-expression
  ( type-id ) cast-expression
  """
  format = '( {0} ) {1}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      t, rest = type_id.split(ctx, line[1:].lstrip())
      if t and startswith_token(rest, ')'):
        e, rest = cast_expression.split(ctx, rest[1:].lstrip())
        if e:
          return cls(t, e), rest
    e, rest = unary_expression.split(ctx, line)
    if e:
      return e, rest
  
class pm_expression(pair_or_item('pm_expression', ['.*', '->*'], cast_expression)):
  """
  cast-expression
  pm-expression .* cast-expression
  pm-expression ->* cast-expression
  """

class multiplicative_expression(pair_or_item('multiplicative_expression', ['*', '/', '%'], pm_expression)):
  """
  pm-expression
  multiplicative-expression * pm-expression
  multiplicative-expression / pm-expression
  multiplicative-expression % pm-expression
  """

class additive_expression(pair_or_item('additive_expression', ['+', '-'], multiplicative_expression)):
  """
  multiplicative-expression
  additive-expression + multiplicative-expression
  additive-expression - multiplicative-expression
  """

class shift_expression(pair_or_item('shift_expression', ['<<', '>>'], additive_expression)):
  """
  additive-expression
  shift-expression << additive-expression
  shift-expression >> additive-expression
  """
class compare_expression(pair_or_item('compare_expression', ['<=>'], shift_expression)):
  """
  shift-expression
  compare-expression <=> shift-expression
  """

class relational_expression(pair_or_item('relational_expression', ['<=', '>=', '<', '>'], compare_expression)):
  """
  compare-expression
  relational-expression < compare-expression
  relational-expression > compare-expression
  relational-expression <= compare-expression
  relational-expression >= compare-expression
  """

class equality_expression(pair_or_item('equality_expression', ['==', '!='], relational_expression)):
  """
  relational-expression
  equality-expression == relational-expression
  equality-expression != relational-expression
  """

class and_expression(pair_or_item('and_expression', '&', equality_expression)):
  """
  equality-expression
  and-expression & equality-expression
  """

class exlucive_or_expression(pair_or_item('exlucive_or_expression', '^', and_expression)):
  """
  and-expression
  exclusive-or-expression ^ and-expression
  """

class inclusive_or_expression(pair_or_item('inclusive_or_expression', '|', exlucive_or_expression)):
  """
  exclusive-or-expression
  inclusive-or-expression | exclusive-or-expression
  """

class logical_and_expression(pair_or_item('logical_and_expression', '&&', inclusive_or_expression)):
  """
  inclusive-or-expression
  logical-and-expression && inclusive-or-expression
  """

class logical_or_expression(pair_or_item('logical_or_expression', '||', logical_and_expression)):
  """
  logical-and-expression
  logical-or-expression || logical-and-expression
  """

class assignment_operator(namedtuple('assignment_operator')):
  @splitter
  def split(cls, ctx, line):
    for aop in ['>>=', '<<=', '*=',  '/=',  '%=',   '+=',  '-=', '&=',  '^=',  '|=', '=']:
      if line.startswith(aop):
        return line[:len(aop)], line[len(aop):].lstrip()

class assignment_expression_assignment(sequence('assignment_expression_assignment', logical_or_expression, assignment_operator, lambda: initializer_clause)):
  """
  logical-or-expression assignment-operator initializer-clause

  assignment-operator: one of
  =  *=  /=  %=   +=  -=  >>=  <<=  &=  ^=  |=
  """
  
class conditional_expression(namedtuple('conditional_expression', ['logical_or_expression', 'expression', 'assignment_expression'])):
  """
  logical-or-expression
  logical-or-expression ? expression : assignment-expression
  """
  format = '{0} ? {1} : {2}'
  @splitter
  def split(cls, ctx, line):
    l, rest = logical_or_expression.split(ctx, line)
    if l:
      if rest.startswith('?'):
        e, rest = expression.split(ctx, rest[1:].lstrip())
        if e:
          if startswith_token(rest, ':'):
            a, rest = assignment_expression.split(ctx, rest[1:].lstrip())
            if a:
              return cls(l, e, a), rest
      else:
        return l, rest

class yield_expression(namedtuple('yield_expression')):
  """
  co_yield assignment-expression
  co_yield braced-init-list
  """
  format = 'co_yield {0}'
  @splitter
  def split(cls, ctx, line):
    co_yield, rest = word.split(ctx, line, require='co_yield')
    if co_yield:
      lst, rest = braced_init_list.split(ctx, rest)
      if lst:
        return cls(lst), rest
      a, rest = assignment_expression.split(ctx, rest)
      if a:
        return cls(a), rest

class throw_expression(namedtuple('throw_expression')):
  """
  throw assignment-expression?
  """
  format = 'throw {0}'
  @splitter
  def split(cls, ctx, line):
    throw, rest = word.split(ctx, line, require='throw')
    if throw:
      a, rest = assignment_expression.split(ctx, rest)
      return cls(a), rest

class assignment_expression(alternatives('assignment_expression',
                                         yield_expression,
                                         throw_expression,
                                         assignment_expression_assignment,
                                         conditional_expression,
                                         )):
  """
  conditional-expression
  yield-expression
  throw-expression
  logical-or-expression assignment-operator initializer-clause
  """

class expression(pair_or_item('expression', ',', assignment_expression)):
  """
  assignment-expression
  expression , assignment-expression
  """

class constant_expression(alternatives('constant_expression', conditional_expression)):
  """
  conditional-expression
  """
  
class initializer_clause(alternatives('initializer_clause', braced_init_list, assignment_expression)):
  """
  assignment-expression
  braced-init-list
  """

class initializer_list(pair_or_item('initializer_list', ',', initializer_clause_dots)):
  """
  initializer-clause ...?
  initializer-list , initializer-clause ...?
  """

class designated_initializer_list(pair_or_item('designated_initializer_list', ',', designated_initializer_clause)):
  """
  designated-initializer-clause
  designated-initializer-list , designated-initializer-clause
  """

class expression_list_with_parenthesis(namedtuple('expression_list_with_parenthesis')):
  """
  ( expression-list )
  """
  format = '({0})'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '('):
      lst, rest = expression_list.split(ctx, line[1:].lstrip())
      if lst and startswith_token(rest, ')'):
        return cls(lst), rest[1:].lstrip()

class initializer(alternatives('initializer', brace_or_equal_initializer, expression_list_with_parenthesis)):
  """
  brace-or-equal-initializer
  ( expression-list )
  """

class init_declarator(namedtuple('init_declarator', ['declarator', 'initializer_or_requires_clause'])):
  """
  declarator initializer?
  declarator requires-clause
  """
  @splitter
  def split(cls, ctx, line):
    decl, rest = declarator.split(ctx, line)
    if decl:
      r, rest = requires_clause.split(ctx, rest)
      if r:
        return cls(decl, r), rest
      init, rest = initializer.split(ctx, rest)
      return cls(decl, init), rest

  
class init_declarator_list(pair_or_item('init_declarator_list', ',', init_declarator)):
  """
  init-declarator
  init-declarator-list , init-declarator
  """

class simple_declaration_constructor(namedtuple('simple_declaration_constructor', ['decl-specifier-seq', 'constructor'])):
  """
  decl-specifier-seq? constructor ;
  """
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):

    s, rest = decl_specifier_seq.split(ctx, line, has_type_specifier=True)
    ctr, rest = constructor.split(ctx, rest)
    if ctr:
      return cls(s, ctr), rest

class simple_declaration_1(namedtuple('simple_declaration_1', ['decl-specifier-seq', 'init-declarator-list'])):
  """
  decl-specifier-seq init-declarator-list? ;
  """
  format = '{0} {1};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    s, rest = decl_specifier_seq.split(ctx, line)
    lst, rest = init_declarator_list.split(ctx, rest)
    if s:
      return cls(s, lst), rest

class simple_declaration_2(namedtuple('simple_declaration_2', ['attribute-specifier-seq', 'decl-specifier-seq', 'init-declarator-list'])):
  """
  attribute-specifier-seq decl-specifier-seq init-declarator-list ;
  """
  format = '{0} {1} {2};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    if a:
      s, rest = decl_specifier_seq.split(ctx, rest)
      if s:
        lst, rest = init_declarator_list.split(ctx, rest)
        if lst:
          return cls(a, s, lst), rest

class simple_declaration_structured_binding(namedtuple('simple_declaration_structured_binding', ['structured-binding-declaration', 'initializer'])):
  """
  structured-binding-declaration initializer ;
  """
  format = '{0} {1};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    d, rest = structured_binding_declaration.split(ctx, line)
    if d:
      i, rest = initializer.split(ctx, rest)
      if i:
        return cls(d, i), rest

class simple_declaration(alternatives('simple_declaration', simple_declaration_structured_binding, simple_declaration_2, simple_declaration_1, simple_declaration_constructor)):
  """
                          decl-specifier-seq init-declarator-list? ;
  attribute-specifier-seq decl-specifier-seq init-declarator-list ;
  structured-binding-declaration initializer ;
  """

class attributed_identifier(item_optional_suffix(identifier, attribute_specifier_seq)):
  """
  identifier attribute-specifier-seq?
  """

class attributed_identifier_list(pair_or_item('attributed_identifier_list', ',', attributed_identifier)):
  """
  attributed-identifier
  attributed-identifier-list , attributed-identifier
  """

class structured_binding_declaration(namedtuple('structured_binding_declaration', ['attribute-specifier-seq', 'decl-specifier-seq', 'ref-qualifier', 'attributed-identifier-list'])):
  """
  attribute-specifier-seq? decl-specifier-seq ref-qualifier? [ attributed-identifier-list ]
  """
  format = '{0} {1} [{2}]'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    seq, rest = decl_specifier_seq.split(ctx, rest)
    if seq:
      r, rest = ref_qualifier.split(ctx, rest)
      if startswith_token(rest, '['):
        lst, rest = attributed_identifier_list.split(ctx, rest[1:].lstrip())
        if lst and startswith_token(rest, ']'):
          return cls(a, seq, r, lst), rest[1:].lstrip()

class virt_specifier(namedtuple('virt_specifier')):
  @classmethod
  def split_keywords(cls):
    return ('override', 'final')

class virt_specifier_seq(namedtuple('virt_specifier_seq')):
  @splitter
  def split(cls, ctx, line):
    lst = []
    rest = line
    while rest:
      spec, rest = virt_specifier.split(ctx, rest)
      if spec:
        lst.append(spec)
      else:
        break
    if lst:
      return cls(lst), rest

class anystatement(namedtuple('anystatement')):
  """
  anystatement ;
  """
  format = '{0};'
  @splitter
  def split(cls, ctx, line):
    s, rest = split_until(line, ';', stop_marks='}',  require_mark=False)
    if s:
      return cls(s), rest

class labeled_statement_identifier(namedtuple('labeled_statement_identifier', ['attribute-specifier-seq', 'identifier'])):
  """
  attribute-specifier-seq? identifier :
  """
  format = '{0} {1}:'
  @splitter
  @_require_and_drop_colon
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    i, rest = identifier.split(ctx, rest)
    if i:
      return cls(a, i), rest

class labeled_statement_case(namedtuple('labeled_statement_case', ['attribute-specifier-seq', 'constant-expression'])):
  """
  attribute-specifier-seq? case constant-expression :
  """
  format = '{0} case {1}:'
  @splitter
  @_require_and_drop_colon
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    case, rest = word.split(ctx, rest, require='case')
    if case:
      e, rest = constant_expression.split(ctx, rest)
      if e:
        return cls(a, e), rest

class labeled_statement_default(namedtuple('labeled_statement_default')):
  """
  attribute-specifier-seq? default :
  """
  format = '{0} default:'
  @splitter
  @_require_and_drop_colon
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    default, rest = word.split(ctx, rest, require='default')
    if default:
      return cls(a), rest

class labeled_statement(alternatives('labeled_statement', labeled_statement_default, labeled_statement_case, labeled_statement_identifier)):
  """
  attribute-specifier-seq? identifier :
  attribute-specifier-seq? case constant-expression :
  attribute-specifier-seq? default :
  """

class declaration_statement(alternatives('declaration_statement', block_declaration)):
  """
  block-declaration
  """

class expression_statement(namedtuple('expression_statement')):
  """
  expression? ;
  """
  format = '{0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    e, rest = expression.split(ctx, line)
    return cls(e), rest
    
class expression_statement_with_prefix(item_optional_prefix(expression_statement, attribute_specifier_seq)):
  """
  attribute-specifier-seq? expression-statement
  """

class compound_statement(namedtuple('compound_statement', ['statement-seq', 'label-seq'])):
  """
  { statement-seq? label-seq? }
  """
  format = '{{ {0} {1} }}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('{'):
      head_lines = line[:1]
      s, rest = statement_seq.split(ctx, line[1:].lstrip())
      l, rest = label_seq.split(ctx, rest)
      if startswith_token(rest, '}'):
        return cls(s, l), rest[1:].lstrip()
      _report_unexpected_block_end(cls, head_lines, rest)
      raise RuntimeError(f'unexpected return when parsing class member specifications (see output above)')

class compound_statement_with_prefix(item_optional_prefix(compound_statement, attribute_specifier_seq)):
  """
  attribute-specifier-seq? compound-statement
  """

class selection_statement_if_else(namedtuple('selection_statement_if_else', ['constexpr', 'init-statement', 'condition', 'statement', 'else_statement'])):
  """
  if constexpr? ( init-statement? condition ) statement else statement
  """
  @property
  def format(self):
    if self.else_statement is None:
      return 'if {0} ({1} {2}) {3}'
    return 'if {0} ({1} {2}) {3} else {4}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='if')
    if t:
      ce, rest = constexpr.split(ctx, rest)
      if startswith_token(rest, '('):
        init, rest = init_statement.split(ctx, rest[1:].lstrip())
        c, rest = condition.split(ctx, rest)
        if c and startswith_token(rest, ')'):
          s, rest = statement.split(ctx, rest[1:].lstrip())
          if s:
            te, rest = word.split(ctx, rest, require='else')
            if te:
              se, rest = statement.split(ctx, rest)
              if se:
                return cls(ce, init, c, s, se), rest
            else:
              return cls(ce, init, c, s, None), rest

class selection_statement_if_compound_else(namedtuple('selection_statement_if_compound_else', ['excl', 'compound-statement', 'else_statement'])):
  """
  if !? consteval compound-statement else statement
  """
  @property
  def format(self):
    if self.else_statement is None:
      return 'if {0} consteval {1}'
    return 'if {0} consteval {1} else {2}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='if')
    if t:
      if startswith_token(rest, '!'):
        excl = rest[0]
        rest = rest[1:].lstrip()
      else:
        excl = None
      ce, rest = consteval.split(ctx, rest)
      if ce:
        c, rest = compound_statement.split(ctx, rest)
        if c:
          te, rest = word.split(ctx, rest, require='else')
          if te:
            se, rest = statement.split(ctx, rest)
            return cls(excl, c, se), rest
          else:
            return cls(excl, c, None), rest

class selection_statement_switch(namedtuple('selection_statement_switch', ['init-statement', 'condition', 'statement'])):
  """
  switch ( init-statement? condition ) statement
  """
  format = 'switch ({0} {1}) {2}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='switch')
    if t and startswith_token(rest, '('):
      init, rest = init_statement.split(ctx, rest[1:].lstrip())
      c, rest = condition.split(ctx, rest)
      if c and startswith_token(rest, ')'):
        s, rest = statement.split(ctx, rest[1:].lstrip())
        if s:
          return cls(init, c, s), rest
          
class selection_statement(alternatives('selection_statement',
                                       selection_statement_if_else,
                                       selection_statement_if_compound_else,
                                       selection_statement_switch,
                                       )):
  """
  if constexpr? ( init-statement? condition ) statement
  if constexpr? ( init-statement? condition ) statement else statement
  if !? consteval compound-statement
  if !? consteval compound-statement else statement
  switch ( init-statement? condition ) statement
  """

class selection_statement_with_prefix(item_optional_prefix(selection_statement, attribute_specifier_seq)):
  """
  attribute-specifier-seq? selection-statement
  """

class iteration_statement_while(namedtuple('iteration_statement_while', ['condition', 'statement'])):
  """
  while ( condition ) statement
  """
  format = 'while ({0}) {1}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='while')
    if t and startswith_token(rest, '('):
      c, rest = condition.split(ctx, rest[1:].lstrip())
      if c and startswith_token(rest, ')'):
        s, rest = statement.split(ctx, rest[1:].lstrip())
        if s:
          return cls(c, s), rest

class iteration_statement_do(namedtuple('iteration_statement_do', ['statement', 'expression'])):
  """
  do statement while ( expression ) ;
  """
  format = 'do {0} while ({1});'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='do')
    if t:
      s, rest = statement.split(ctx, rest)
      if s:
        w, rest = word.split(ctx, rest, require='while')
        if w and startswith_token(rest, '('):
          e, rest = expression.split(ctx, rest[1:].lstrip())
          if e and startswith_token(rest, ')'):
            return cls(s, e), rest[1:].lstrip()

class init_statement(alternatives('init_statement',
                                  expression_statement,
                                  simple_declaration,
                                  alias_declaration)):
  """
  expression-statement
  simple-declaration
  alias-declaration
  """

class decl_specifier_seq_with_prefix(item_optional_prefix(decl_specifier_seq, attribute_specifier_seq)):
  """
  attribute-specifier-seq? decl-specifier-seq
  """
  
class decl_specifier_seq_declaration(sequence('decl_specifier_seq_declaration', decl_specifier_seq_with_prefix, declarator)):
  """
    attribute-specifier-seq? decl-specifier-seq declarator
  """
  
class for_range_declaration(alternatives('for_range_declaration', decl_specifier_seq_declaration, structured_binding_declaration)):
  """
  attribute-specifier-seq? decl-specifier-seq declarator
  structured-binding-declaration
  """

class for_range_initializer(alternatives('for_range_initializer', lambda: expr_or_braced_init_list)):
  """
  expr_or_braced_init_list
  """
  
class iteration_statement_for_classic(namedtuple('iteration_statement_for_classic', ['init-statement', 'for-range-declaration', 'for-range-initializer', 'statement'])):
  """
  for ( init-statement? for-range-declaration : for-range-initializer ) statement
  """
  format = 'for({0} {1} : {2}) {3}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='for')
    if t and startswith_token(rest, '('):
      init, rest = init_statement.split(ctx, rest[1:].lstrip())
      d, rest = for_range_declaration.split(ctx, rest)
      if d and startswith_token(rest, ':'):
        i, rest = for_range_initializer.split(ctx, rest[1:].lstrip())
        if i and startswith_token(rest, ')'):
          s, rest = statement.split(ctx, rest[1:].lstrip())
          if s:
            return cls(init, d, i, s), rest

class decl_specifier_seq_declarator_initializer(sequence('decl_specifier_seq_declarator_initializer', decl_specifier_seq_with_prefix, declarator, brace_or_equal_initializer)):
  """
  attribute-specifier-seq? decl-specifier-seq declarator brace-or-equal-initializer
  """
class structured_binding_declaration_initializer(sequence('structured_binding_declaration_initializer', structured_binding_declaration, initializer)):
  """
  structured-binding-declaration initializer
  """

class condition(alternatives('condition',
                             structured_binding_declaration_initializer,
                             decl_specifier_seq_declarator_initializer,
                             expression)):
  """
  expression
  attribute-specifier-seq? decl-specifier-seq declarator brace-or-equal-initializer
  structured-binding-declaration initializer
  """
          
class iteration_statement_for(namedtuple('iteration_statement_for', ['init-statement', 'condition', 'expression', 'statement'])):
  """
  for ( init-statement condition? ; expression? ) statement
  """
  format = 'for({0} {1}; {2}) {3}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='for')
    if t and startswith_token(rest, '('):
      init, rest = init_statement.split(ctx, rest[1:].lstrip())
      if init:
        c, rest = condition.split(ctx, rest)
        if rest.startswith(';'):
          e, rest = expression.split(ctx, rest[1:].lstrip())
          if startswith_token(rest, ')'):
            s, rest = statement.split(ctx, rest[1:].lstrip())
            if s:
              return cls(init, c, e, s), rest

class iteration_statement(alternatives('iteration_statement',
                                       iteration_statement_while,
                                       iteration_statement_do,
                                       iteration_statement_for_classic,
                                       iteration_statement_for)):
  """
  while ( condition ) statement
  do statement while ( expression ) ;
  for ( init-statement condition? ; expression? ) statement
  for ( init-statement? for-range-declaration : for-range-initializer ) statement
  """

class iteration_statement_with_prefix(item_optional_prefix(iteration_statement, attribute_specifier_seq)):
  """
  attribute-specifier-seq? iteration-statement
  """

class jump_statement_break(namedtuple('jump_statement_break', ['unused'])):
  """
  break ;
  """
  format = 'break;'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='break')
    if t:
      return cls(None), rest

class jump_statement_continue(namedtuple('jump_statement_continue', ['unused'])):
  """
  continue ;
  """
  format = 'continue;'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='continue')
    if t:
      return cls(None), rest

class expr_or_braced_init_list(alternatives(expression, braced_init_list)):
  """
  expression
  braced-init-list
  """
    
class jump_statement_return(namedtuple('jump_statement_return')):
  """
  return expr-or-braced-init-list? ;
  """
  format = 'return {0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='return')
    if t:
      r, rest = expr_or_braced_init_list.split(ctx, rest)
      return cls(r), rest

class coroutine_return_statement(namedtuple('coroutine_return_statement')):
  """
  co_return expr-or-braced-init-list? ;
  """
  format = 'co_return {0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='co_return')
    if t:
      r, rest = expr_or_braced_init_list.split(ctx, rest)
      return cls(r), rest

class jump_statement_goto(namedtuple('jump_statement_goto')):
  format = 'goto {0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='goto')
    if t:
      i, rest = identifier.split(ctx, rest)
      if i:
        return cls(i), rest

class jump_statement(alternatives('jump_statement',
                                  jump_statement_break,
                                  jump_statement_continue,
                                  jump_statement_return,
                                  coroutine_return_statement,
                                  jump_statement_goto)):
  """
  break ;
  continue ;
  return expr-or-braced-init-list? ;
  coroutine-return-statement
  goto identifier ;
  """

class jump_statement_with_prefix(item_optional_prefix(jump_statement, attribute_specifier_seq)):
  """
  attribute-specifier-seq? jump-statement
  """

class exception_declaration(namedtuple('exception_declaration', ['attribute-specifier-seq', 'type-specifier-seq', 'declarator'])):
  """
  attribute-specifier-seq? type-specifier-seq declarator
  attribute-specifier-seq? type-specifier-seq abstract-declarator?
  ...
  """
  @property
  def format(self):
    if self[1] is None:
      return self[2]  # `...`
    return '{0} {1} {2}'

  @splitter
  def split(cls, ctx, line):
    if line.startswith('...'):
      return cls(None, None, line[:3]), line[3:].lstrip()

    a, rest = attribute_specifier_seq.split(ctx, line)
    s, rest = type_specifier_seq.split(ctx, rest)
    if s:
      d, rest = declarator.split(ctx, rest)
      if d:
        return cls(a, s, d), rest
      d, rest = abstract_declarator.split(ctx, rest)
      return cls(a, s, d), rest
    
class handler(namedtuple('handler', ['exception-declaration', 'compound-statement'])):
  """
  catch ( exception-declaration ) compound-statement
  """
  format = 'catch({0}) {1}'
  @splitter
  def split(cls, ctx, line):
    catch, rest = word.split(ctx, line, require='catch')
    if catch and rest.startswith('('):
      d, rest = exception_declaration.split(ctx, rest[1:].lstrip())
      if d and rest.startswith(')'):
        s, rest = compound_statement.split(ctx, rest[1:].lstrip())
        if s:
          return cls(d, s), rest

class handler_seq(item_sequence('handler_seq', handler)):
  """
  handler handler-seq?
  """
    
class try_block(namedtuple('try_block', ['compound-statement', 'handler-seq'])):
  """
  try compound-statement handler-seq
  """
  format = 'try {0} {1}'
  @splitter
  def split(cls, ctx, line):
    t, rest = word.split(ctx, line, require='try')
    if t:
      s, rest = compound_statement.split(ctx, rest)
      if s:
        seq, rest = handler_seq.split(ctx, rest)
        if seq:
          return cls(s, seq), rest

class try_block_with_prefix(item_optional_prefix(try_block, attribute_specifier_seq)):
  """
  attribute-specifier-seq? try-block
  """
  
class statement(alternatives('statement',
                             expression_statement_with_prefix,
                             jump_statement_with_prefix,
                             selection_statement_with_prefix,
                             iteration_statement_with_prefix,
                             try_block_with_prefix,
                             compound_statement_with_prefix,
                             labeled_statement,
                             declaration_statement,
                             )):
  """
  labeled-statement
  attribute-specifier-seq? expression-statement
  attribute-specifier-seq? compound-statement
  attribute-specifier-seq? selection-statement
  attribute-specifier-seq? iteration-statement
  attribute-specifier-seq? jump-statement
  declaration-statement
  attribute-specifier-seq? try-block
  """

class label_identifier(namedtuple('label_identifier', ['attribute-specifier-seq', 'identifier'])):
  """
  attribute-specifier-seq? identifier :
  """
  format = '{0} {1}:'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    i, rest = identifier.split(ctx, rest)
    if i and startswith_token(rest, ':'):
      return cls(a, i), rest[1:].lstrip()

class label_case(namedtuple('label_case', ['attribute-specifier-seq', 'constant-expression'])):
  """
  attribute-specifier-seq? case constant-expression :
  """
  format = '{0} case {1}:'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    case, rest = word.split(ctx, line, require='case')
    if case:
      e, rest = constant_expression.split(ctx, rest)
      if e and startswith_token(rest, ':'):
        return cls(a, e), rest[1:].lstrip()

class label_default(namedtuple('label_case', ['attribute-specifier-seq'])):
  """
  attribute-specifier-seq? case constant-expression :
  """
  format = '{0} default:'
  @splitter
  def split(cls, ctx, line):
    a, rest = attribute_specifier_seq.split(ctx, line)
    d, rest = word.split(ctx, line, require='default')
    if d:
      if startswith_token(rest, ':'):
        return cls(a), rest[1:].lstrip()

class label(alternatives(label_case, label_default, label_identifier)):
  """
  attribute-specifier-seq? identifier :
  attribute-specifier-seq? case constant-expression :
  attribute-specifier-seq? default :
  """

class statement_seq(item_sequence('statement_seq', statement)):
  """
  statement
  statement-seq statement
  """

class label_seq(item_sequence('label_seq', label)):
  """
  label
  label-seq label
  """


class mem_initializer_braced_init_list(namedtuple('mem_initializer_braced_init_list', ['mem_initializer_id', 'braced_init_list'])):
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    m, rest = mem_initializer_id.split(ctx, line)
    if m:
      lst, rest = braced_init_list.split(ctx, rest)
      if lst:
        return cls(m, lst), rest

class mem_initializer_expression_list(namedtuple('mem_initializer_expression_list', ['mem_initializer_id', 'expression_list'])):
  """
  mem-initializer-id ( expression-list? )
  """
  format = '{0} ({1})'
  @splitter
  def split(cls, ctx, line):
    m, rest = mem_initializer_id.split(ctx, line)
    if m and startswith_token(rest, '('):
      rest = rest[1:].lstrip()
      if startswith_token(rest, ')'):
        return cls(m, None), rest[1:].lstrip()
      lst, rest = expression_list.split(ctx, rest)
      if lst and startswith_token(rest, ')'):
          return cls(m, lst), rest[1:].lstrip()

class mem_initializer(alternatives('mem_initializer',
                                   mem_initializer_expression_list,
                                   mem_initializer_braced_init_list)):
  """
  mem-initializer-id ( expression-list? )
  mem-initializer-id braced-init-list
  """
  
class mem_initializer_with_dots(item_optional_dots(mem_initializer)):
  """
  mem-initializer ...?
  """

class mem_initializer_list(pair_or_item('mem_initializer_list', ',', mem_initializer_with_dots)):
  """
  mem-initializer ...?
  mem-initializer-list , mem-initializer ...?
  """
  
class ctor_initializer(namedtuple('ctor_initializer')):
  """
  : mem_initializer_list
  """
  format = ': {0}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, ':'):
      lst, rest = mem_initializer_list.split(ctx, line[1:].lstrip())
      if lst is not None:
        return cls(lst), rest

class regular_function_body(namedtuple('regular_function_body', ['ctor_initializer', 'compound_statement'])):
  """
  ctor-initializer ﻿(optional) compound-statement
  """

  @splitter
  def split(cls, ctx, line):
    init, rest = ctor_initializer.split(ctx, line)
    stmt, rest = compound_statement.split(ctx, rest)

    if stmt is not None:
      return cls(init, stmt), rest

class function_try_block(namedtuple('function_try_block', ['ctor_initializer', 'compound_statement', 'handler_seq'])):
  """
  try ctor-initializer ﻿(optional) compound-statement handler-seq
  """
  def __str__(self):
    if self[0] is None:
      return 'try {1} {2}'.format(*self)
    return 'try {0} {1} {2}'.format(*self)

  @splitter
  def split(cls, ctx, line):
    try_, rest = word.split(ctx, line, require='try')
    if try_ is not None:
      ctor_init, rest = ctor_initializer.split(ctx, rest)
      stmt, rest = compund_statement.split(ctx, rest)
      if stmt is not None:
        seq, rest = handler_seq.split(ctx, rest)
        if seq is not None:
          return cls(ctor_init, stmt, seq)

class explicit_default(namedtuple('explicit_default', [])):
  """
  = default
  """
  def __str__(self):
    return '= default'

  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '='):
      rest = line[1:].lstrip()
      default, rest = word.split(ctx, rest, require='default')
      if default:
        return cls(), rest

class explicitly_defaulted_function_definition(namedtuple('explicitly_defaulted_function_definition')):
  """
  = default ;
  """
  format = '{0} ;'
  @splitter
  def split(cls, ctx, line):
    d, rest = explicit_default.split(ctx, line)
    if d is not None and rest.startswith(';'):
      return cls(d), rest[1:].lstrip()

class explicitly_deleted_function_definition(namedtuple('explicitly_deleted_function_definition')):
  """
  = delete ;
  = delete ( string-literal );
  """
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, '='):
      rest = line[1:].lstrip()
      delete, rest = word.split(ctx, rest, require='delete')
      if delete is not None:
        if rest.startswith(';'):
          return cls(None), rest[1:].lstrip()
        elif startswith_token(rest, '('):
          raw, rest = split_until(rest, ')')
          s, rest = string_literal.split(ctx, rest)
          if s is not None and rest.startswith(';'):
            return cls(s), rest[1:].lstrip()

class function_body(alternatives('function_body',
                                 regular_function_body,
                                 function_try_block,
                                 explicitly_defaulted_function_definition,
                                 explicitly_deleted_function_definition,)):
  pass

class requires_clause(namedtuple('requires_clause', ['kind', 'parameter_list', 'requirement_seq'])):
  """
  requires { requirement-seq }	(1)	
  requires ( parameter-list ﻿(optional) ) { requirement-seq }	(2)
  """
  def __str__(self):
    r = 'requires'
    if self.kind == '(1)':
      r += '{{ {self.requirement_seq} }}'
    elif self.kind == '(2)':
      if self.parameter_list is None:
        r += ' ()'
      r += '{{ {self.requirement_seq} }}'
    else:
      assert 0, self.kind  # unreachable
    return r

  @splitter
  def split(cls, ctx, line):
    requires, rest = word.split(ctx, line, require='requires')
    if requires:
      lst = None
      kind = '(1)'
      lst = None
      if startswith_token(rest, '('):
        kind = '(2)'
        raw, rest = split_until(rest[1:].lstrip(), ')')
        if raw is not None:
          lst, rest2 = parameter_list.split(ctx, raw)
          if not (lst is None or rest2 == ''):
            return UNEXPECTED
      if startswith_token(rest, '{'):
        raw, rest = split_until(rest[1:].lstrip(), '}')
        if raw is not None:
          seq, rest2 = requirement_seq.split(ctx, raw)
          if seq is not None and rest2=='':
            return cls(kind, lst, seq)


class function_definition(namedtuple('function_definiton', ['kind', 'attr_seq', 'decl_specifier_seq', 'declarator', 'virt_specifier_seq', 'requires_clause', 'function_body'])):
  """
  attr ﻿(optional) decl-specifier-seq ﻿(optional) declarator virt-specifier-seq ﻿(optional) function-body	(1)	
  attr ﻿(optional) decl-specifier-seq ﻿(optional) declarator requires-clause function-body	(2)
  """
  def __str__(self):
    r = str(self.attr_seq or '')
    r += f' {self.decl_specifier_seq}' if self.decl_specifier_seq else ''
    r += (' ' if r else '') + str(self.declarator)
    if self.kind == '(1)':
      if self.virt_specifier_seq:
        r += f' {self.virt_specifier_seq}'
    elif self.kind == '(2)':
      if self.requiers_clause:
        r += f' {self.requires_clause}'
    else:
      assert 0  # unreachable
    r += f' {self.function_body}'
    return r.lstrip()

  @splitter
  def split(cls, ctx, line):

    attr_seq, rest = attribute_specifier_seq.split(ctx, line)
    if 1:
      # First detect constructor definitions:
      seq, rest_ = decl_specifier_seq.split(ctx, rest, has_type_specifier=True)
      ctr, rest_ = constructor.split(ctx, rest_)
      if ctr:
        virt_spec, rest_ = virt_specifier_seq.split(ctx, rest_)
        body, rest_ = function_body.split(ctx, rest_)
        if body:
          return cls('(1)', attr_seq, seq, ctr, virt_spec, None, body), rest_

    seq, rest = decl_specifier_seq.split(ctx, rest)
    decl, rest = declarator.split(ctx, rest)
    # when seq is None, we'll have a constructor or destructor
    #assert 0, rest
    if decl:
      req, rest = requires_clause.split(ctx, rest)
      if req:
        kind = '(2)'
      else:
        kind = '(1)'
        virt_spec, rest = virt_specifier_seq.split(ctx, rest)
      body, rest = function_body.split(ctx, rest)
      if body:
        return cls(kind, attr_seq, seq, decl, virt_spec, req, body), rest


class template_head(namedtuple('template_head', ['template_parameter_list', 'requires_clause'])):
  """
  template < template-parameter-list > requires-clause?
  """
  format = 'template <{0}> {1}'

  @splitter
  def split(cls, ctx, line):
    export, rest = word.split(ctx, line, require='export')
    template, rest = word.split(ctx, rest, require='template')
    if export and template:
      assert 0, rest[:50]  # < C++11 feature

    if template and startswith_token(rest, '<'):
      raw, rest = split_until(rest[1:].lstrip(), '>')
      lst, rest2 = template_parameter_list.split(ctx, raw)
      assert rest is not None, rest2
      if lst and rest2 == '':
        req, rest = requires_clause.split(ctx, rest)
        return cls(lst, req), rest

class template_declaration_declaration(namedtuple('template_declaration_declaration', ['template_head', 'declaration'])):
  """
  template <parameter-list ﻿> requires-clause ﻿(optional) declaration	(1)
  """
  format = '{0} {1}'

  @splitter
  def split(cls, ctx, line):
    head, rest = template_head.split(ctx, line)
    if head is not None:
      decl, rest = declaration.split(ctx, rest)
      if decl is not None:
        return cls(head, decl), rest

class constraint_expression(namedtuple('constraint_expression')): pass

class concept_definition(namedtuple('concept_definition')):
  """
  concept concept-name = constraint-expression ﻿ ;
  """
  format = 'concept {0} = {1} ;'

  @splitter
  def split(cls, ctx, line):
    concept, rest = word.split(ctx, line, require='concept')
    if concept:
      n, rest = concept_name.split(ctx, rest)
      if n:
        if startswith_token(rest, '='):
          expr, rest = constraint_expression.split(ctx, rest[1:].lstrip())
          if expr is not None:
            return cls(n, expr), rest
        return UNEXPECTED

class template_declaration_concept(namedtuple('template_declaration_concept', ['template_head', 'concept'])):
  """
  template <parameter-list ﻿> concept concept-name = constraint-expression ﻿;	(3)
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    head, rest = template_head.split(ctx, line)
    if head is not None:
      c, rest = concept_definition.split(ctx, rest)
      if c is not None:
        return cls(head, c), rest

class template_declaration_with_declaration(namedtuple('template_declaration_with_declaration', ['template_head', 'declaration'])):
  """
  template-head declaration
  """
  format = '{0} {1}'
  @splitter
  def split(cls, ctx, line):
    head, rest = template_head.split(ctx, line)
    if head:
      decl, rest = declaration.split(ctx, rest)
      if decl:
        return cls(head, decl), rest      

class template_declaration(namedtuple('template_declaration')):
  """
  template-head declaration
  template-head concept-definition

  export template <parameter-list ﻿> declaration	(2)	(until C++11) [NOTIMPL]
  """
  @classmethod
  def alternatives(cls):
    return (template_declaration_with_declaration, template_declaration_concept)


class explicit_template_instantiation(namedtuple('explicit_template_instantiation', ['extern', 'class_key', 'template_name', 'argument_list'])):
  """
  template class-key template-name < argument-list > ;	(1)	
  extern template class-key template-name < argument-list > ;	(2)	(since C++11)
  """
  format = '{0} template {1} {2} <{3}> ;'
  @splitter
  def split(cls, ctx, line):
    extern, rest = word.split(ctx, line, require='extern')
    template, rest = word.split(ctx, rest, require='template')
    key, rest = word.split(ctx, rest, require=['class', 'struct', 'union'])
    if template:
      n, rest = template_name.split(ctx, rest)
      if n:
        if startswith_token(rest, '<'):
          raw, rest = split_until(rest[1:].lstrip(), '>')
          if raw and rest.startswith(';'):
            # https://timsong-cpp.github.io/cppwp/temp.names#4
            lst, rest2 = template_argument_list.split(ctx, raw)
            if lst:
              if rest2 == '':
                return cls(extern, key, n, lst), rest[1:].lstrip()
              return UNEXPECTED


class explicit_template_specialization(namedtuple('explicit_template_specialization')):
  """
  template <> declaration
  """
  format = f'template <> {0}'
  @splitter
  def split(cls, ctx, line):
    template, rest = word.split(ctx, line, require='template')
    if template:
      if startswith_token(rest, '<'):
        rest = rest[1:].lstrip()
        if startswith_token(rest, '>'):
          rest = rest[1:].lstrip()
          decl, rest = declaration.split(ctx, rest)
          if decl:
            return cls(decl), rest

class declaration_seq(item_sequence('declaration_seq', declaration)):
  """
  declaration
  declaration-seq declaration
  """

  @splitter
  def __split(cls, ctx, line):
    lst, rest = consume_to_list(ctx, declaration.split, line)
    if lst is not None:
      return cls(tuple(lst)), rest

class namespace_body(namedtuple('namespace_body')):
  """
  declaration-seq?
  """
  @splitter
  def split(cls, ctx, line):
    if line == '':
      return cls(()), line
    return declaration_seq.split(ctx, line)


class ns_name(namedtuple('ns_name')):
  """
  ns-name
  :: ns-name
  ns-name :: member-name
  ns-name ::inline member-name
  """
  format = '{0}'

  @splitter
  def split(cls, ctx, line):
    n = line[0:0]
    rest = line
    while rest:
      if startswith_token(rest, '::'):
        n += rest[:2]
        rest = rest[2:]
        inline, rest = word.split(ctx, rest, require='inline', strip=False)
        if inline:
          if not n:
            break
          d = len(rest) - len(rest.lstrip())
          n += inline + rest[:d]
          rest = rest.lstrip()
      i, rest = identifier.split(ctx, rest)
      if i:
        n += i[0]
        if startswith_token(rest, '::'):
          continue
      break
    if n:
      return cls(n), rest.lstrip()


class named_namespace_definition(namedtuple('named_namespace_definition', ['inline', 'attribute-specifier-seq', 'identifier', 'namespace-body'])):
  """
  inline? namespace                 attribute-specifier-seq? identifier { namespace-body }
  """
  format = '{0} namespace {1} {2} {{{3}}}'
  @splitter
  def split(cls, ctx, line):
    inline, rest = word.split(ctx, line, require='inline')
    namespace, rest = word.split(ctx, rest, require='namespace')
    if namespace:
      a, rest = attribute_specifier_seq.split(ctx, rest)
      i, rest = identifier.split(ctx, rest)

      if i and rest.startswith('{'):
        rest = rest[1:].lstrip()
        if rest.startswith('}'):
          return cls(inline, a, i, None), rest[1:].lstrip()
        head_lines = line[:len(line) - len(rest)]
        b, rest = namespace_body.split(ctx, rest)

        if b:
          if rest.startswith('}'):
            return cls(inline, a, i, b), rest[1:].lstrip()
          _report_unexpected_block_end(cls, head_lines, rest)
          raise RuntimeError(f'unexpected return when parsing {cls.__name__} (see output above)')

class unnamed_namespace_definition(namedtuple('unnamed_namespace_definition', ['inline', 'attribute-specifier-seq', 'namespace-body'])):
  """
  inline? namespace                 attribute-specifier-seq?            { namespace-body }
  """
  format = '{0} namespace {1} {{{2}}}'

  @splitter
  def split(cls, ctx, line):
    inline, rest = word.split(ctx, line, require='inline')
    namespace, rest = word.split(ctx, rest, require='namespace')
    if namespace:
      a, rest = attribute_specifier_seq.split(ctx, rest)
      if rest.startswith('{'):
        head_lines = line[:len(line) - len(rest)]
        b, rest = namespace_body.split(ctx, rest[1:].lstrip())
        if b:
          if rest.startswith('}'):
            return cls(inline, a, b), rest[1:].lstrip()
          _report_unexpected_block_end(cls, head_lines, rest)
          raise RuntimeError(f'unexpected return when parsing {cls.__name__} (see output above)')

class colon_optional_inline(namedtuple('colon_optional_inline')):
  """
  :: inline?
  """
  format = '::{0} '
  @splitter
  def split(cls, ctx, line):
    if line.startswith('::'):
      inline, rest = word.split(ctx, line[2:].lstrip(), require='inline')
      return cls(inline), rest

class enclosing_namespace_specifier(pair_or_item('enclosing_namespace_specifier', [colon_optional_inline], identifier)):
  """
  identifier
  enclosing-namespace-specifier :: inline? identifier
  """

class nested_namespace_definition(namedtuple('nested_namespace_definition', ['enclosing-namespace-specifier', 'inline', 'identifier', 'namespace-body'])):
  """
          namespace enclosing-namespace-specifier :: inline? identifier { namespace-body }
  """
  format = 'namespace {0}::{1} {2} {{{3}}}'
  @splitter
  def split(cls, ctx, line):
    namespace, rest = word.split(ctx, line, require='namespace')

    if namespace:
      s, rest = enclosing_namespace_specifier.split(ctx, rest)
      if isinstance(s, enclosing_namespace_specifier):
        # enclosing_namespace_specifier is greedy
        inline = s.separator[0]
        i = s.right
        s = s.left
        if i and rest.startswith('{'):
          head_lines = line[:len(line) - len(rest)]
          b, rest = namespace_body.split(ctx, rest[1:].lstrip())
          if b:
            if rest.startswith('}'):
              return cls(s, inline, i, b), rest[1:].lstrip()
            _report_unexpected_block_end(cls, head_lines, rest)
            raise RuntimeError(f'unexpected return when parsing {cls.__name__} (see output above)')

class namespace_definition(alternatives('namespace_definition',
                                        nested_namespace_definition,
                                        named_namespace_definition,
                                        unnamed_namespace_definition,
                                        )):
  """
  named-namespace-definition
  unnamed-namespace-definition
  nested-namespace-definition
  """




  
class linkage_specification_seq(namedtuple('linkage_specification_seq', ['unevaluated-string', 'declaration-seq'])):
  """
  extern unevaluated-string { declaration-seq? }
  """
  format = 'extern {0} {{ {1} }}'
  @splitter
  def split(cls, ctx, line):
    extern, rest = word.split(ctx, line, require='extern')
    if extern:
      s, rest = unevaluated_string.split(ctx, rest)
      if s and startswith_token(rest, '{'):
        head_lines = line[:len(line) - len(rest)]
        rest = rest[1:].lstrip()
        if startswith_token(rest, '}'):
          return cls(s, None), rest[1:].lstrip()
        d, rest = declaration_seq.split(ctx, rest)
        if d:
          if not startswith_token(rest, '}'):
            _report_unexpected_block_end(cls, head_lines, rest)
            raise RuntimeError(f'unexpected return when parsing class member specifications (see output above)')
          return cls(s, d), rest[1:].lstrip()

class linkage_specification_declaration(namedtuple('linkage_specification_declaration', ['unevaluated-string', 'name-declaration'])):
  """
  extern unevaluated-string name-declaration
  """
  format = 'extern {0} {1}'
  @splitter
  def split(cls, ctx, line):
    extern, rest = word.split(ctx, line, require='extern')
    if extern:
      s, rest = unevaluated_string.split(ctx, rest)
      if s:
        d, rest = name_declaration.split(ctx, rest)
        if d:
          return cls(s, d), rest
  
class linkage_specification(alternatives('linkage_specification', linkage_specification_seq, linkage_specification_declaration)):
  """
  extern unevaluated-string { declaration-seq? }
  extern unevaluated-string name-declaration
  """

class attribute_declaration(namedtuple('attribute_declaration')):
  """
  attribute-specifier-seq ;
  """
  format = '{0};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    return attribute_specifier_seq.split(ctx, line)

class function_declaration_without_decl_specifier_seq(namedtuple('function_declaration_without_decl_specifier_seq', ['attr', 'function_declarator'])):
  """
  attr ﻿(optional) function-declarator ;

  function declarator declares a constructor, destructor, or user-defined type conversion function
  """
  format = '{0} {1} ;'

  @splitter
  def split(cls, ctx, line):
    attr, rest = attribute_specifier_seq.split(ctx, line)
    decl, rest = function_declarator.split(ctx, rest)
    if decl is not None and rest.startswith(';'):
      return cls(attr, decl), rest

  
class empty_declaration(namedtuple('empty_declaration', ['unused'], defaults=['unused'])):
  format = ';'
    
  @splitter
  def split(cls, ctx, line):
    if line.startswith(';'):
      return cls(), line[1:].lstrip()

class global_module_fragment(namedtuple('global_module_fragment')):
  """
  module-keyword ; declaration-seq?
  """
  format = 'module; {0}'
  @splitter
  def split(cls, ctx, line):
    m, rest = word.split(ctx, line, require='module')
    if m:
      s, rest = declaration_seq.split(ctx, rest)
      return cls(m, s), rest

class identifier_with_a_dot(namedtuple('identifier_with_a_dot')):
  """
  identifier .
  """
  format = '{0}.'
  @splitter
  def split(cls, ctx, line):
    i, rest = identifier.split(ctx, line)
    if i and startswith_token(rest, '.'):
      return cls(i), rest[1:].lstrip()

class module_name_qualifier(item_sequence("module_name_qualifier", identifier_with_a_dot)):
  """
  identifier .
  module-name-qualifier identifier .
  """

class module_name(item_optional_prefix(identifier, module_name_qualifier)):
  """
  module-name-qualifier? identifier
  """

class module_partition(namedtuple('module_partition', ['module-name-qualifier', 'identifier'])):
  """
  : module-name-qualifier? identifier
  """
  format = ': {0} {1}'
  @splitter
  def split(cls, ctx, line):
    if startswith_token(line, ':'):
      rest = line[1:].lstrip()
      q, rest = module_name_qualifier.split(ctx, rest)
      i, rest = identifier.split(ctx, rest)
      if i:
        return cls(q, i), rest

class module_declaration(namedtuple('module_declaration')):
  """
  export-keyword? module-keyword module-name module-partition? attribute-specifier-seq? ;
  """
  format = '{0} module {2} {3} {4};'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    e, rest = word.split(ctx, line, require='export')
    module, rest = word.split(ctx, rest, require='module')
    if module:
      n, rest = module_name.split(ctx, rest)
      if n:
        p, rest = module_partition.split(ctx, rest)
        a, rest = attribute_specifier_seq.split(ctx, rest)
        return cls(e, n, p, a), rest

class private_module_fragment(namedtuple('private_module_fragment')):
  """
  module-keyword : private ; declaration-seq?
  """
  format = 'module : private; {0}'
  @splitter
  @_require_and_drop_semicolon
  def split(cls, ctx, line):
    module, rest = word.split(ctx, line, require='module')
    if module and startswith_token(rest, ':'):
      rest = rest[1:].lstrip()
      private, rest = word.split(ctx, rest, require='private')
      if private and rest.startswith(';'):
        s, rest = declaration_seq.split(ctx, rest[1:].lstrip())
        return cls(s), rest

class translation_unit(namedtuple('translation_unit', ['global-module-fragment', 'module-declaration', 'declaration-seq', 'private-module-fragment'])):
  """
                                             declaration-seq?
  global-module-fragment? module-declaration declaration-seq? private-module-fragment?
  """
  format = '{0} {1} {2} {3}'
  @splitter
  def split(cls, ctx, line):
    gf, rest = global_module_fragment.split(ctx, line)

    m, rest = module_declaration.split(ctx, rest)

    head_lines = line[:len(line) - len(rest)]
    s, rest = declaration_seq.split(ctx, rest)
    pf, rest = private_module_fragment.split(ctx, rest)

    if rest:
      _report_unexpected_block_end(cls, head_lines, rest)
      raise RuntimeError(f'unexpected return when parsing {cls.__name__} (see output above)')
    if (gf or pf and m) or not (gf or pf or m):
      return cls(gf, m, s, pf), rest

