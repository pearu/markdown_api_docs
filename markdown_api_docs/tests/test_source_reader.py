import os
import pytest
import markdown_api_docs as mad

def test_simple():

  tree = mad.source_reader('''
namespace mad {
    // This is a class A documentation.    
    class A {
        private_mth();
      public:
        // This is a class A constructor documentation.
        A() { }
        A(int x) { }
        // This is a class A member function foo documentation.
        int foo(int x) { return x; }
    };
}  // namespace mad
    ''')
  assert tree.tostring() == '''// File: <string>
  3:  class A {  // `class mad::A`
  7:    A();  // ` mad::A::A`
  8:    A(int x);  // ` mad::A::A`
 10:    int foo(int x);  // `int mad::A::foo`
   :  }'''


  

def test_xla():
  path = os.path.abspath(os.path.join(os.path.dirname(mad.__file__), '..', '..', 'xla'))
  if not os.path.isdir(path):
    pytest.skip(f'could not find xla sources in {path}')
  tree = mad.source_reader(os.path.join(path, 'xla'))
  s = tree.tostring()

  
def test_stablehlo():
  path = os.path.abspath(os.path.join(os.path.dirname(mad.__file__), '..', '..', 'stablehlo'))
  if not os.path.isdir(path):
    pytest.skip(f'could not find stablehlo sources in {path}')
  tree = mad.source_reader(os.path.join(path, 'stablehlo'))

  
def test_mylib():
  path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'mylib'))
  if not os.path.isdir(path):
    pytest.skip(f'could not find {path}')
  tree = mad.source_reader(path)
  print(tree)
  assert tree.tostring() == '''\
ROOT=markdown_api_docs/tests/data/mylib
Directory: ROOT/.
// File: ROOT/mylib.h
  3:      int mysquare(int x);  // `int ::mysquare`
  5:      int global_variable;  // `template <> int ::global_variable`
  9:      int foo_(int, int);  // `extern "C" int foo_`
Directory: ROOT/include
// File: ROOT/include/foo.h
  9:      class Foo {  // `class mylib::foo::Foo`
 13:        Foo(int default_value=0): value(default_value);  // ` mylib::foo::Foo::Foo`
 16:        ~Foo();  // ` mylib::foo::Foo::~Foo`
 19:        int add(int y);  // `int mylib::foo::Foo::add`
 23:        int value;  // `int mylib::foo::Foo::value`
 26:        struct Bar {  // `struct mylib::foo::Foo::Bar`
 27:          int a;  // `int mylib::foo::Foo::Bar::a`
 29:          int b;  // `int mylib::foo::Foo::Bar::b`
   :        }
   :      }
 34:      int get_value(const Foo& f);  // `int mylib::foo::get_value`
 38:      int foo_variable;  // `template <> int mylib::foo::foo_variable`
 41:      int mylib_variable;  // `int mylib::mylib_variable`
 47:      class Car: public Foo {  // `class mylib2::Car: Foo`
 49:        int mul(int y);  // `int mylib2::Car::mul`
   :      }
 54:      class Sar: public Foo;  // `class mylib2::Sar: Foo`'''


def _test_enum():

  tree = mad.source_reader('''

// Color doc
enum Color {
  // red color doc
  red,
  // green color doc
  green,
  blue
};

''')
  print(tree)
  assert tree.tostring() == ''''''
