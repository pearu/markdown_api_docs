# Copyright 2024 The OpenXLA Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Extract doc-strings from C++ sources and output these to a Markdown file.

It is assumed that C++ sources follow the [Google C++ Style
Guide](https://google.github.io/styleguide/cppguide.html). In
particular, the documentation strings of classes, class members,
functions, variables must preceed the corresponding declarations and
are in the form of Google C++ comments (lines starting with `//` or
lines included in `/* ... */` blocks).

With the above assumption, we don't need a full C++ parser in Python
to extract the C++ constructs and their doc-strings in comments.

Usage:

  markdown_api_docs <paths to C++ header files>

where a path to a header file can be a directory containing 

"""
import os
import sys


def header_files(path):
  """Yield header files contained in path.
  """
  if os.path.isfile(path) and path.endswith('.h'):
    yield path
    return
  for dirpath, dnames, fnames in os.walk(path):
    for f in fnames:
      if f.endswith(".h"):
        yield os.path.join(dirpath, f)


def eliminate_cpp_newlines(source_lines):
  """Pass that eliminates `\\` in CPP macro definitions.
  """
  new_source_lines = dict()
  cppline = None
  cpplineno = None
  for lineno, line in source_lines.items():
    if cppline is None:
      if line.lstrip().startswith('#') and line.endswith('\\'):
        cppline = line[:-1].rstrip()
        cpplineno = lineno
      else:
        new_source_lines[lineno] = line
    elif line.endswith('\\'):
      cppline = cppline + ' ' + line[:-1].rstrip()
    else:
      new_source_lines[cpplineno] = cppline
      cppline = None
      cpplineno = None
  return new_source_lines


def filter_comments(source_lines):
  """Pass that separates source code and comments.
  """

  def block2str(block, comment_type):
    min_tab = len(block[0])
    for i, line in enumerate(block):
      ln = line.lstrip()
      if comment_type == '/*':
        while ln.startswith('*'):
          ln = ln[1:]
      else:
        assert comment_type == '//', comment_type
        assert ln.startswith('//'), ln
        ln = ln[2:]  # lstrips '//'
      ln = ln.lstrip()
      if ln:
        min_tab = min(min_tab, len(line) - len(ln))
    return '\n'.join([line[min_tab:] for line in block])

  new_source_lines = dict()
  comments = dict()

  def add_comment(comment_lineno, lineno, comment_block, comment_type):
    if comment_lineno in comments:
      prev_comment = comments.pop(comment_lineno) + '\n'
    else:
      prev_comment = ''
    assert lineno not in comments, lineno
    comments[lineno] = prev_comment + block2str(comment_block, comment_type)
    comment_block.clear()

  comment_type = None
  comment_lineno = None
  comment_block = []

  lineno_index = -1
  lineno_list = list(source_lines)
  cache = {}
  while True:
    lineno_index += 1
    if lineno_index >= len(lineno_list):
      break
    lineno = lineno_list[lineno_index]
    line = cache.pop(lineno, source_lines[lineno])
    lline = line.lstrip()

    if comment_type == '//':
      if lline.startswith('//'):
        comment_block.append(line)
      else:
        add_comment(comment_lineno, lineno, comment_block, comment_type)
        comment_type = None        
        lineno_index -= 1
    elif comment_type == '/*':
      if '*/' in line:
        j = line.index('*/')
        comment_block.append(line[:j])
        add_comment(comment_lineno, lineno, comment_block, comment_type)
        comment_type = None
        if line[j + 2:].strip():
          cache[lineno] = line[j + 2:]
          lineno_index -= 1
      else:
        comment_block.append(line)
    else:
      assert comment_type is None, comment_type
      if lline.startswith('//'):
        comment_type = '//'
        comment_lineno = lineno
        comment_block.append(line)
      elif lline.startswith('/*'):
        if '*/' not in lline:
          comment_type = '/*'
          comment_lineno = lineno
          comment_block.append(line.replace('/*', ' ', 1))
        else:
          i = line.index('/*')
          j = line.index('*/')
          assert i < j, (lineno, line)
          add_comment(lineno, lineno, [line[i+2:j]], '/*')
          cache[lineno] = line[:i] + line[j+2:]
          lineno_index -= 1
      elif '//' in line:
        j = line.index('//')
        add_comment(lineno, lineno, [line[j:]], '//')
        if '/*' in line[:j]:
          assert '*/' in line[:j], (lineno, line)
        cache[lineno] = line[:j]
        lineno_index -= 1
      elif '/*' in line:
        i = line.index('/*')
        if '*/' in line:
          j = line.index('*/')
          assert i < j, (lineno, line)
          add_comment(lineno, lineno, [line[i+2:j]], '/*')
          cache[lineno] = line[:i] + line[j+2:]
          lineno_index -= 1
        else:
          if line[:i].strip():
            assert '//' not in line[:i], (lineno, line)
            assert '/*' not in line[:i], (lineno, line)
            new_source_lines[lineno] = line[:i].rstrip()
          cache[lineno] = line[i:]  # start of the multiline comment
          lineno_index -= 1
      elif lline:
        assert '//' not in line, (lineno, line)
        assert '/*' not in line, (lineno, line)
        new_source_lines[lineno] = line.rstrip()
      # else discarding empty lines
  return new_source_lines, comments


def eliminate_newlines(source_lines):
  """Pass that joins source lines that belong to the same C++ constuct.
  """
  new_source_lines = dict()

  def isidentifier(s):
    return s.isalnum() or s == ''

  prev_line = ''
  for lineno, line in source_lines.items():
    lline = line.lstrip()

    if lline.startswith('#') or prev_line.startswith('#'):
      # CPP macro definitions are always single lines due to using
      # eliminate_cpp_newlines
      new_source_lines[lineno] = line
      prev_lineno = lineno
    elif ('R"pb(' in prev_line and ')pb"' not in prev_line):
      new_source_lines[prev_lineno] += '\n' + line
    elif prev_line.startswith('enum ') and not prev_line.endswith(';'):
      new_source_lines[prev_lineno] += ' ' + lline
    elif prev_line and (
        [c for c in {'>', '(', ',', '=', '&', '|', '+', '-', '"', '?', '<', '^', '*', '/', '%', '.', ']'} if prev_line.endswith(c)]
        or [c for c in {'>', ':', ',', '=', '&', '|', '+', '-', '?', '<', '^', '*', '/', ')', '%', '"'} if lline.startswith(c)]
        or ((prev_line[-1].isalnum() or prev_line[-1] == '_') and (
          lline[0].isidentifier()
          or lline.startswith('}')
          or lline.startswith('{')
          or lline.startswith('[')
        ))
        or (prev_line.endswith(')') and (
          lline.startswith('const')
          or lline.startswith('{')
          or lline.startswith('}')
          or lline[0].isidentifier()
          or lline.startswith(';')
          or lline.startswith('(')
        ))
        or ((prev_line[-1].isidentifier()) and lline.startswith('('))
    ):
      new_source_lines[prev_lineno] += ' ' + lline
    elif prev_line and [c for c in {'.'} if lline.startswith(c)]:
      new_source_lines[prev_lineno] += lline
    else:

      new_source_lines[lineno] = line
      prev_lineno = lineno    

    prev_line = new_source_lines[prev_lineno].strip()

  # sanity checks:
  lineno_list = list(new_source_lines)

  skip = False
  for lineno_index in range(len(lineno_list)):
    lineno = lineno_list[lineno_index]
    line = new_source_lines[lineno]
    lline = line.lstrip()

    if lline == '#if 0':
      skip = True
      continue
    elif skip:
      if lline == '#endif':
        skip = False
      continue
    
    if line.endswith('}') or line.endswith('{') or line.endswith(':') or line.endswith(';') or lline.startswith('#'):
      continue
    if lline.startswith('[[') and line.endswith(']]'):
      continue
    if line.endswith(')'):
      if '(' in line:
        n = line[:line.index('(')].strip()
        if n.isupper():  # n is presumably CPP macro name
          continue

    if lline.startswith('@') or lline[0].isdigit():
      print('Not a C++/C line @ {lineno}: `line`  STOPPING')
      break

    if lline.isupper() and lline.isidentifier():
      continue
    
    if lineno_index < len(lineno_list) - 1:
      nlineno = lineno_list[lineno_index + 1]
      nline = new_source_lines[nlineno]
      if nline.lstrip().startswith('#'):
        continue
      if nline.lstrip().startswith('@'):
        print('Not a C++/C line @ {nlineno}: `nline`  STOPPING')
        break
      print(f'unexpected EOL @ {lineno}: `{line}`')
      print(f'                 {nlineno}: `{nline}`')
      #assert 0
    else:
      print(f'unexpected EOL @ {lineno}: `{line}`')
      #assert 0

  return new_source_lines

def filter_blocks_and_statements(source_lines):
  """Pass that eliminates everything that is not a {}-block or a
  statement (line ending with ;) or a declaration (line ending with :)

  """
  new_source_lines = dict()
  for lineno, line in source_lines.items():
    if line.lstrip().startswith('#'):
      continue
    if line.endswith('{') or line.endswith('}') or line.endswith(';') or line.endswith(':'):
      new_source_lines[lineno] = line

  return new_source_lines

class Namespace:

  def __init__(self, name=''):
    self.name = name
    self.data = []

class Block:

  def __init__(self, prefix):
    self.prefix = prefix
    self.content = []
    self.suffix = None


def collect_blocks(source_lines, filename):

  def postprocess(body):
    new_body = []
    last_lineno = None
    for row in body:
      if not row[-1]:
        continue
      if len(row) == 2:
        new_body.append(row[0])
        last_lineno = None
      else:
        lineno, line = row[:-1]
        if lineno == last_lineno:
          _, last_line = new_body.pop()
          line = last_line + ' ' + line
        new_body.append((lineno, line))
        last_lineno = lineno
    return new_body

  lineno_index = -1
  lineno_list = list(source_lines)
  cache = dict()
  stack = []
  body = []
  public = True
  while True:
    lineno_index += 1
    if lineno_index >= len(lineno_list):
      break
    lineno = lineno_list[lineno_index]
    line = cache.pop(lineno, source_lines[lineno])
    lline = line.lstrip()
    if not lline or lline == ';':
      continue

    #print(f'{len(stack)}:{lineno}:{line}')
    
    if '}' in lline:
      i = lline.index('}')
      new_block = False
      if '{' in lline:
        j = lline.index('{')
        if j < i:
          if i == j + 1 and not lline.startswith('namespace'):
            body.append((lineno, lline[:i + 1], public))
            rest = lline[i+1:].strip()
            if rest:
              cache[lineno] = rest
              lineno_index -= 1
            continue
          i = j
          new_block = True
    elif '{' in lline:
      new_block = True
      i = lline.index('{')
    else:
      if lline.startswith('public:'):
        public = True
      elif lline.startswith('private:') or lline.startswith('protected:'):
        public = False
      else:
        body.append((lineno, lline, public))
        continue
      i = line.index(':')
      rest = line[i+1:].strip()
      if rest:
        cache[lineno] = rest
        lineno_index -= 1
      continue

    lliner = lline[:i].rstrip()

    if lliner:
      body.append((lineno, lliner, public))

    if new_block:
      stack.append((public, body))
      body = []
      if lliner.startswith('class '):
        public = False
      elif lliner.startswith('struct ') or lliner.startswith('namespace ') or lliner.startswith('enum '):
        pass
      else:
        # functions, {}-blocks
        public = False
    else:
      public, body_ = stack.pop()
      lst = postprocess(body)
      if not lst and body_:
        lno, ln, p = body_.pop()
        if ln.startswith('namespace '):
          body_.append((lno, ln, p))
          body_.append((lst, public))
        else:
          body_.append((lno, ln + ';', p))
      else:
        body_.append((lst, public))
      body = body_

    cache[lineno] = lline[i+1:]
    lineno_index -= 1
  assert not stack  # sanity check

  body = postprocess(body)

  # from pprint import pprint
  # pprint(body)
  
  def make_tree(lst, namespace=None, parent=None):
    if namespace is None:
      namespace = []
    targets = []
    entering_namespace = False
    for item in lst:
      if entering_namespace:
        assert isinstance(item, list), type(item)
        targets.extend(make_tree(item, namespace=namespace))
        namespace.pop()
        entering_namespace = False
      elif isinstance(item, tuple):
        lineno, line = item
        if line.startswith('namespace ') and '=' not in line:
          _, nsname = line.split()
          namespace.append(nsname)
          entering_namespace = True
        elif line.startswith('class ') or (line.startswith('template') and ' class ' in line):
          targets.append(Node('class', line, namespace=namespace[:], lineno=lineno, filename=filename, parent=parent))
        elif line.startswith('struct ') or (line.startswith('template') and ' struct ' in line):
          targets.append(Node('struct', line, namespace=namespace[:], lineno=lineno, filename=filename, parent=parent))
        elif line.startswith('enum '):
          targets.append(Node('enum', line, namespace=namespace[:], lineno=lineno, filename=filename, parent=parent))
        elif line.startswith('using '):
          print(f'{lineno}:`{line}` <- ignoring')
        elif '(' in line:
          targets.append(Node('function', line, namespace=namespace[:], lineno=lineno, filename=filename, parent=parent))
        else:
          targets.append(Node('attribute', line, namespace=namespace[:], lineno=lineno, filename=filename, parent=parent))
      else:
        assert isinstance(item, list)
        if not targets:
          targets.append(Node('', ''))
        assert targets[-1].kind in {'', 'class', 'struct', 'enum'}, (targets[-1].kind, targets[-1].spec)
        targets[-1].content.extend(make_tree(item, parent=targets[-1]))

    return targets

  return make_tree(body)

class Node:

  def __init__(self, kind, spec, **params):
    self.kind = kind
    self.spec = spec
    self.params = params
    self.content = []

  def __str__(self):
    return self.tostring()

  def tostring(self, tab=''):
    lineno = self.params.get('lineno')
    ns = self.params.get('namespace')
    if isinstance(ns, list):
      ns = '::'.join(ns)
    if self.kind == '':
      lines = []
      for item in self.content:
        lines.append(item.tostring(tab=tab+'  '))
      return '\n'.join(lines)
    elif self.kind in {'class', 'struct', 'enum'} and self.content:
      lines = [f'{lineno:3}:{tab}{self.spec} {{  // {ns}']
      for item in self.content:
        lines.append(item.tostring(tab=tab+'  '))
      lines.append(f'   :{tab}}}')
      return '\n'.join(lines)
    else:
      assert not self.content, (self.kind, self.spec, lineno)
      if lineno is None:
        return f'{tab}{self.spec}'
      return f'{lineno:3}:{tab}{self.spec}'

  def gettype(self, with_template=False):
    if self.kind == 'function':
      i = self.spec.index('(')
      rest, name = self.spec[:i].rsplit(None, 1)
      if rest.startswith('template'):
        j = rest.rindex('>')
        tmpl = rest[:j+1]
        typ = rest[j+1:i - len(name)].strip()
      else:
        tmpl = None
        typ = rest[:i - len(name)].strip()
      if with_template:
        if tmpl is not None:
          return f'<sup>{tmpl}</sup>{typ}'
        return typ
    else:
      assert 0, self.kind  # not impl

  def getargs(self):
    if self.kind == 'function':
      i = self.spec.index('(')
      j = self.spec.index(')', i)
      return self.spec[i: j + 1]
    else:
      assert 0, self.kind  # not impl

  def get_args_and_types_and_init(self):
    args = self.getargs()[1:-1]
    atypes = dict()
    ainit = dict()
    for type_name in args.split(','):  # todo: typ may contain commas
      if not type_name:
        continue
      if '=' in type_name:
        type_name, init = type_name.rsplit('=', 1)
      else:
        init = None
      i = len(type_name) - 1
      while i > 0 and (type_name[i].isalnum() or type_name[i] == '_'):
        i -= 1
      i += 1
      atyp = type_name[:i].strip()
      aname = type_name[i:].strip()
      atypes[aname] = atyp
      if init is not None:
        ainit[aname] = ainit
    return atypes, ainit

  def getname(self, with_namespace=False, with_parent=False):
    prefix = ''
    if with_namespace:
      ns = self.params.get('namespace')
      if isinstance(ns, list):
        ns = '::'.join(ns)
      if ns:
        prefix = prefix + ns + '::'
    if with_parent:
      parent = self.params.get('parent')
      if parent is not None:
        prefix = prefix + parent.getname() + '::'

    if self.kind in {'class', 'struct'}:
      i = self.spec.index(self.kind)
      if ':' in self.spec[i:]:
        j = self.spec.rindex(':')
      else:
        j = len(self.spec)
        if self.spec.endswith(';'):
          j -= 1
      name = self.spec[i + len(self.kind): j].strip()
      return prefix + name
    elif self.kind == 'function':
      i = self.spec.index('(')
      rest, name = self.spec[:i].rsplit(None, 1)
      if rest.startswith('template'):
        j = rest.rindex('>')
        typ = rest[j+1:i - len(name)].strip()
      else:
        typ = rest[:i - len(name)].strip()
      return prefix + name

      
    elif self.kind == 'enum':
      assert 0, (self.spec)  # not impl
    else:
      assert 0, (self.kind, self.spec)  # not impl

  def tomarkdown(self, comments):
    lines = []

    lineno = self.params.get('lineno')
    ns = self.params.get('namespace')
    if isinstance(ns, list):
      ns = '::'.join(ns)

    if self.kind in {'class', 'struct'}:
      lines.append(f'# {self.getname(with_namespace=True)} {self.kind.title()} Reference\n')

      lineno = self.params.get('lineno')

      if lineno in comments:
        #lines.append('```')
        lines.append(comments[lineno])
        #lines.append('```')
        lines.append('')

      member_functions = [item for item in self.content if item.kind == 'function']
      if member_functions:
        lines.append(f'## Public Member Functions\n')

        constructors = [item for item in member_functions if item.getname() == self.getname()]
        destructors = [item for item in member_functions if item.getname() == '~' + self.getname()]
        member_functions = constructors + destructors + [item for item in member_functions if item.getname() not in {self.getname(), '~' + self.getname()}]

        lines.append('|   |   |')
        lines.append('|--:|:--|')
        for item in member_functions:
          lines.append(f'| ` {item.gettype(with_template=True)} ` | [**{item.getname()}**](#fnc-{self.getname().lower()}-{item.getname().lower()}) ` {item.getargs()} ` |')

        lines.append('')
          
        lines.append(f'## Member Function Documentation\n')


        for item in member_functions:
          lineno = item.params.get('lineno')

          lines.append(f'### <a name="fnc-{self.getname().lower()}-{item.getname().lower()}">-</a>\n')

          atypes, ainit = item.get_args_and_types_and_init()

          #fname = f'<a name="fnc-{self.getname().lower()}-{item.getname().lower()}">**{item.getname()}**</a>'
          fname = f'**{item.getname()}**'

          
          if len(atypes) == 0:
            lines.append(f'` {item.gettype(with_template=True)} ` {fname} ()')
          elif len(atypes) == 1:
            aname, atype = list(atypes.items())[0]
            lines.append(f'` {item.gettype(with_template=True)} ` {fname} ( ` {atype} ` {aname} )')
          else:
            mx = max(map(len, atypes.values()))
            lines.append(f'` {item.gettype(with_template=True)} ` {fname} (')
            for i, (aname, atype) in enumerate(atypes.items()):
              s = ')' if i == len(atypes) - 1 else ','
              lines.append(f'`        {{:{mx}}} ` {aname} {s}'.format(atype))
              
          lines.append('')
              
          if lineno in comments:
            # lines.append('```')
            lines.append(comments[lineno])
            # lines.append('```')
            lines.append('')

    return '\n'.join(lines)

    
def main():
  if len(sys.argv) == 1:
    print(f'{sys.argv[0]} <path to cc sources>')
    return
  for path in sys.argv[1:]:
    for fn in header_files(path):
      if 'ryu_long_double_constants.h' in fn:
        continue
      print(f'{fn=}')

      source_lines = dict(enumerate(open(fn, 'r', encoding='utf-8-sig').read().splitlines()))

      source_lines = eliminate_cpp_newlines(source_lines)

      source_lines, comments = filter_comments(source_lines)

      source_lines = eliminate_newlines(source_lines)
      
      source_lines = filter_blocks_and_statements(source_lines)

      for tree in collect_blocks(source_lines, fn):
        print(tree.tomarkdown(comments))
        
      continue
      for lineno, line in source_lines.items():
        print(f'{lineno}: {line}')
      continue
      for lineno, block in comment_blocks.items():
        print('---')
        print(block)
        print(source_lines[lineno])

      split_curly_blocks(source_lines)

  pass


if __name__ == "__main__":
  main()
