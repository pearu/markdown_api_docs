import collections
import os
import re
from .node import Node, _split_identifier


def source_reader(source, root_path=None, stop_at_stage=None, apply_onread=None):
  """Return a tree of C++ constructs defined by a specified source.

  Source can be a
  - a string containing C++ code
  - a file name to C++ source or header code
  - a directory name to C++ files and subdirectories
  - a list of C++ source code lines
  """
  if root_path is None:
    root_path = os.getcwd()
  if isinstance(source, str):
    if os.path.isfile(source):
      filename = os.path.relpath(source, root_path)
      source_text = open(source, 'r', encoding='utf-8-sig').read()
      if apply_onread is not None:
        source_text = apply_onread(source_text)
      source_lines = dict(enumerate(source_text.splitlines()))
    elif os.path.isdir(source):
      if stop_at_stage == 'after_filter_comments':
        top_node = []
      else:
        top_node = Node(None, 'directory', source)
        top_node.set_root_path(root_path)
      dir_nodes = dict()
      for dirpath, dnames, fnames in os.walk(source):
        for f in fnames:
          if os.path.splitext(f)[1] in {".h", ".hpp"}:
            if dirpath not in dir_nodes:
              if stop_at_stage == 'after_filter_comments':
                node = dir_nodes[dirpath] = []
                top_node.append(node)
              else:
                node = dir_nodes[dirpath] = Node(None, 'directory', dirpath)
                top_node.add(node)
            fn = os.path.join(dirpath, f)
            if stop_at_stage == 'after_filter_comments':
              dir_nodes[dirpath].append((fn, source_reader(fn, root_path=root_path, stop_at_stage=stop_at_stage, apply_onread=apply_onread)))
            else:
              dir_nodes[dirpath].add(source_reader(fn, root_path=root_path, stop_at_stage=stop_at_stage, apply_onread=apply_onread))
      return top_node
    else:
      filename = '<string>'
      source_lines = dict(enumerate(source.splitlines()))
  elif isinstance(source, list):
    filename = '<list>'
    source_lines = dict(enumerate(source))
  else:
    raise TypeError(f'source must be a file name, directory name, source text, or a list of source lines, got {type(source)}')

  source_lines = _eliminate_cpp_newlines(source_lines)

  source_lines, comments = _filter_comments(source_lines)

  if stop_at_stage == 'after_filter_comments':
    return source_lines, comments
  
  source_lines = _eliminate_newlines(source_lines)

  source_lines, cpp_data = _filter_cpp_data(source_lines)
  
  source_lines = _filter_blocks_and_statements(source_lines, cpp_data['define'])

  pretree = _make_pretree(source_lines)

  return _make_tree(filename, comments, cpp_data, pretree)


def _eliminate_cpp_newlines(source_lines):
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


def _filter_comments(source_lines):
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
      elif '//' in line and (line[line.index('//') -1] != ':'):  # `https://...` is likely not a comment line
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
        assert '//' not in line or '://' in line, (lineno, line)
        assert '/*' not in line, (lineno, line)
        new_source_lines[lineno] = line.rstrip()
      # else discarding empty lines
  return new_source_lines, comments


def _eliminate_newlines(source_lines):
  """Pass that joins source lines that belong to the same C++ constuct.
  """
  new_source_lines = dict()

  def __isidentifier(s):
    return s.isalnum() or s == '_'

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
    elif ('R"(' in prev_line and ')"' not in prev_line):
      new_source_lines[prev_lineno] += '\n' + line
    elif prev_line.count('(') > prev_line.count(')'):
      new_source_lines[prev_lineno] += ' ' + line
    #elif (prev_line.startswith('enum ') or prev_line.startswith('typedef enum')) and not prev_line.endswith(';'):
    #  new_source_lines[prev_lineno] += ' ' + lline
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
          or (lline[0].isidentifier() and lline[0].islower())
          or lline.startswith(';')
          or lline.startswith('(')
        ))
        or ((prev_line[-1].isidentifier()) and lline.startswith('('))
    ):
      #print(f'>>> {prev_line} | {lline}')
      new_source_lines[prev_lineno] += ' ' + lline
    elif prev_line and (
            [c for c in {'.'} if lline.startswith(c)]
            or prev_line.endswith('::')
    ):
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
      # some C++ headers use `#if 0 ... #endif` blocks for storing
      # arbitrary text (such as docs).
      skip = True
      continue
    elif skip:
      if lline == '#endif':
        skip = False
      continue

    if line.endswith('}') or line.endswith('{') or line.endswith(':') or line.endswith(';') or lline.startswith('#') or line.endswith(')'):
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
    else:
      print(f'unexpected EOL @ {lineno}: `{line}`')

  return new_source_lines


def _filter_cpp_data(source_lines):
  """Pass that filters CPP directives and source lines.
  """
  new_source_lines = dict()
  cpp_data = dict(include=[], define=dict())
  for lineno, line in source_lines.items():
    lline = line.lstrip()
    if lline.startswith('#include'):
      fn = lline[8:].strip()
      assert fn[0] in '"<' and fn[-1] in '">', fn
      cpp_data['include'].append(fn[1:-1])
    elif lline.startswith('#define'):
      n, rest = _split_identifier(lline[7:].lstrip())
      cpp_data['define'][n] = (lineno, rest)
    elif lline.startswith('#'):
      pass
    else:
      new_source_lines[lineno] = line
  return new_source_lines, cpp_data

def _splitatmark(line, mark):
  stack = []
  pmap = {'(': ')', '{': '}', '[': ']'}
  string_literal = False
  for i in range(len(line)):
    if string_literal:
      if line[i] == '"' and (i==0 or line[i-1] != '\\'):
        string_literal = False
      continue
    if line[i] == '"' and (i==0 or line[i-1] != '\\'):
      string_literal = True
      continue    
    if line[i] in pmap:
      stack.append(pmap[line[i]])
    elif stack and line[i] == stack[-1]:
      stack.pop()
    elif not stack and line[i:i+len(mark)] == mark:
      return line[:i], line[i+1:]
  return line, None

def _apply_cpp_macro_to_text(text, name, macro):

  def worker(text):
    m = re.search(r'\b' + name + r'\b', text)
    if m:
      before, after = text[:m.start()], text[m.end():].lstrip()
      if callable(macro):
        if after.startswith('('):
          argline, rest = _splitatmark(after[1:], ')')
          assert rest is not None, (before, name, after, argline)
          print(f'{argline=}')
          args = []
          r = argline.lstrip()
          while r:
            arg, r = _splitatmark(r, ',')
            if r is not None:
              r = r.lstrip()
            args.append(arg.rstrip())
          middle = macro(*args)
          extra_newlines = max(0, argline.count("\n") - middle.count("\n"))
          middle += '\n' * extra_newlines
          return before + middle + worker(rest)
        else:
          return text
          #assert 0, (name, after)  # not implemented
      else:
        return before + macro + worker(after)
    return text

  return worker(text)

def _apply_cpp_macro(source_lines, name, macro):
  """Pass that applies CPP macro to source lines.

  macro is a callable that returns source line content with new lines replaced with spaces.
  """

  def worker(line):
    m = re.search(r'\b' + name + r'\b', line)
    if m:
      before, after = line[:m.start()], line[m.end():].lstrip()
      if callable(macro):
        if after.startswith('('):
          argline, rest = _splitatmark(after[1:].lstrip(), ')')
          if rest is None:
            return line
          assert rest is not None, (before, name, after, argline)
          args = []
          r = argline.lstrip()
          while r:
            arg, r = _splitatmark(r, ',')
            if r is not None:
              r = r.lstrip()
            args.append(arg.rstrip())
          return before + macro(*args) + worker(rest)
        else:
          pass
          #assert 0, (before, name, after)  # not implemented
      else:
        return before + macro + worker(after)
    return line
      
  new_source_lines = dict()
  for lineno, line in source_lines.items():
    new_source_lines[lineno] = worker(line)
  return new_source_lines
    
def _filter_blocks_and_statements(source_lines, cpp_defines):
  """Pass that eliminates everything that is not a {}-block or a
  statement (line ending with `;`) or a declaration (line ending with `:`)
  """
  new_source_lines = dict()
  for lineno, line in source_lines.items():
    lline = line.lstrip()
    if lline.startswith('static_assert('):
      continue
    if line.endswith('{') or line.endswith('}') or line.endswith(';') or line.endswith(':') or line.endswith(')'):
      new_source_lines[lineno] = line
    else:
      n, rest = _split_identifier(lline)
      if n in cpp_defines and rest.startswith('('):
        new_source_lines[lineno] = line
      else:
        print(f'{lineno}:{line}  <- ignoring')
    last_line = line

  return new_source_lines


def _make_pretree(source_lines):
  """Pass that constructs a premilinary tree of source lines and blocks
  with public data.
  """
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
      elif (lliner.startswith('struct ')
            or lliner.startswith('namespace ') or lliner.startswith('enum')
            or lliner.startswith('union')
            or lliner.startswith('typedef enum')
            or lliner.startswith('extern "C"')):
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
  
  return postprocess(body)

  
def _make_tree(filename, comments, cpp_data, pretree):
  """Pass that constructs a tree of nodes.
  """
  def worker(parent, lst, namespace, **params):
    entering_namespace = False
    block_node = None  # enum, union

    local_namespace = []
    extern_C_block = False
    typedef_enum = 0
    typedef_enum_params = None
    typedef_enum_line = None
    typedef_enum_node = None

    typedef = 0
    typedef_node = None
    for item in lst:
      if local_namespace:
        assert not extern_C_block
        assert isinstance(item, list), type(item)
        worker(parent, item, namespace + local_namespace)
        local_namespace.clear()
      elif extern_C_block:
        assert isinstance(item, list), (item)
        worker(parent, item, namespace, extern_C=True)
        extern_C_block = False
      elif typedef == 1:
        assert isinstance(item, list), (item, filename)
        worker(typedef_node, item, [])
        typedef = 2
      elif typedef == 2:
        assert isinstance(item, tuple), (item)
        lineno, line = item
        if line.endswith(';'):
          line = line[:-1].rstrip()
        typedef_node.spec += ' {} ' + line
        parent.add(typedef_node)
        typedef = 0
        typedef_node = None
      elif typedef_enum == 1:
        assert isinstance(item, list), (item)
        typedef_enum_node = Node(None, 'typedef enum', typedef_enum_line, **typedef_enum_params)
        worker(typedef_enum_node, item, [])
        typedef_enum_params = None
        typedef_enum = 2
      elif typedef_enum == 2:
        assert isinstance(item, tuple), (item)
        typedef_enum = 0
        lineno, line = item
        if line.endswith(';'):
          line = line[:-1].rstrip()
        typedef_enum_node.spec = line
        parent.add(typedef_enum_node)
      elif block_node is not None:
        assert isinstance(item, list)
        worker(block_node, item, [])
        parent.add(block_node)
        block_node = None
      elif isinstance(item, tuple):
        lineno, line = item
        if line.startswith('namespace ') and '=' not in line:
          _, nsname = line.split()
          local_namespace.append(nsname)
        elif line == 'extern "C"':
          extern_C_block = True
        elif [kind for kind in {'typedef struct'} if line.startswith(kind)]:
          typedef_node = Node.fromstring(None, line, namespace=namespace, lineno=lineno)
          if not line.endswith(';'):
            typedef = 1
        elif line.startswith('typedef enum'):
          typedef_enum = 1
          typedef_enum_line = line
          typedef_enum_params = dict(namespace=namespace, lineno=lineno)
        elif line in {'enum', 'union'}:
          block_node = Node.fromstring(parent, line, namespace=namespace, lineno=lineno)
        else:
          n = Node.fromstring(parent, line, namespace=namespace, lineno=lineno, **params)
          if n is not None:
            parent.add(n)
      else:
        assert isinstance(item, list)
        assert parent.content, (parent.kind, item, params)
        assert parent.content[-1].kind in ['file', 'directory'] + Node.block_kinds, (parent.content[-1].kind, parent.content[-1].spec)
        worker(parent.content[-1], item, [])

  top_node = Node(None, 'file', filename, cpp_data=cpp_data, comments=comments)
  worker(top_node, pretree, [])

  return top_node
