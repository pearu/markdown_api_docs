import os
import traceback

from . import utils

def _recursive(func):
  def wrapper(line, *args, **kwargs):
    r, rest = func(line, *args, **kwargs)
    result = ''
    while r:
      result += r
      r, rest = func(rest, *args, **kwargs)
    return result, rest
  return wrapper

def _split_identifier(line):
  if not (line and (line[0].isalpha() or line[0] == '_')):
    return None, line
  i = 1
  while i < len(line) and (line[i].isalnum() or line[i] == '_'):
    i += 1
  return line[:i], line[i:].lstrip()


def _split_type_qualifiers(line):
  for q in {'const', 'volatile', 'mutable'}:
    if line == q or (line.startswith(q) and not (line[len(q)].isalnum() or line[len(q)] == '_')):
      return q, line[len(q):].lstrip()
  return None, line

def _split_type(line):
  q, rest = _split_type_qualifiers(line)
  level = 0
  for i in range(len(rest)):
    if rest[i] == '<':
      level += 1
    elif rest[i] == '>':
      level -= 1
    elif rest[i] in {' ', '*', '&'} and level == 0 and i < len(rest)-1 and (rest[i + 1].isalpha() or rest[i + 1] == '_'):
      typ = rest[:i+1].rstrip()
      if q and typ:
        typ = q + ' ' + typ
      return typ, rest[i+1:].lstrip()
  assert level == 0, (line, q, rest, level)
  return line, ''


def _split_marks(line, marks):
  stack = []
  pmap = {'<': '>', '(': ')', '{': '}', '[': ']'}
  for i in range(len(line)):
    if line[i] in pmap:
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack and line[i] in marks:
      return line[:i+1].rstrip(), line[i+1:].lstrip()
  return None, line

def _split_scope(line):
  stack = []
  pmap = {'<': '>', '(': ')', '{': '}', '[': ']'}
  for i in range(len(line)):
    if line[i] in pmap:
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack:
      if line[i:i + 2] == '::':
        return line[:i+2].rstrip(), line[i+2:].lstrip()
      if not (line[i].isalnum() or line[i] == '_'):
        break
  return None, line

def _split_specifier(line):
  for specifier in {'virtual', 'explicit', 'inline'}:
    if line.startswith(specifier + ' '):
      spec, rest = _split_specifier(line[len(specifier):].lstrip())
      if spec:
        return specifier + ' ' + spec, rest
      return specifier, rest
  return '', line

def _split_extern_C(line):
  if line.startswith('extern "C"'):
    return True, line[10:].lstrip()
  return False, line

def _split_template(line):
  assert line.startswith('template'), line
  if '<' not in line[:10]:
    j = 8
  else:
    level = 0
    flag = False
    for i_ in range(len(line)):
      if line[i_] == '>':
        # todo: make sure that line[_i] is not a part of right-shift operations
        level -= 1
        if level == 0:
          j = i_ + 1
          break
      elif line[i_] == '<':
        # make sure that line[_i] is not a part of left-shift operations
        # todo: make it more robust
        if not (line[i_ - 1] == '<' or (i_ < len(line) and line[i_ + 1] == '<')):
          level += 1
    assert level == 0, (line, level)
  rest = line[j:].lstrip()
  if rest.startswith('template '):
    tmpl, rest = _split_template(rest)
    return line[:j] + ' ' + tmpl, rest
  return line[:j], rest


def cacheit(mth):
  def wrapper(self, *args, **kwargs):
    if mth.__name__ in self._cache:
      return self._cache[mth.__name__]
    r = self._cache[mth.__name__] = mth(self, *args, **kwargs)
    return r
  return wrapper

class Node:

  block_kinds = ['class', 'struct', 'enum class', 'enum struct', 'enum', 'typedef enum', 'typedef struct', 'union']
  @classmethod
  def fromstring(cls, parent, line, **params):
    assert '' not in params.get('namespace', [])
    extern_C, line = _split_extern_C(line)
    if extern_C:
        params['extern_C'] = True
    for kind in cls.block_kinds:
      if line.startswith(kind + ' ') or line == kind:
        return Node(parent, kind, line, **params)
    if line.startswith('template'):
      # assert 0, line  # template is resolved when reading sources
      tmpl, line = _split_template(line)
      return cls.fromstring(parent, line, template=tmpl, **params)
    elif line.startswith('using namespace '):
      lineno = params.get('lineno', '')
      print(f'{parent.filename}#{lineno}:`{line}`  <- ignoring as not implemented')
    elif line.startswith('using '):
      if '=' in line:
        name, value = line.split(None, 1)[1].split('=', 1)
        name = name.strip()
        if value.endswith(';'):
          value = value[:-1]
        value = value.strip()
        parent.using[name] = value
      else:
        name = line.split(None, 1)[1]
        if name.endswith(';'):
          name = name[:-1]
        name = name.strip()
        parent.using[name] = None
      return
    elif '(' in line:
      specifier, rest = _recursive(_split_specifier)(line)
      scope, rest = _recursive(_split_scope)(rest)
      if rest.startswith('~'):
        n, rest = _split_identifier(rest[1:].lstrip())
        if n and rest.startswith('('):
          if parent.kind in {'class', 'struct'}:
            if parent.name == n:
              return Node(parent, 'destructor', line, **params)
        lineno = params.get('lineno', '')
        print(f'{parent.filename}#{lineno}:`{line}`  <- ignoring as unknown')
        return
      cpp_defines = list(parent.params.get("cpp_data", dict()).get('define', dict()))
      n, rest = utils.split_identifier(rest)
      if n in parent.cpp_defines:
        return Node(parent, 'cpp_macro_apply', line, **params)
      print(f'{parent.file.path=}')
      print(f'{line=} {parent.kind=} {n=} {rest=}')
      if n and rest.startswith('('):
        if parent.kind in {'class', 'struct'}:
          if parent.name == n:
            return Node(parent, 'constructor', line, **params)
        if n.isupper():
          # likely a CPP macro apply
          return Node(parent, 'cpp_macro_apply', line, **params)
        lineno = params.get('lineno', '')
        print(f'{parent.filename}#{lineno}:`{line}`  <- ignoring as unknown')
        return
      return Node(parent, 'function', line, **params)
    elif line:
      if parent.kind in {'enum', 'enum class', 'enum struct', 'typedef enum'}:
        return Node(parent, 'constant', line, **params)
      n, rest = _split_identifier(line)
      if n and rest == ';' and parent.kind == 'file':
        lineno = params.get('lineno', '')
        print(f'{parent.filename}#{lineno}:`{line}`  <- ignoring as unknown')
        return
      return Node(parent, 'attribute', line, **params)

  def __init__(self, parent, kind, spec, **params):
    self.parent = parent
    self.kind = kind
    assert spec, (kind)
    self.spec = spec
    self.params = params
    self.content = []
    self._cache = dict()

  def __str__(self):
    return self.tostring()

  @property
  @cacheit
  def path(self):
    if self.parent is None:
      return os.path.relpath(self.spec, self.root_path)
    elif self.kind in {'file', 'directory'}:
      return os.path.relpath(self.spec, self.root.spec)
    assert 0  # unreachable

  def tostring(self, tab=''):
    lineno = self.params.get('lineno')
    if self.kind == 'directory':
      lines = [f'ROOT={self.path}'] if self.parent is None else [f'Directory: ROOT/{self.path}']
      for item in self.content:
        lines.append(item.tostring(tab=tab+'  '))
      return '\n'.join(lines)
    elif self.kind == 'file':
      path = f'ROOT/{self.path}' if self.root_path else self.path
      lines = [f'// File: {path}']
      for item in self.content:
        lines.append(item.tostring(tab=tab+'  '))
      return '\n'.join(lines)
    elif self.kind in self.block_kinds:
      base = ''
      if self.kind in {'class', 'struct'}:
        bases = []
        for bname, access in self.data['bases'].items():
          if access == 'public':
            bases.append(bname)
        base = ": " + ', '.join(bases) if bases else ''
      if self.spec.endswith(';'):
        return f'{lineno:3}:{tab}{self.spec}  // `{self.type_prefix}{self.kind} {self.name_prefix}{self.name}{base}`'
      lines = [f'{lineno:3}:{tab}{self.spec} {{  // `{self.type_prefix}{self.kind} {self.name_prefix}{self.name}{base}`']
      for item in self.content:
        lines.append(item.tostring(tab=tab+'  '))
      lines.append(f'   :{tab}}}')
      return '\n'.join(lines)
    else:
      assert not self.content, (self.kind, self.spec, lineno)
      if lineno is None:
        return f'{tab}{self.spec}'
      if self.kind == 'constructor':
        return f'{lineno:3}:{tab}{self.spec}  // `{self.type_prefix} {self.name_prefix}{self.name}`'
      if self.kind == 'destructor':
        return f'{lineno:3}:{tab}{self.spec}  // `{self.type_prefix} {self.name_prefix}~{self.name}`'
      if self.kind in {'function'}:
        return f'{lineno:3}:{tab}{self.spec}  // `{self.type_prefix}{self.rtype} {self.name_prefix}{self.name}`'
      if self.kind in {'attribute'}:
        return f'{lineno:3}:{tab}{self.spec}  // `{self.type_prefix}{self.vtype} {self.name_prefix}{self.name}`'
      return f'{lineno:3}:{tab}{self.spec}   !! {self.kind}'

  @property
  def using(self):
    if 'using' not in self.params:
      self.params['using'] = {}
    return self.params['using']

  @property
  @cacheit
  def filename(self):
    if self.kind == 'file':
      return self.spec
    if self.parent is not None:
      return self.parent.filename

  @property
  @cacheit
  def root(self):
    if self.parent is None:
      return self
    else:
      return self.parent.root

  @property
  @cacheit
  def root_path(self):
    if self.parent is None:
      return self.params.get('root_path')
    else:
      return self.parent.root_path

  def set_root_path(self, path):
    if self.parent is None:
      self.params['root_path'] = path
    else:
      self.parent.set_root_path(path)

  @property
  @cacheit
  def file(self):
    if self.kind == 'file':
      return self
    if self.parent is not None:
      return self.parent.file

  @property
  @cacheit
  def directory(self):
    if self.kind == 'directory':
      return self
    if self.parent is not None:
      return self.parent.directory

  @property
  @cacheit
  def comment_text(self):
    lineno = self.params.get('lineno')
    if lineno is not None:
      f = self.file
      if f is not None:
        comments = f.params.get('comments', dict())
        return comments.get(lineno)

  @property
  @cacheit
  def data(self):
    """Return node data using its spec string.
    """
    # 
    line = self.spec
    data = dict()
    if self.kind == 'function':
      print(f'>>>>>>>>>>>>>>> {self.spec=}')
      extern_C, line = _split_extern_C(self.spec)
      fspec, line = utils.split_function_specifier(line)
      print(f'{fspec=} {line=}')
      rtype, line = utils.split_type(line)
      print(f'{rtype=} {line=}')
      scope, line = utils.split_scope(line, recursive_str=True)
      print(f'{scope=} {line=}')
      name, line = utils.split_identifier(line)
      print(f'{name=} {line=}')
      assert line.startswith('('), (line, self.spec)
      args_lst, line = utils.split_marks(line[1:].lstrip(), ',)', recursive_list=True, keep_mark=False)
      print(f'{args_lst=} {line=}')

      args = []
      for a in args_lst:
        atype_spec, rest = utils.split_type_specifier(a)
        atype, rest = utils.split_type(rest)
        print(f'----------------- {atype=} {rest=}')
        aname, rest = utils.split_identifier(rest)
        if aname:
          if rest.startswith('='):
            init = rest[1:].lstrip()
          else:
            init = None
        else:
          aname = None
          init = None
        if atype_spec:
          atype = atype_spec + ' ' + atype
        args.append((atype, aname, init))

      print(f'{args=}')

      cv, line = utils.split_cv_qualifier(line)
      print(f'{cv=} {line=}')
      mspec, line = utils.split_method_specifier(line)
      print(f'{mspec=} {line=}')
      virtual, line = utils.split_virtual_specifier(line)
      print(f'{virtual=} {line=}')
      assert not line or line == ';' or line == '{}', (line, self.spec)

      data.update(
          extern_C=extern_C,
          function_spec=fspec,
          rtype=rtype,
          scope=scope,
          name=name,
          cv=cv,
          mspec=mspec,
          virtual=virtual,
          args=args,                         # list of (type, name, init)
          arguments='(' + ', '.join(args_lst) + ')',
      )

    elif self.kind in {'class', 'struct'}:
      assert line.startswith(self.kind), (self.kind, line)
      line = line[len(self.kind):].lstrip()
      attrs, line = utils.split_attribute_specifier(line)
      scope, line = utils.split_scope(line, recursive_str=True)
      name, line = utils.split_identifier(line)
      if line.startswith('<'):
        tparam, line = utils.split_marks(line, ' ;\n', pmap={'<': '>'})
        if tparam:
          if tparam.endswith(';'):
            tparam = tparam[:-1]
            line = ';' + line
            assert tparam.endswith('>'), (tparam, line, self.spec)
          else:
            tparam = tparam.rstrip()
      else:
        tparam = ''
      final, line = utils.split_keywords(line, 'final')
      bases = dict()
      if line.startswith(':'):
        base_specifiers, line = utils.split_marks(line[1:].lstrip(), ',{;\n', recursive_list=True)
        assert not line, (line, self.spec, base_specifiers)
        if base_specifiers[-1][-1] in ',{;':
          line = base_specifiers[-1][-1] + line
        for spec in base_specifiers:
          access_spec, bname = utils.split_access_specifier(spec)
          if bname[-1] in ',{;':
            bname = bname[:-1].rstrip()
          bases[bname] = access_spec
      assert not line or line.endswith(';') or line.endswith('{}'), (line, self.spec)

      data.update(name=name, tparam=tparam,
                  scope=scope, final=final == 'final', template=self.params.get('template'),
                  bases=bases)
    else:
      assert 0, self.kind  # not impl
    return data

  @property
  @cacheit
  def name(self):
    if self.kind in {'file', 'directory'}:
      return os.path.basename(self.spec)
    elif self.kind in {'class', 'struct'}:
      return self.data['name']
    elif self.kind == 'constructor':
      specifier, rest = _recursive(_split_specifier)(self.spec)
      scope, rest = _recursive(_split_scope)(rest)
      name, _ = _split_identifier(rest)
      assert name is not None
      return name
    elif self.kind == 'destructor':
      specifier, rest = _recursive(_split_specifier)(self.spec)
      scope, rest = _recursive(_split_scope)(rest)
      assert rest.startswith('~'), self.spec
      rest = rest[1:].lstrip()
      name, _ = _split_identifier(rest)
      assert name is not None, rest
      return name
    elif self.kind == 'function':
      return self.data['name']
      specifier, line = _recursive(_split_specifier)(self.spec)
    elif self.kind == 'cpp_macro_apply':
      name, _ = _split_identifier(self.spec)
      assert name is not None, line
      return name
    elif self.kind == 'attribute':
      line = self.spec[len(self.vtype):].lstrip()
      name, _ = _split_identifier(line)
      return name
    elif self.kind in {'enum', 'enum class', 'enum struct', 'typedef enum', 'typedef struct', 'union'}:
      line = self.spec[len(self.kind):].lstrip()
      name, _ = _split_identifier(line)
      return name
    assert 0, (self.kind, self.spec)  # not impl

  @property
  @cacheit
  def arguments(self):
    if self.kind == 'destructor':
      return []
    if self.kind in {'function', 'constructor'}:
      return self.data['arguments']
    assert 0, (self.kind, self.spec)  # not impl

  @property
  @cacheit
  def arguments_data(self):
    return self.data['args']

  @property
  @cacheit
  def ttype(self):
    assert self.kind in {'class', 'struct', 'function'}, self.kind
    return self.params.get('template', '')

  @property
  @cacheit
  def isconstructor(self):
    return self.kind == 'constructor'

  @property
  @cacheit
  def isdestructor(self):
    return self.kind == 'destructor'

  @property
  @cacheit
  def rtype(self):
    if self.kind == 'function':
      if self.isconstructor or self.isdestructor:
        return ''
      return self.data['rtype']
    assert 0, self.kind  # unreachable

  @property
  @cacheit
  def vtype(self):
    if self.kind == 'attribute':
      extern_C, line = _split_extern_C(self.spec)
      typ, _ = _split_type(line)
      return typ
    assert 0, self.kind  # unreachable
    
  @property
  @cacheit
  def namespace(self):
    if self.parent.kind in {'class', 'struct'}:
        return self.parent.namespace + '::' + self.parent.name
    if self.kind in {'function', 'attribute'}:
      return '::'.join(self.params.get('namespace', []))
    elif self.kind in self.block_kinds:
      return '::'.join(self.params.get('namespace', []))
    else:
      assert 0, self.kind  # unreachable

  @property
  @cacheit
  def label(self):
    label = self.kind + '-' + self.namespace.replace('::','-') + '-' + self.name
    # ensure label is unique for overloaded functions/methods:
    if 'labels' not in self.root._cache:
      self.root._cache['labels'] = dict()
    labels = self.root._cache['labels']
    if label not in labels:
      labels[label] = 0
    else:
      labels[label] += 1
    extra = labels[label]
    suffix = f'-{extra}' if extra else ''
    return label + suffix

  @property
  @cacheit
  def source_ref(self):
    lineno = self.params.get('lineno')
    return f'{self.file.name}#{lineno}' if lineno else self.file.path

  @property
  @cacheit
  def name_prefix(self):
    if self.params.get('extern_C'):
      return ''
    if self.kind in {'struct', 'class'}:
      scope = self.data.get('scope')
      if scope:
        return self.namespace + '::' + scope + '::'
    return self.namespace + '::'

  @property
  @cacheit
  def scope(self):
    if self.params.get('extern_C'):
      return 'extern "C"'
    return self.namespace + '::'

  @property
  @cacheit
  def type_prefix(self):
    prefixes = []
    if self.params.get('extern_C'):
      prefixes.append('extern "C" ')
    if self.params.get('template'):
      prefixes.append(self.params['template'] + ' ')
    return ''.join(prefixes)

  @property
  @cacheit
  def cpp_defines(self):
    if self.kind == 'file':
      return self.params.get('cpp_data', dict()).get('define', dict())
    if self.kind == 'directory':
      assert 0  # unreachable
    return self.parent.cpp_defines

  def add(self, node):
    assert node.parent is None or node.parent is self
    node.parent = self
    try:
      node.tostring()
    except Exception as msg:
      traceback.print_exc(-4)
      print(f'skip adding node: {type(msg).__name__}({msg})')
      print(f'                  {node.params.get("lineno", '')}:{node.spec}')
      print(f'                  {self.filename}')
      raise
        
      return
    self.content.append(node)

  def collect(self, *kinds, **options):
    level = options.get('level', -1)
    if self.kind in kinds:
      yield self
    if level == 0:
      return
    for item in self.content:
      yield from item.collect(*kinds, **dict(level=level - 1))

  def find(self, kind, name, scope=None):
    for node in self.root.collect(kind):
      if node.name != name:
        continue
      if scope is not None:
        if node.data['scope'] == scope:
          return node
