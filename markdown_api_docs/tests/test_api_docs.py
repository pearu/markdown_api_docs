import os
import pytest
import markdown_api_docs as mad

def test_mylib():
  path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
  if not os.path.isdir(path):
    pytest.skip(f'could not find {path}')

  mad.make_api_docs(path)

   
