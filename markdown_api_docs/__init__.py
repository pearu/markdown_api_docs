__all__ = ["source_reader", "markdown_writer", "make_api_docs", "parser"]

try:
    from ._version import __version__
except ImportError:
    import importlib.metadata

    try:
        __version__ = importlib.metadata.version("py" + __name__)
    except:
        __version__ = "N/A"

from .source_reader import source_reader
from .markdown_writer import markdown_writer
from . import parser

def make_api_docs(path, docfile='API.md', root_path=None):
  """Generate C++ API documentation from header files in path.

  The documentation is saved in docfile in Markdown format. The
  docfile is created for each sub-directory of path that contains
  C/C++ header files.
  """
  import os
  tree = source_reader(path, root_path=root_path)
  tree.params['docfile'] = docfile
  for node in tree.content:
    for dnode in node.collect('directory'):
      target = os.path.join(dnode.spec, docfile)
      doc = markdown_writer(dnode)
      f = open(target, 'w')
      f.write(doc)
      f.close()
      print(f'Created `{os.path.relpath(target, os.getcwd())}`')
