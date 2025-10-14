import collections

class _REQUIRED(object): pass
REQUIRED = _REQUIRED()

def namedtuple(name, *args, **kwargs):

  def eq(self, other):
    return type(self) is type(other) and tuple(self) == tuple(other)

  def repr(self):
    data = [f'{k}={v!r}' for k, v in self._asdict().items() if v is not None]
    return f'{type(self).__name__}({", ".join(data)})'

  return type(name, (collections.namedtuple(name, *args, **kwargs),), dict(__eq__=eq, __repr__=repr))


def recursive(func):
  def wrapper(line, *args, **kwargs):
    recursive_lst = kwargs.pop('recursive_list', None)
    recursive_str = kwargs.pop('recursive_str', None)
    assert not kwargs or list(kwargs)==['keep_mark'], kwargs
    r, rest = func(line, *args, **kwargs)
    print(f'1: {r=}')
    if not (recursive_lst or recursive_str):
      assert not recursive_lst
      print(f'3: {r=}')
      return r, rest
    raise
    if recursive_str:
      result = ''
      while r:
        result += r
        r, rest = func(rest, *args, **kwargs)
      print(f'4: {result=}')
      return result, rest
    elif recursive_lst:
      result = []
      while r is not None:
        print(f'2: {r=}')
        result.append(r)
        r, rest = func(rest, *args, **kwargs)
      print(f'{result=}')
      return result, rest
    else:
      assert 0  # unreachable

  return wrapper


class simple_template_id(namedtuple('simple_template_id', ['name', 'args'], defaults=[REQUIRED, REQUIRED])):
  def __str__(self):
    return f'{self.name}<{self.args}>'

class scope_list(namedtuple('scope_list', ['names'], defaults=[REQUIRED])):
  def __str__(self):
    return '::'.join(self.names) + '::'

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

def split_word(line):
  if line and startswith_identifier0(line):
    for i in range(1, len(line)):
      if not startswith_identifier(line[i]):
        word = line[:i].rstrip()
        return word, line[i:].lstrip()
    return line, ''
  return None, line

def split_keyword(line):
  word, rest = split_word(line)
  if word in keywords:
    return word, rest
  return None, line

def split_identifier(line):
  word, rest = split_word(line)
  if word not in keywords:
    return word, rest
  return None, line

class unqualified_id_declarator(namedtuple('unqualified_id_declarator', ['id', 'attr'], defaults=[REQUIRED, None])):
  def __str__(self):
    if self.attr:
      return f'{self.id} {self.attr}'
    return str(self.id)
  @property
  def name(self):
    return str(self.id)
  @property
  def qname(self):
    return str(self.id)

class qualified_id_declarator(namedtuple('qualified_id_declarator', ['scope', 'id', 'attr'], defaults=[REQUIRED, REQUIRED, None])):
  def __str__(self):
    r = f'{self.scope}{self.id}'
    if self.attr:
      r += f' {self.attr}'
    return r
  @property
  def name(self):
    return str(self.id)
  @property
  def qname(self):
    return f'{self.scope}{self.id}'


class parameter_pack_declarator(namedtuple('parameter_pack_declarator', ['id', 'attr'], defaults=[REQUIRED, None])):
  def __str__(self):
    if self.attr:
      return f'...{self.id} {self.attr}'
    return f'...{self.id}'
  @property
  def name(self):
    return str(self.id)
  @property
  def qname(self):
    return str(self.id)

class pointer_declarator(namedtuple('pointer_declarator', ['attr', 'cv', 'declarator'], defaults=[None, None, REQUIRED])):
  def __str__(self):
    extra = []
    if self.attr:
      extra.append(str(self.attr))
    if self.cv:
      extra.append(str(self.cv))
    extra = ' '.join(extra)
    return f'* {extra} {self.declarator}'
  @property
  def name(self):
    return self.declarator.name
  @property
  def qname(self):
    return self.declarator.qname

  @classmethod
  def split(cls, line):
    if line.startswith('*'):
      rest = line[1:].lstrip()
      attr, rest = split_attribute_specifier(rest)
      cv, rest = split_cv_qualifier(rest)
      decl, rest = declarator.split(rest)
      if decl:
        return cls(attr, cv, decl), rest
    return None, line

class pointer_to_member_declarator(namedtuple('pointer_to_member_declarator', ['nested_name_specifier', 'attr', 'cv', 'declarator'], defaults=[REQUIRED, None, None, REQUIRED])):
  def __str__(self):
    extra = []
    if self.attr:
      extra.append(str(self.attr))
    if self.cv:
      extra.append(str(self.cv))
    extra = ' '.join(extra)
    return f'{self.nested_name_specifier}* {extra} {self.declarator}'
  @property
  def name(self):
    return self.declarator.name
  @property
  def qname(self):
    return self.declarator.qname

  @classmethod
  def split(cls, line):
    nested_name_spec, rest = nested_name_specifier.split(rest)
    if nested_name_spec:
      if rest.startswith('*'):
        rest = rest[1:].lstrip()
        attr, rest = split_attribute_specifier(rest)
        cv, rest = split_cv_qualifier(rest)
        decl, rest = declarator.split(rest)
        if decl:
          return cls(attr, cv, decl), rest
    return None, line

class lvalue_reference_declarator(namedtuple('lvalue_reference_declarator', ['attr', 'declarator'], defaults=[None, REQUIRED])):
  def __str__(self):
    extra = []
    if self.attr:
      return f'& {self.attr} {self.declarator}'
    return f'& {self.declarator}'
  @property
  def name(self):
    return self.declarator.name
  @property
  def qname(self):
    return self.declarator.qname

  @classmethod
  def split(cls, line):
    if line.startswith('&'):
      rest = line[1:].lstrip()
      attr, rest = split_attribute_specifier(rest)
      decl, rest = declarator.split(rest)
      if decl:
        return cls(attr, decl), rest
    return None, line
  
class rvalue_reference_declarator(namedtuple('rvalue_reference_declarator', ['attr', 'declarator'], defaults=[None, REQUIRED])):
  def __str__(self):
    extra = []
    if self.attr:
      return f'&& {self.attr} {self.declarator}'
    return f'&& {self.declarator}'
  @property
  def name(self):
    return self.declarator.name
  @property
  def qname(self):
    return self.declarator.qname

  @classmethod
  def split(cls, line):
    if line.startswith('&&'):
      rest = line[2:].lstrip()
      attr, rest = split_attribute_specifier(rest)
      decl, rest = declarator.split(rest)
      if decl:
        return cls(attr, decl), rest
    return None, line

class array_declarator(namedtuple('array_declarator', ['noptr_declarator', 'constexpr', 'attr'], defaults=[REQUIRED, None, None])):
  def __str__(self):
    r = f'{self.noptr_declarator}[{self.constexpr or ""}]'
    if self.attr:
      return f'{r} {self.attr}'
    return r
  @property
  def name(self):
    return self.noptr_declarator.name
  @property
  def qname(self):
    return self.noptr_declarator.qname

class function_declarator(namedtuple('function_declarator', ['kind', 'noptr_declarator', 'parameter_list', 'cv', 'ref', 'exc', 'attr', 'trailing'], defaults=[REQUIRED, REQUIRED, None, None, None, None, None, None])):
  def __str__(self):
    r = str(self.noptr_declarator)
    if r.startswith('&') or r.startswith('*'):
      r = f'({r})'
    r += f'({self.parameter_list or ""})'
    if self.cv:
      r += f' {self.cv}'
    if self.ref:
      r += f' {self.ref}'
    if self.except_:
      r += f' {self.exc}'
    if self.attr:
      r += f' {self.attr}'
    return r
  @property
  def name(self):
    return self.noptr_declarator.name
  @property
  def qname(self):
    return self.noptr_declarator.qname

  @classmethod
  def split(cls, line):
    assert 0  # not impl

class declarator(namedtuple('declarator', ['kind', 'attr', 'identifier'], defaults=[REQUIRED, None, None])):
  def __str__(self):
    pass

  @classmethod
  def split(cls, line):
    for split in [
        pointer_declarator.split,
        pointer_to_member_declarator.split,
        rvalue_reference_declarator.split,
        lvalue_reference_declarator.split,
        parameter_pack_expansion.split,
        array_declarator.split,
        function_declarator.split,
        name_declarator.split,
    ]:
      decl, rest = split(line)
      if decl:
        return decl, rest
      return None, line

  
class decltype_specifier(namedtuple('decltype_specifier', ['expr'], defaults=[REQUIRED])):
  def __str__(self):
    return f'decltype({self.expr})'

  @classmethod
  def split(cls, line):
    if line.startswith('decltype'):
      rest = line[len('decltype'):].lstrip()
      if rest.startswith('('):
        expr, rest = split_marks(rest[1:].lstrip(), ')', keep_mark=False)
        if expr and expr != 'auto':
          return cls(expr), rest
    return None, line

split_decltype_specifier = decltype_specifier.split

def __split_decltype_specifier(line):
  if line.startswith('decltype'):
    rest = line[len('decltype'):].lstrip()
    if rest.startswith('('):
      expr, rest = split_marks(rest[1:].lstrip(), ')', keep_mark=False)
      if expr and expr != 'auto':
        return decltype_specifier(expr), rest
  return None, line

class class_or_computed(namedtuple('class_or_computed', ['nested_name_spec', 'istemplate', 'tname'], defaults=[None, False, REQUIRED])):
  def __str__(self):
    r = str(self.nested_name_spec) if self.nested_name_spec else ''
    if self.istemplate:
      r += ' template'
    return f'{r} {self.tname}'

  @classmethod
  def split(cls, line):
    istemplate = False
    nested_name_spec, rest = split_nested_name_specifier(line)
    if rest.startswith('template') and not startswith_identifier(rest[len('template'):]):
      istemplate = True
      if nested_name_spec:
        tid, rest = split_simple_template_id(rest[len('template'):].lstrip())
        if tid:
          return cls(nested_name_spec, istemplate, tid), rest
    else:
      tname, rest = split_name(rest)
      if tname:
        return cls(nested_name_spec, istemplate, tname), rest
    decltype_spec, rest = split_decltype_specifier(line)
    if decltype_spec:
      return decltype_spec, rest
    typedef_name, rest = split_name(line)
    if rest.startswith('...'):
      raise NotImplementedError('pack-index-specifier: `{line}`')
    return None, line

split_class_or_computed = class_or_computed.split

def __split_class_or_computed(line):
  istemplate = False
  nested_name_spec, rest = split_nested_name_specifier(line)
  if rest.startswith('template') and not startswith_identifier(rest[len('template'):]):
    istemplate = True
    if nested_name_spec:
      tid, rest = split_simple_template_id(rest[len('template'):].lstrip())
      if tid:
        return class_or_computed(nested_name_spec, istemplate, tid), rest
  else:
    tname, rest = split_name(rest)
    if tname:
      return class_or_computed(nested_name_spec, istemplate, tname), rest
  decltype_spec, rest = split_decltype_specifier(line)
  if decltype_spec:
    return decltype_spec, rest
  typedef_name, rest = split_name(line)
  if rest.startswith('...'):
    raise NotImplementedError('pack-index-specifier: `{line}`')
  return None, line

class base_specifier(namedtuple('base_specifier', ['kind', 'attr', 'access_spec', 'class_or_computed'], defaults=[REQUIRED, None, None, REQUIRED])):
  def __str__(self):
    r = str(self.attr) if self.attr else ''
    if self.kind == '(1)':
      pass
    elif self.kind == '(2)':
      r += (' ' if r else '') + 'virtual'
    elif self.kind == ('3'):
      r += (' ' if r else '') + str(self.assess_spec)
    elif self.kind == '(4)':
      r += (' ' if r else '') + str(self.assess_spec) + ' virtual'
    elif self.kind == '(5)':
      r += (' ' if r else '') + 'virtual ' + str(self.assess_spec)
    else:
      assert 0  # unreachable
    r += (' ' if r else '') + str(self.class_or_computed)
    return r

  @classmethod
  def split(cls, line):
    attr, rest = split_attribute_specifier(line)
    kind = '(1)'
    if startswithword(rest, 'virtual'):
      kind = '(2)'
      rest = rest[len('virtual'):].lstrip()
    access_spec = None
    for k in ['private', 'public', 'protected']:
      if startswithword(rest, k):
        access_spec = k
        rest = rest[len(k):].lstrip()
        kind = '(4)' if kind == '(2)' else '(3)'
        break
    if access_spec and startswithword(rest, 'virtual'):
      rest = rest[len('virtual'):].lstrip()
      kind = '(5)'
    class_or_computed, rest = split_class_or_computed(rest)
    if class_or_computed:
      return cls(kind, attr, access_spec, class_or_computed), rest
    return None, line

split_base_specifier = base_specifier.split
  
def __split_base_specifier(line):
  attr, rest = split_attribute_specifier(line)
  isvirtual = False
  if rest.startswith('virtual') and not startswith_identifier0(rest[len('virtual'):]):
    isvirtual = True
    rest = rest[len('virtual'):].lstrip()
  access_spec = None
  for k in ['private', 'public', 'protected']:
    if rest.startswith(k) and not startswith_identifier(rest[len(k):]):
      access_spec = k
      rest = rest[len(k):].lstrip()
      break
  if rest.startswith('virtual') and not startswith_identifier(rest[len('virtual'):]):
    isvirtual = True
    rest = rest[len('virtual'):].lstrip()
  class_or_computed, rest = split_class_or_computed(rest)
  if class_or_computed:
    return base_specifier(attr, access_spec, isvirtual, class_or_computed), rest
  return None, line


class base_clause(namedtuple('base_clause', ['base_specifiers'], defaults=[REQUIRED])):
  def __str__(self):
    return ': ' + ', '.join(map(str, self.base_specifiers))

  @classmethod
  def split(cls, line):
    if not line.startswith(':'):
      return None, line
    rest = line[1:].lstrip()
    lst = []
    for p, rest in iter_split_marks(rest, ',', keep_mark=False):
      base_spec, r = base_specifier.split(p)
      if base_spec:
        lst.append(base_spec)
      else:
        rest = r + rest
        break
    if lst:
      return cls(lst), rest
    return None, line

split_base_clause = base_clause.split
  
def __split_base_clause(line):
  if not line.startswith(':'):
    return None, line
  rest = line[1:].lstrip()
  base_spec, rest = split_base_specifier(rest)
  if not base_spec:
    return None, line
  base_specs = [base_spec]
  while rest.startswith(','):
    base_spec2, rest2 = split_base_specifier(rest[1:].strip())
    if base_spec2:
      base_specs.append(base_spec2)
      rest = rest2
    else:
      return None, line
  return base_clause(base_specs), rest

  
class named_class_definition(namedtuple('named_class_definition', ['key', 'attr', 'headname', 'isfinal', 'base_clause', 'member_specs'], defaults=[REQUIRED, None, False, None, None])):
  def __str__(self):
    r = f'{self.key}'
    if self.attr:
      r += f' {self.attr}'
    r += f' {self.headname}'
    if self.isfinal:
      r += ' final'
    if self.base_clause:
      r += ' {self.base_clause}'
    if self.members:
      r += ' {{ {self.member_specs} }}'
    return r

class unnamed_class_definition(namedtuple('unnamed_class_definition', ['key', 'attr', 'base_clause', 'member_specs'], defaults=[REQUIRED, None, None, None])):
  def __str__(self):
    r = f'{self.key}'
    if self.attr:
      r += f' {self.attr}'
    if self.base_clause:
      r += ' {self.base_clause}'
    if self.members:
      r += ' {{ {self.member_specs} }}'
    return r

def startswithword(line, key):
  return line.startswith(key) and not startswith_identifier(line[len(key):])

def split_class_head_name(line):
  headname, rest = split_qualified_identifier(line)
  if headname:
    return headname, rest
  return split_unqualified_identifier(line)

class class_specifier(namedtuple('class_specifier', ['kind', 'key', 'attr', 'class_head_name', 'isfinal', 'base_clause', 'member_specification'], defaults=[REQUIRED, REQUIRED, None, None, None, REQUIRED])):
  def __str__(self):
    r = self.key
    if self.attr:
      r += f' {self.attr}'
    if self.kind == '(1)':
      r += f' {self.class_head_name}'
      if self.isfinal:
        r += ' final'
    elif self.kind == '(2)':
      pass
    else:
      assert 0  # unreachable
    if self.base_clause:
      r += f' {self.base_clause}'
    r += f' {{ {self.member_specification} }}'
    return r

  @classmethod
  def split(cls, line):
    for key in ['class', 'struct', 'union']:
      if startswithword(line, key):
        break
    else:
      return None, line
    rest = line[len(key):].lstrip()
    attr, rest = split_attribute_specifier(rest)
    headname, rest = split_class_head_name(rest)
    isfinal = False
    if headname:
      kind = '(1)'
      if startswithword(rest, 'final'):
        isfinal = True
        rest = rest[len('final'):].lstrip()
    else:
      kind = '(2)'
    base_clause, rest = split_base_clause(rest)
    if rest.startswith('{'):
      member_specs, rest = split_marks(rest[1:].lstrip(), '}', keep_mark=False)
      if member_specs is not None:
        return cls(kind, key, attr, headname, isfinal, base_clause, members_specs)

    return None, line

split_class_specifier = class_specifier.split
      
def __split_class_specifier(line):
  for key in ['class', 'struct', 'union']:
    if startswithword(line, key):
      break
  else:
    return None, line

  rest = line[len(key):].lstrip()
  attr, rest = split_attribute_specifier(rest)
  headname, rest = split_class_head_name(rest)
  isfinal = False
  if headname:
    if startswithword(rest, 'final'):
      isfinal = True
      rest = rest[len('final'):].lstrip()
    base_clause, rest = split_base_clause(rest)
    if rest.startswith('{'):
      member_specs, rest = split_marks(rest[1:].lstrip(), '}', keep_mark=False)
      if member_specs is not None:
        return named_class_definition(key, attr, headname, isfinal, base_clause, member_specs), rest
    elif not rest or rest.startswith(';'):
      return named_class_definition(key, attr, headname, isfinal, base_clause, None), rest[1:].lstrip()
  else:
    base_clause, rest = split_base_clause(rest)
    if rest.startswith('{'):
      member_specs, rest = split_marks(rest[1:].lstrip(), '}', keep_mark=False)
      if member_specs is not None:
        return unnamed_class_definition(key, attr, base_clause, member_specs), rest
    elif not rest or rest == ';':
      return unnamed_class_definition(key, attr, base_clause, None), rest
  return None, line

def split_enum_head_name(line):
  headname, rest = split_qualified_identifier(line)
  if headname:
    return headname, rest
  return split_unqualified_identifier(line)

class enum_base(namedtuple('enum_base', ['type_spec_seq'], defaults=[REQUIRED])):
  def __str__(self):
    seq = ' '.join(map(str, self.type_spec_seq))
    return f': {seq}'

def split_enum_base(line):
  if line.startswith(':'):
    rest = line[1:].strip()
    type_spec_seq, rest = split_type_specifier_sequence(rest)
    if type_spec_seq:
      return enum_base(type_spec_seq), rest
  return None, line

class enum_specifier(namedtuple('enum_specifier', ['key', 'attr', 'headname', 'base', 'enumerator_list'], defaults=[REQUIRED, None, None, None, None])):
  def __str__(self):
    r = str(self.key)
    if self.attr:
      r += f' {self.attr}'
    if self.headname:
      r += f' {self.headname}'
    if self.base:
      r += f' {self.base}'
    lst = ', '.join(map(str, self.enumerator_list))
    r += f' {{ {lst} }}'
    return r

  @classmethod
  def split(cls, line):
    for key in ['enum class', 'enum struct', 'enum']:
      if startswithword(line, key):
        break
    else:
      return None, line
    rest = line[len(key):].lstrip()
    attr, rest = split_attribute_specifier(rest)
    headname, rest = split_enum_head_name(rest)
    base, rest = split_enum_base(rest)
    if rest.startswith('{'):
      enumerator_lst, rest = split_marks(rest[1:], '}', keep_mark=False)
      if enumerator_lst is not None:
        lst = []
        for p in split_marks(rest, ',', keep_mark=False, recursive_list=True):
          e, rest = enumerator.split(rest)
          if e:
            lst.append(e)
          else:
            break
        if lst:
          return cls(key, attr, headname, base, lst), rest
    return None, line

split_enum_specifier = enum_specifier.split
  
def split_enum_specifier(line):
  for key in ['enum class', 'enum struct', 'enum']:
    if startswithword(line, key):
      break
  else:
    return None, line
  rest = line[len(key):].lstrip()
  attr, rest = split_attribute_specifier(rest)
  headname, rest = split_enum_head_name(rest)
  base, rest = split_enum_base(rest)
  if rest.startswith('{'):
    enumerator_lst, rest = split_marks(rest[1:], '}', keep_mark=False)
    if enumerator_lst is not None:
      return enum_specifier(key, attr, headname, base, enumerator_lst), rest
  elif not rest or rest.startswith(';'):
    return enum_specifier(key, attr, headname, base, None), rest[1:].lstrip()
  return None, line

class type_specifier_sequence(namedtuple('type_specifier_sequence', ['content'], defaults=[REQUIRED])):
  def __str__(self):
    return str(list(map(str, self.content)))

  @classmethod
  def split(cls, line):
    cv0, rest = split_cv_qualifier(line)
    for split in [
        class_specifier.split,
        enum_specifier.split,
        simple_type_specifier.split,
        elaborated_type_specifier.split,
        typename_specifier.split
    ]:
      spec, rest = split(rest)
      if spec:
        cv1, rest = split_cv_qualifier(rest)
        lst = []
        if cv0:
          lst.append(cv0)
        lst.append(spec)
        if cv1:
          lst.append(cv1)
        return cls(lst), rest
    return None, line

split_type_specifier_sequence = type_specifier_sequence.split
  
def __split_type_specifier_sequence(line):

  specs, rest = split_type_specifier(line, recursive_list=True)
  print(f'---------- {specs=} {rest=}')
  if specs is None:
    return None, line
  if (not rest or rest.startswith(';')) and len(specs) > 1 and not isinstance(specs[-1], str):
    specs, rest = specs[:-1], str(specs[-1]) + rest
  specs_ = tuple(s for s in specs if not (s == 'volatile' or s == 'const'))

  if len(specs_) == 1:
    return specs, rest

  if tuple(specs_) in [
      ('signed', 'char'),
      ('signed', 'long'),
      ('signed', 'long', 'long'),
      ('signed', 'long', 'long', 'int'),
      ('signed', 'int'),
      ('signed', 'short'),
      ('signed', 'short', 'int'),
      ('unsigned', 'char'),
      ('unsigned', 'long'),
      ('unsigned', 'long', 'long'),
      ('unsigned', 'long', 'long', 'int'),
      ('unsigned', 'int'),
      ('unsigned', 'short'),
      ('unsigned', 'short', 'int'),
      ('short', 'int'),
      ('long', 'int'),
      ('long', 'double'),
      ('long', 'long'),
      ('long', 'long', 'int'),
  ]:
    return specs, rest
  print(f'oooooooooooooo {specs=} {rest=}')
  return None, line


class elaborated_type_specifier(namedtuple('elaborated_type_specifier', ['key', 'tname'], defaults=[REQUIRED, REQUIRED])):
  def __str__(self):
    return f'{self.key} {self.tname}'
  @classmethod
  def split(cls, line):
    for k in ['class', 'struct', 'union', 'enum']:
      if startswithword(line, k):
        rest = line[len(k):].lstrip()
        break
    else:
      return None, line

    qid, rest = split_qualified_identifier(rest)
    if qid:
      return cls(k, qualified_id_declarator(scope=qid[0], id=qid[1])), rest
    uqid, rest = split_unqualified_identifier(rest)
    if uqid:
      return cls(k, unqualified_id_declarator(uqid)), rest
    return None, line

class typename_specifier(namedtuple('typename_specifier', ['tname'], defaults=[REQUIRED])):
  def __str__(self):
    return f'typename {self.tname}'
  @classmethod
  def split(cls, line):
    if startswithword(line, 'typename'):
      rest = line[len('typename'):].lstrip()
      qid, rest = split_qualified_identifier(rest)
      if qid:
        return cls(qualified_id_declarator(scope=qid[0], id=qid[1])), rest
      uqid, rest = split_unqualified_identifier(rest)
      if uqid:
        return cls(unqualified_id_declarator(uqid)), rest
    return None, line

class placeholder_type_specifier(namedtuple('placeholder_type_specifier', ['type_constraint', 'auto'], defaults=[None, REQUIRED])):
  def __str__(self):
    if self.type_constraint:
      return f'{self.type_constraint} {self.auto}'
    return str(self.auto)
  @classmethod
  def split(cls, line):
    type_constraint = None
    qid, rest = split_qualified_identifier(line)
    if qid:
      type_constraint = qualified_id_declarator(scope=qid[0], id=qid[1])
    else:
      uqid, rest = split_unqualified_identifier(line)
      if uqid:
        type_constraint = unqualified_id_declarator(uqid)
      else:
        rest = line
    if rest.startswith('decltype(auto)'):
      auto = "decltype(auto)"
    elif startswithword(rest, 'auto'):
      auto = 'auto'
    else:
      return None, line
    return cls(type_constraint, auto), rest[len(auto):].lstrip()

class declared_type_name(namedtuple('declared_type_name', ['tname'], defaults=[REQUIRED])):
  def __str__(self):
    return str(self.tname)
  @classmethod
  def split(cls, line):
    qid, rest = split_qualified_identifier(line)
    if qid:
      return cls(qualified_id_declarator(scope=qid[0], id=qid[1])), rest

    uqid, rest = split_unqualified_identifier(line)
    if uqid:
      return cls(unqualified_id_declarator(uqid)), rest
    return None, line

class typedef_declaration(namedtuple('typedef_declaration', ['type_specifer', 'tname'], defaults=[REQUIRED, REQUIRED])):
  def __str__(self):
    return f'typedef {self.type_specifier} {self.tname}'
  @classmethod
  def split(cls, line):
    if startswithword(line, 'typedef'):
      spec, rest = split_type_specifier(line[len('typedef'):].lstrip())
      if spec:
        tname, rest = split_identifier(rest)
        if tname:
          return cls(spec, tname), rest
    return None, line

class declaration_specifier(namedtuple('declaration_specifier', ['spec'], defaults=[REQUIRED])):
  def __str__(self):
    return str(self.spec)
  @classmethod
  def split(cls, line, abstract=False):
    print(f'{cls.__name__}: {line=}')
    decl, rest = typedef_declaration.split(line)
    if decl:
      return decl, rest

    for k in ['inline', 'virtual', 'explicit', 'friend', 'constexpr', 'consteval', 'constinit'] + storage_class_specifiers:
      if startswithword(line, k):
        return k, line[len(k):].lstrip()
    print(f'BBBBBB {line=}')
    spec, rest = split_type_specifier_sequence(line)
    if spec is not None:
      return spec, rest
    return None, line

split_declaration_specifier = recursive(declaration_specifier.split)

storage_class_specifiers = ['register', 'static', 'thread_local', 'extern', 'mutable']

class declaration_specifier_sequence(namedtuple('declaration_specifier_sequence', ['content'], defaults=[REQUIRED])):
  def __str__(self):
    return ' '.join(map(str, self.content))

  @classmethod
  def split(cls, line, abstract=False):
    lst = []
    rest = line
    while True:
      spec, rest = declaration_specifier.split(rest, abstract=abstract)
      if spec:
        lst.append(spec)
      else:
        break
    if lst:
      return cls(lst), rest
    return None, line

split_declaration_specifier_sequence = declaration_specifier_sequence.split

def __split_declaration_specifier_sequence(line, abstract=False):
  specs, rest = split_declaration_specifier(line, recursive_list=True)
  print(f'AAAAAAAAAAA {specs=} {rest=}')
  if specs is not None:

    new_specs = []
    for spec in specs:
      if isinstance(spec, list):
        new_specs.extend(spec)
      else:
        new_specs.append(spec)
    specs = new_specs

    if len(specs) > 1 and isinstance(specs[0], typedef_declaration):
      # typedef spec becomes decl when typedef name is present
      return specs[0], ' '.join(map(str, specs[1:])) + (' ' if startswith_identifier0(rest) else '') + rest 

    if [s for s in specs if isinstance(s, typedef_declaration)]:
      return None, line

    new_specs = []
    sc_specs0 = []
    sc_specs1 = []
    rest0 = ''
    for s in specs:
      if not new_specs:
        if s in simple_type_specifiers or not isinstance(s, str):
          new_specs.append(s)
        else:
          sc_specs0.append(s)
      elif not rest0 and new_specs[0] in simple_type_specifiers and s in simple_type_specifiers:
        new_specs.append(s)
      else:
        if not rest0 and s in storage_class_specifiers:
          sc_specs1.append(s)
        else:
          rest0 += ' ' + str(s)
      specs = sc_specs0 + new_specs + sc_specs1
      rest = rest0.lstrip() + (' ' if startswith_identifier0(rest) else '') + rest

    if (not rest or rest.startswith(',')) and not abstract:
      specs, rest = specs[:-1], str(specs[-1]) + rest
    
    sc_specs = tuple([s for s in specs if s in storage_class_specifiers])
    if len(sc_specs) > 1 and sc_sprecs not in [
        ('thread_local', 'extern'),
        ('thread_local', 'static'),
        ('extern', 'thread_local'),
        ('static', 'thread_local'),
    ]:
      return None, line


    return specs, rest
  return None, line

class typedef_name(namedtuple('typedef_name', ['content'], defaults=[REQUIRED])):
  def __str__(self):
    return str(self.content)
  @classmethod
  def split(cls, line):
    for split in [# simple_template_identifier.split,
                  split_simple_template_id,
                  split_identifier]:    
      spec, rest = split(line)
      if spec:
        return spec, rest
    return None, line
  

class pack_indexing_specifier(namedtuple('pack_indexing_specifier', ['typedef_name', 'expr'], defaults=[REQUIRED, REQUIRED])):
  def __str__(self):
    return f'{self.typedef_name} ...[ {self.expr} ]'

  @classmethod
  def split(cls, line):
    tname, rest = typedef_name.split(line)
    if tname:
      if rest.startswith('...['):
        expr, rest = split_marked(rest[len('...['):], ']')
        if expr:
          return cls(tname, expr), rest
    return None, line

simple_type_specifiers = ['char8_t', 'char16_t', 'char32_t', 'char', 'wchar_t', 'bool', 'short', 'int', 'long', 'signed', 'unsigned', 'float', 'double', 'void']

class simple_type_specifier(namedtuple('simple_type_specifier', ['content'], defaults=[REQUIRED])):

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
    ('long',),
    ('long', 'int'),
    ('long', 'double'),
    ('long', 'long'),
    ('long', 'long', 'int'),
    ('int',),
    ('float',),
    ('double',),
    ('void',),
  ]

  def __str__(self):
    if isinstance(self.content, tuple):
      return ' '.join(map(str, self.content))
    return str(self.content)

  @classmethod
  def split(cls, line):
    tname, rest = split_keyword(line)
    if tname:
      t = (tname,)
      while True:
        tname2, rest2 = split_keyword(rest)
        t2 = t + (tname2,)
        if tname2 and t2 in cls.keyword_types:
          t, rest = t2, rest2
        else:
          break
      return cls(t), rest

    for split in [
        placeholder_type_specifier.split,
        decltype_specifier.split,
        pack_indexing_specifier.split,
        # qualified/unqualified class/enum/typedef/template name, w/
        # and wo/ template arguments:
        declared_type_name.split
    ]:
      spec, rest = split(line)
      if spec:
        return cls(spec), rest

    return None, line
      
    
@recursive
def split_type_specifier(line):
  class_spec, rest = split_class_specifier(line)
  if class_spec:
    return class_spec, rest
  enum_spec, rest = split_enum_specifier(line)
  if enum_spec:
    return enum_spec, rest
  for t in simple_type_specifiers:
    if startswithword(line, t):
      return t, line[len(t):].lstrip()

  spec, rest = placeholder_type_specifier.split(line)
  if spec:
    return spec, rest

  spec, rest = split_decltype_specifier(line)
  if spec:
    return spec, rest
  
  spec, rest = elaborated_type_specifier.split(line)
  if spec:
    return spec, rest

  spec, rest = typename_specifier.split(line)
  if spec:
    return spec, rest

  cv, rest = split_cv_qualifier(line)
  if cv:
    return cv, rest

  spec, rest = declared_type_name.split(line)
  if spec:
    return spec, rest
  return None, line
  qid, rest = split_qualified_identifier(line)
  if qid:
    attr, rest = split_attribute_specifier(rest)
    return qualified_id_declarator(scope=qid[0], id=qid[1], attr=attr), rest

  uqid, rest = split_unqualified_identifier(line)
  if uqid:
    attr, rest = split_attribute_specifier(rest)
    return unqualified_id_declarator(uqid, attr), rest
  
  return None, line


def iter_split_marks(line, marks, keep_mark=True, pmap=None):
  if pmap is None:
    pmap = {'<': '>', '(': ')', '{': '}', '[': ']'}
  stack = []
  i0 = 0
  for i in range(len(line)):
    if line[i] in pmap:
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack and line[i] in marks:
      if keep_mark:
        yield line[i0:i+1].strip(), line[i+1:].lstrip()
        i0 = i+1
      else:
        yield line[i0:i].strip(), line[i:].lstrip()
        i0 = i+1
  if i0 < len(line):
    yield line[i0:].rstrip(), ''

@recursive
def split_marks(line, marks, **options):
  stack = []
  pmap = {'<': '>', '(': ')', '{': '}', '[': ']'}
  pmap = options.get('pmap', pmap)
  keep_mark = options.get('keep_mark', True)
  for i in range(len(line)):
    if line[i] in pmap:
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack and line[i] in marks:
      if keep_mark:
        return line[:i+1].rstrip(), line[i+1:].lstrip()
      else:
        return line[:i].rstrip(), line[i+1:].lstrip()
  if '\n' in marks:
    return line, ''
  return None, line

def isnamestart(s):
  return s and (s[0].isalpha() or s[0] == '_')

def isnamemiddle(s):
  return s and (s[0].isalnum() or s[0] == '_')

def startswith_identifier(s):
  # TODO: XID_Continue
  return s and (s[0].isalnum() or s[0] == '_')

def startswith_identifier0(s):
  # TODO: XID_Start
  return s and (s[0].isalpha() or s[0] == '_')

def split_operator(line):
  if not line.startswith('operator'):
    return None, line
  rest = line[len('operator'):].lstrip()
  operators = [">>=", "<<=", "<=>", "->*", "==", "!=", "<=", ">=",
               "&&", "||", "++", "--", "->", "+=", "-=", "*=", "/=",
               "%=", "^=", "&=", "|=", "<<", ">>", ",", "+", "-", "*",
               "/", "%", "^", "&", "|", "~", "!", "=", "<", ">", "(",
               ")", "[", "]"]
  for op in operators:
    if rest.startswith(op):
      return f'operator{op}', rest[len(op):].lstrip()

  for k in ['new', 'delete']:
    if rest.startswith(k) and not startswith_identifier(rest[len(k):]):
      r = rest[len(k):].lstrip()
      if r.startswith('[]'):
        return f'operator {k} []', r[2:].lstrip()
      return f'operator {k}', r

  if rest.startswith('co_await') and not startswith_identifier(rest[len('co_await'):]):
    return 'operator co_await', rest[len('ca_await'):].lstrip()

  # TODO:
  if rest.startswith('""'):
    raise NotImplementedError('split `operator "" <identifier>` | `operator ""<ud-suffix>`')
  raise NotImplementedError('split `operator <conversion-type-id>`')

def split_template_arguments(line):
  if not line.startswith('<'):
    return None, line
  tmpl, rest = split_marks(line[1:].lstrip(), '>', keep_mark=False)
  if tmpl:
    return tmpl, rest
  return None, line

def split_simple_template_id(line):
  name, rest = split_identifier(line)
  if name:
    targs, rest = split_template_arguments(rest)
    if targs:
      return simple_template_id(name, targs), rest
  return None, line

def split_name(line):
  name, rest = split_simple_template_id(line)
  if name:
    return name, rest
  return split_identifier(line)

def split_unqualified_identifier(line):
  name, rest = split_operator(line)
  if not name:
    name, rest = split_name(line)
  if name and not rest.startswith('::'):
    return name, rest
  return None, line

def split_qualified_identifier(line):
  # TODO:
  #   <decltype specifier>
  #   <pack indexing specifier>
  scope_names = []
  if line.startswith('::'):
    identifier = ''
    rest = line
  else:
    identifier, rest = split_name(line)
    if not identifier or not rest.startswith('::'):
      return None, line
    assert identifier != 'decltype'
  scope_names.append(identifier)

  while rest.startswith('::'):
    identifier2, rest2 = split_name(rest[2:].lstrip())
    assert identifier2 != 'decltype'
    if identifier2 and rest2.startswith('::'):
      scope_names.append(identifier2)
      rest = rest2
    else:
      identifier2, rest2 = split_unqualified_identifier(rest[2:].lstrip())
      if identifier2:
        assert identifier2 != 'decltype'
        assert not rest2.startswith('::')
        assert not rest2.startswith('...')
        return (scope_list(scope_names), identifier2), rest2
      break

  return None, line

def split_nested_name_specifier(line):
  scope_names = []
  if line.startswith('::'):
    name, rest = '', line
  else:
    name, rest = split_name(line)
    if not name or not rest.startswith('::'):
      return None, line
  scope_names.append(name)
  while rest.startswith('::'):
    rest_look_ahead = rest[2:].lstrip()
    if not startswith_identifier0(rest_look_ahead):
      return scope_list(scope_names), rest_look_ahead
    name2, rest2 = split_name(rest_look_ahead)
    if not name2:
      name2, rest2 = split_keyword(rest_look_ahead)
    if name2:
      scope_names.append(name2)
      rest = rest2
    else:
      break
  if scope_names:
    return scope_list(scope_names[:-1]), str(scope_names[-1]) + (' ' if startswith_identifier0(rest) else '') + rest
  return None, line
  
@recursive
def split_attribute_specifier(line):
  if line.startswith('[['):
    j = line.index(']]')
    return line[:j + 2], line[j + 2:].lstrip()
  return None, line

def split_ref_qualifier(line):
  for k in ['&&', '&']:
    if line.startswith(k):
      return k, line[len(k):].lstrip()
  return None, line


def split_except_qualifier(line):
  # TODO:
  # throw(type-id-list ﻿(optional))
  # noexcept
  # noexcept(expression)
  if line.startswith('throw') or line.startswith('noexcept'):
    raise NotImplementedError(f'split `{line}`')
  return None, line

def _function_declarator_with_trailing(decl, rest, line):
  if rest.startswith('->'):
    raise NotImplementedError(f'{rest}')
  return decl, rest

def _array_or_function_declarator(decl, rest, line):
  if rest.startswith('('):
    params_lst, rest = split_marks(rest[1:].lstrip(), ')', keep_mark=False)
    if params_lst is not None:
      params_lst, rest2 = parameter_list.split(params_lst)
      if params_lst is None:
        return None, line
      assert not rest2, rest2
      cv, rest = split_cv_qualifier(rest)
      ref, rest = split_ref_qualifier(rest)
      exc, rest = split_except_qualifier(rest)
      attr, rest = split_attribute_specifier(rest)
      return _function_declarator_with_trailing(function_declarator(decl, params_lst, cv, ref, exc, attr), rest, line)
  elif rest.startswith('['):
    expr, rest = split_marks(rest[1:].lstrip(), ']', keep_mark=True)
    if expr:
      expr = '[' + expr
      attr, rest = split_attribute_specifier(rest)
      return array_declarator(decl, expr, attr), rest
  else:
    return decl, rest
  return None, line

def split_declarator(line, abstract=False):
  if line.startswith('('):
    rest = line[1:].lstrip()
    decl, rest = split_declarator(rest, abstract=abstract)
    if decl and rest.startswith(')'):
      return _array_or_function_declarator(decl, rest[1:].lstrip(), line)
    return None, line

  if line.startswith('...'):
    assert not abstract  # not impl
    ident, rest = split_identifier(line[3:])
    if ident:
      attr, rest = split_attribute_specifier(rest)
      return  _array_or_function_declarator(parameter_pack_declarator(ident, attr), rest, line)
    return None, line
  
  if line.startswith('*'):
    attr, rest = split_attribute_specifier(line[1:].lstrip())
    cv, rest = split_cv_qualifier(rest)
    decl, rest = split_declarator(rest, abstract=abstract)
    if decl:
      return  _array_or_function_declarator(pointer_to_declarator(attr, cv, decl), rest, line)
    return None, line

  if line.startswith('&&'):
    attr, rest = split_attribute_specifier(line[2:].lstrip())
    decl, rest = split_declarator(rest, abstract=abstract)
    if decl:
      return  _array_or_function_declarator(rvalue_reference_declarator(attr, decl), rest, line)
    return None, line

  if line.startswith('&'):
    attr, rest = split_attribute_specifier(line[1:].lstrip())
    decl, rest = split_declarator(rest, abstract=abstract)
    if decl:
      return  _array_or_function_declarator(lvalue_reference_declarator(attr, decl), rest, line)
    return None, line
  if abstract:
    name, rest = None, line
  else:
    name, rest = split_nested_name_specifier(line)
  if (name or abstract) and rest.startswith('*'):
    attr, rest = split_attribute_specifier(rest[1:].lstrip())
    cv, rest = split_cv_qualifier(rest)
    decl, rest = split_declarator(rest)
    if decl:
      return pointer_to_member_declarator(name, attr, cv, decl), rest

  print(f'{line=}')
  if abstract:
    qid, rest = None, line
  else:
    qid, rest = split_qualified_identifier(line)
  if qid:
    attr, rest = split_attribute_specifier(rest)
    return  _array_or_function_declarator(qualified_id_declarator(scope=qid[0], id=qid[1], attr=attr), rest, line)
  
  if abstract:
    uqid, rest = None, line
  else:
    uqid, rest = split_unqualified_identifier(line)
    print(f'{uqid=} {rest=}')
  if uqid:
    attr, rest = split_attribute_specifier(rest)
    decl = unqualified_id_declarator(uqid, attr)
    decl2, rest2 = _array_or_function_declarator(decl, rest, line)
    print(f'{decl2=} {rest2=}')
    if decl2:
      return decl2, rest2
    return decl, rest

  if abstract:
    attr, rest = split_attribute_specifier(rest)
    assert not attr, attr  # not impl
    return  _array_or_function_declarator(None, rest, line)
  
  return None, line

def __split_decl_specifier_seq(line):
  storage_class_specifiers = ['register', 'static', 'thread_local', 'extern', 'mutable']
  type_specifiers_seq = ['class', 'struct', 'union',
                         'enum',
                         # simple type specifiers
                         'char', 'char8_t', 'char16_t', 'char32_t', 'wchar_t', 'bool', 'short', 'int', 'long', 'signed', 'unsigned', 'float', 'double', 'void',
                         'auto',
                         'decltype',
                         'pack indexing specifier',
                         'qualified/unqualified class/enum/typedef name, template name with or without args',
                         'Elaborated type specifier',
                         'typename',
                         'const', 'volatile',
                         
                         ]
  specifiers = ['typedef', 'inline', 'friend', 'constexpr', 'consteval', 'constinit']
  raise

def __split_class_specifier(line):
  for key in {'class', 'struct', 'union'}:
    if not (line.startswith(key) and not startswith_identifier(line[len(key):])):
      continue
    rest = line[len(key):].lstrip()
    attrs, rest = split_attribute_specifier(rest, recursive_list=True)
    base_clause, rest = split_base_clause(rest)
    final = False
    if base_clause:  # unnamed class definition
      name = None
    else: # named class definition
      name, rest = split_qualified_identifier(rest)
      if not name:
        return None, line
      if rest.startswith('final') and not startswith_identifier(line[len('final'):]):
        final = True
        rest = rest[len('final'):].lstrip()
      base_clause, rest = split_base_clause(rest)
    if rest.startswith('{'):
      member_specs, rest = split_marks(rest[1:].lstrip(), '}', keep_mark=True)
      if member_specs:
        member_specs = '{' + member_specs
        return (key, attrs, name, final, base_clause, member_specs), rest
    else:
      return (key, attrs, name, final, base_clause, None)
  return None, line


def split_cv_qualifier(line):
  for k in ['const', 'volatile']:
    if startswithword(line, k):
      return k, line[len(k):].lstrip()
  return None, line

class init_declarator(namedtuple('init_declarator', ['declarator', 'initializer'], defaults=[REQUIRED, REQUIRED])):
  def __str__(self):
    return f'{self.declarator}{self.initializer}'
  @classmethod
  def split(cls, line):
    decl, rest = split_declarator(line)
    if decl:
      init, rest = initializer.split(rest)
      if init:
        return cls(decl, init), rest
      return decl, rest
    return None, line

class initializer(namedtuple('initializer', ['kind', 'content'], defaults=[REQUIRED, None])):
  def __str__(self):
    if self.kind == '(1)':
      assert self.content
      return f'= {self.content}'
    elif self.kind == '(2)':
      return f'= {{ {self.content or ""} }}'
    elif self.kind == '(3)':
      return f'( {self.content} )'
    elif self.kind == '(4)':
      return f'{{ {self.content or ""} }}'
    assert 0, self.kind  # unreachable
  @classmethod
  def split(cls, line):
    if line.startswith('='):
      rest = line[1:].lstrip()
      if rest.startswith('{'):
        content, rest = split_marks(rest[1:].lstrip(), '}', keep_mark=False)
        if content:
          if rest.startswith(','):
            rest = rest[1:].lstrip()
          return cls('(2)', content), rest
      else:
        content, rest = split_marks(rest, ',;\n', keep_mark=True)
        if content is not None:
          if content.endswith(';'):
            rest = ';' + rest
          elif content.endswith(','):
            content = content[:-1]
        if content:
          if rest.startswith(','):
            rest = rest[1:].lstrip()
          return cls('(1)', content), rest
    elif line.startswith('('):
      content, rest = split_marks(line[1:].lstrip(), ')', keep_mark=False)
      if content:
        if rest.startswith(','):
          rest = rest[1:].lstrip()
        return cls('(3)', content), rest
    elif line.startswith('{'):
      content, rest = split_marks(line[1:].lstrip(), '}', keep_mark=False)
      if rest.startswith(','):
        rest = rest[1:].lstrip()
      if content:
        return cls('(4)', content), rest
      return cls('(4)'), rest
    return None, line

class parameter_declaration(namedtuple('parameter_declaration', ['kind', 'attr', 'decl_specifier_seq', 'declarator', 'initializer'], defaults=[REQUIRED, None, REQUIRED, None, None])):
  def __str__(self):
    r = str(self.attr) if self.attr else ''
    if self.kind == '(1)':
      r += f" {self.decl_specifier_seq} {self.declarator}"
    elif self.kind == '(2)':
      r += f" this {self.decl_specifier_seq} {self.declarator}"
    elif self.kind == '(3)':
      r += f" {self.decl_specifier_seq} {self.declarator} = {self.initializer}"
    elif self.kind == '(4)':
      r += f" {self.decl_specifier_seq} {self.declarator}" if self.declarator else f" {self.decl_specifier_seq}"
    elif self.kind == '(5)':
      r += f" this {self.decl_specifier_seq} {self.declarator}" if self.declarator else f" {self.decl_specifier_seq}"
    elif self.kind == '(6)':
      r += f" this {self.decl_specifier_seq} {self.declarator}" if self.declarator else f" {self.decl_specifier_seq}"
      r += f" = {self.initializer}"
    else:
      assert 0, self.kind  # unreachable
    return r.lstrip()

  @classmethod
  def split(cls, line):
    if startswithword(line, 'void'):
      rest = line[len('void'):].lstrip()
      if rest.startswith(',') or not rest:
        return 'void', rest[1:].lstrip()
      return None, line
    attr, rest = split_attribute_specifier(line)
    is_explicit_object_parameter = False
    if startswithword(rest, 'this'):
      is_explicit_object_parameter = True
      rest = rest[len('this'):].lstrip()
    decl_specifier_seq, rest2 = split_declaration_specifier_sequence(rest, abstract=False)
    if decl_specifier_seq is None:
      return None, line
    is_abstract_decl = False
    if rest2.startswith('='):
      decl = None
      is_abstract_decl = True
      rest = rest2
    else:
      decl, rest2 = split_declarator(rest2)
      if not decl:
        is_abstract_decl = True
        decl_specifier_seq, rest = split_declaration_specifier_sequence(rest, abstract=True)
        if not decl_specifier_seq:
          return None, line
        decl, rest = split_declarator(rest, abstract=True)
      else:
        rest = rest2

    if rest.startswith('='):
      initializer, rest = split_initializer(rest[1:].lstrip())
      if initializer:
        kind = '(6)' if is_abstract_decl else '(3)'
        if rest.startswith(',') or not rest or 1:
          if rest.startswith(','):
            rest = rest[1:].lstrip()
          return cls(kind, attr, decl_specifier_seq, decl, initializer), rest
      else:
        return None, line
    else:
      if is_explicit_object_parameter:
        kind = '(5)' if is_abstract_decl else '(2)'
      else:
        kind = '(4)' if is_abstract_decl else '(1)'
      if rest.startswith(',') or not rest:
        return cls(kind, attr, decl_specifier_seq, decl, None), rest[1:].lstrip()
    return None, line

def split_initializer(line):
  init, rest = split_marks(line, ',\n', keep_mark=False)
  if init:
    return init, rest
  return None, line

class parameter_list(namedtuple('parameter_list', ['content'], defaults=[REQUIRED])):
  def __str__(self):
    return str(list(map(str, self.content)))

  @classmethod
  def split(cls, line):
    if line == '':
      return [], ''
    assert isinstance(line, str)
    lst = []
    rest = line
    for p, rest in iter_split_marks(rest, ',', keep_mark=False):
      if not p:
        continue
      decl, r = parameter_declaration.split(p)
      if decl is not None and not r:
        lst.append(decl)
      else:
        return None, line
    assert not rest
    return lst, ''

class init_declarator_list(namedtuple('init_declarator_list', ['content'], defaults=[REQUIRED])):
  def __str__(self):
    return str(list(map(str, self.content)))

  @classmethod
  def split(cls, line):
    stmt, rest = split_marks(line, ';', keep_mark=False)
    if stmt is not None:
      lst = []
      while stmt:
        assert isinstance(stmt, str), (stmt, str(stmt))
        decl, stmt = init_declarator.split(stmt)
        if stmt.startswith(','):
          stmt = stmt[1:].lstrip()
        if decl:
          lst.append(decl)
        else:
          return None, line
      return lst, rest
    return None, line
  
  
class simple_declaration(namedtuple('simple_declaration', ['attr', 'decl_specifier_seq', 'init_declarator_list'], defaults=[None, REQUIRED, None])):

  def __str__(self):
    if self.attr:
      return f'{self.attr} {self.decl_specifier_seq} {self.init_declarator_list};'
    if self.init_declarator_list:
      return f'{self.decl_specifier_seq} {self.init_declarator_list};'
    return f'{self.decl_specifier_seq};'

  @classmethod
  def split(cls, line):
    # todo:  structured binding declaration
    attr, rest = split_attribute_specifier(line)
    decl_specifier_seq, rest = split_declaration_specifier_sequence(rest)
    if decl_specifier_seq:
      if attr:
        init_decl_list, rest = init_declarator_list.split(rest)
        if init_decl_list:
          if rest.startswith(';'):
            rest = rest[1:].lstrip()
          return cls(attr, decl_specifier_seq, init_decl_list), rest
      else:
        if rest.startswith(';'):
          rest = rest[1:].lstrip()
          return cls(attr, decl_specifier_seq, None), rest
        else:
          init_decl_list, rest = init_declarator_list.split(rest)
          if rest.startswith(';'):
            rest = rest[1:].lstrip()
          return cls(attr, decl_specifier_seq, init_decl_list), rest
    return None, line

###############################################

def ___split_identifier(line):
  if not isnamestart(line):
    return None, line
  i = 1
  while i < len(line) and isnamemiddle(line[i]):
    i += 1
  return line[:i], line[i:].lstrip()

@recursive
def split_keywords(line, *keywords):
  for q in keywords:
    if line == q or (line.startswith(q) and not isnamemiddle(line[len(q)])):
      return q, line[len(q):].lstrip()
  return None, line


def split_access_specifier(line):
  return split_keywords(line, 'public', 'private', 'protected')

def __split_type_specifier(line):
  return split_keywords(line, 'const', 'static')

def split_function_specifier(line):
  return split_keywords(line, 'virtual', 'inline', 'constexpr')

def split_method_specifier(line):
  return split_keywords(line, 'virtual', 'override')

def __split_cv_qualifier(line):
  return split_keywords(line, 'const', 'volatile', recursive_str=True)



def __split_virtual_specifier(line):
  if line.startswith('='):
    line = line[1:].lstrip()
    if line.startswith('0'):
      return True, line[1:].strip()
  return False, line

@recursive
def split_scope(line):
  name, rest = split_identifier(line)
  if rest.startswith('<'):
    scope, rest = split_marks(rest, ':', pmap={'<': '>'})
    if scope and scope.endswith(':'):
      scope = scope[:-1]
      rest = ':' + rest
      if rest.startswith('::'):
        return name + scope, rest[2:]
  elif rest.startswith('::'):
    return name, rest[2:]
  return None, line
    
def split_type(line):
  typ, line = split_marks(line, ' &*\n')
  while True:
    for k in {'&', '*', '...'}:
      if line.startswith(k):
        typ += line[:len(k)]
        line = line[len(k):].lstrip()
        break
    else:
      break
  return typ, line
