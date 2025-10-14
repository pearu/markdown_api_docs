import os
import markdown_api_docs as mad


def main():

  root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'xla'))
  if not os.path.isdir(root_path):
    print(f'could not find xla sources in {root_path}')
    return

  path = os.path.join(root_path, 'xla', 'hlo', 'pass')

  mad.make_api_docs(path)


if __name__ == '__main__':
  main()
