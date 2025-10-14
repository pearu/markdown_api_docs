

def header_reader(filename):
  """Return a tree of C++ constructs defined by a header file.
  
   """
  
  source_lines = dict(enumerate(open(filename, 'r', encoding='utf-8-sig').read().splitlines()))

  source_lines = _eliminate_cpp_newlines(source_lines)

  source_lines, comments = _filter_comments(source_lines)

  source_lines = _eliminate_newlines(source_lines)

  source_lines, cpp_data = _filter_blocks_and_statements(source_lines)

  pretree = _make_pretree(source_lines)

  return _make_tree(pretree, comments, cpp_data)


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


def _eliminate_newlines(source_lines):
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
      # some C++ headers use `#if 0 ... #endif` blocks for storing
      # arbitrary text (such as docs).
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
    else:
      print(f'unexpected EOL @ {lineno}: `{line}`')

  return new_source_lines


def _filter_blocks_and_statements(source_lines):
  """Pass that eliminates everything that is not a {}-block or a
  statement (line ending with `;`) or a declaration (line ending with `:`)

  Also returns CPP include directive data.
  """
  new_source_lines = dict()
  cpp_data = dict(include=[])
  for lineno, line in source_lines.items():
    lline = line.lstrip()
    if lline.startswith('#'):
      lline_nospace = lline.replace(' ', '')
      if lline_nospace.startswith('#include'):
          fn = lline_nospace[7:]
          assert fn[0] in '"<' and fn[-1] in '">', fn
          cpp_data['include'].append(fn[1:-1])
      continue
    if line.endswith('{') or line.endswith('}') or line.endswith(';') or line.endswith(':'):
      new_source_lines[lineno] = line

  return new_source_lines, cpp_data


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

  return postprocess(body)


def _make_tree(pretree, comments, cpp_data):
  """Pass that constructs a tree of nodes.
  """

  def worker(lst):
    pass

  worker(pretree)
