import os
import markdown_api_docs as mad
from markdown_api_docs.source_reader import _filter_cpp_data as filter_cpp_data
from markdown_api_docs.spanstr import spanstr

def test_xla():
  path = os.path.abspath(os.path.join(os.path.dirname(mad.__file__), '..', '..', 'xla'))
  if not os.path.isdir(path):
    pytest.skip(f'could not find xla sources in {path}')
  tree = mad.source_reader(os.path.join(path, 'xla'), stop_at_stage = 'after_filter_comments')

  def flatten(lst):
    if isinstance(lst, list):
      for item in lst:
        yield from flatten(item)
    else:
      yield lst

  success_count = 0
  fail_count = 0
  for i, (fn, (source_lines, comments)) in enumerate(flatten(tree)):
    # if fn != '/home/pearu/git/pearu/xla/xla/primitive_util.h': continue

    ctx = mad.parser.Context(enable_debug_rerun=not True)

    source_lines, cpp_data = filter_cpp_data(source_lines)
    print(fn)

    source = ''
    for lineno, line in source_lines.items():
      source += line + '\n'
    source = f'{source}'
    if source.strip() == '': continue
    source = spanstr(source)
    #print(source)
    
    tree, rest = mad.parser.declaration_seq.split(ctx, source)
    if tree is None:
      #mad.parser.declaration_seq.split(ctx_debug, source)
      #ctx_debug.report()
      fail_count += 1
    else:
      #print(tree)
      #print(f'{rest=}')
      success_count += 1
    #assert tree is not None

    print(f'-------------------------------- > {success_count=}, {fail_count=}')
