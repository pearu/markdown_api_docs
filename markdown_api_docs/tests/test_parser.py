
from markdown_api_docs.parser import *


def check(split, input, expected, expected_rest=None):
  ctx = Context()  # enable_debug_rerun=True, debug=True)
  if expected_rest is None:
    assert expected is None  # sanity check
    expected_rest = input
  result, rest = split(ctx, input)
  # ctx.report()
  if isinstance(expected, str):
    assert str(result) == expected, (result, expected, (rest, expected_rest))
  else:
    assert result == expected, (type(result), type(expected))
  assert rest == expected_rest, (result, expected, (rest, expected_rest))
  if expected is None:
    return
  # check stability
  ctx = Context()
  result2, rest2 = split(ctx, input[:len(input) - len(rest)].rstrip())
  if isinstance(expected, str):
    assert str(result2) == expected
  else:
    assert result2 == expected
  assert rest2 == ''

def check_declaration(input, expected, expected_rest=None):
  check(declaration.split, input.lstrip(), expected,
        expected_rest=(expected_rest if expected_rest is not None else expected_rest))

def test_ordinary_string_literal():
  split = ordinary_string_literal.split
  check(split, '"a" b', '"a"', 'b')
  check(split, '"" b', '""', 'b')
  check(split, '"a(" b', '"a("', 'b')

  check(split, 'R"a" b', None)
  check(split, 'R"(a)" b', 'R"(a)"', 'b')
  check(split, 'R"()" b', 'R"()"', 'b')
  check(split, 'R"ak()ak" b', 'R"ak()ak"', 'b')
  check(split, 'R"ak()an" b', None)
  
def test_word():
  check(word.split, 'a b', 'a', 'b')
  check(word.split, 'a1 b', 'a1', 'b')
  check(word.split, '1 b', None)

def test_identifier():
  check(identifier.split, 'a b', 'a', 'b')
  check(identifier.split, 'for b', None)

def test_name():
  check(name.split, 'a b', 'a', 'b')
  check(name.split, 'operator+  b', 'operator+', 'b')
  check(name.split, 'operator  new  b', 'operator new', 'b')
  check(name.split, 'operator  ""_kw  b', 'operator ""_kw', 'b')
  check(name.split, 'a<T > b', 'a<T>', 'b')
  check(name.split, 'a< T,  U> b', 'a<T, U>', 'b')
  check(name.split, 'operator<<  <T>  b', 'operator<<<T>', 'b')
  check(name.split, 'operator new<T>  b', 'operator new<T>', 'b')
  # check(name.split, 'a<T><U> b', 'a<T><U>', 'b')  # is this valid C++?

def test_ns_name():
  split = ns_name.split
  check(split, 'a b', 'a', 'b')
  check(split, 'A::a b', 'A::a', 'b')
  check(split, 'A::B::a b', 'A::B::a', 'b')
  check(split, '::a b', '::a', 'b')
  check(split, '::A::a b', '::A::a', 'b')

  check(split, 'a::inline b c', 'a::inline b', 'c')
  check(split, 'A::a::inline b c', 'A::a::inline b', 'c')
  check(split, '::inline b c', '::inline b', 'c')
  
def test_identifier_expression():
  split = identifier_expression.split
  check(split, 'a b', 'a', 'b')
  check(split, 'A::a b', 'A::a', 'b')
  check(split, '::A::a b', '::A::a', 'b')
  check(split, '::a b', '::a', 'b')
  check(split, 'A<T>::a b', 'A<T>::a', 'b')
  check(split, 'B::A<T>::a b', 'B::A<T>::a', 'b')
  check(split, '::template   A  b', '::template A', 'b')
  check(split, '::template   A::C  b', '::template A::C', 'b')
  check(split, 'D::template   A::C  b', 'D::template A::C', 'b')

  check(split, '~A b', '~A', 'b')
  check(split, '::~A b', '::~A', 'b')
  check(split, 'C::~A b', 'C::~A', 'b')

  check(split, 'decltype(a) b', 'decltype(a)', 'b')
  check(split, '~decltype(a) b', '~decltype(a)', 'b')
  
  check(split, 'A::decltype(a) b', 'A::decltype(a)', 'b')
  check(split, 'A::~decltype(a) b', 'A::~decltype(a)', 'b')

  check(split, 'decltype(a)::A b', 'decltype(a)::A', 'b')
  check(split, '~decltype(a)::A b', '~decltype(a)::A', 'b')

  check(split, 'A...[0] b', 'A...[ 0 ]', 'b')
  check(split, 'B::A...[0] b', 'B::A...[ 0 ]', 'b')
  check(split, 'B::A...[0 b', None)
  
def test_unqualified_name():
  check(unqualified_name.split, 'a b', 'a', 'b')

def test_template_argument():
  split = template_argument.split
  check(split, 'T', 'T', '')
  #check(split, 'int', 'int', '')
  
def test_template_argument_list():
  split = template_argument_list.split
  check(split, 'T', 'T', '')

def test_declarator():
  split = declarator.split
  check(split, 'a b', 'a', 'b')
  check(split, 'a [[d]] b', 'a [[d]]', 'b')
  check(split, 'a [[d]][[g]] b', 'a [[d]] [[g]]', 'b')
  check(split, '...a b', '...a', 'b')
  check(split, '...a[[f]] b', '...a [[f]]', 'b')

  for r in ['*', '&', '&&']:
    check(split, r + 'a b', r + ' a', 'b')
    check(split, r + '[[f]]a b', r + ' [[f]] a', 'b')
    check(split, r + '[[f]][[g]]a b', r + ' [[f]] [[g]] a', 'b')

  check(split, '*const a b', '* const a', 'b')
  check(split, '*[[f]]const a b', '* [[f]] const a', 'b')

  check(split, 'A::*a b', 'A::* a', 'b')
  check(split, 'C::A::*a b', 'C::A::* a', 'b')
  check(split, 'A::*[[f]]a b', 'A::* [[f]] a', 'b')
  check(split, 'A::*volatile a b', 'A::* volatile a', 'b')

  check(split, 'A::**a b', 'A::* * a', 'b')
  check(split, 'A::* B::*a b', 'A::* B::* a', 'b')
  
  check(split, 'foo() b', 'foo()', 'b')
  check(split, 'foo() & b', 'foo() &', 'b')
  check(split, 'foo() && b', 'foo() &&', 'b')
  check(split, '(*foo)() b', '(* foo)()', 'b')
  check(split, '(&&foo)() b', '(&& foo)()', 'b')
  check(split, '(*foo)() const b', '(* foo)() const', 'b')
  check(split, '(*foo)() [[f]] b', '(* foo)() [[f]]', 'b')

  check(split, 'arr[] b', 'arr[]', 'b')
  check(split, 'arr[] [[f]] b', 'arr[] [[f]]', 'b')
  check(split, '(&arr)[] b', '(& arr)[]', 'b')
  check(split, '(  &&   arr)[] b', '(&& arr)[]', 'b')

def test_abstract_declarator():
  split = abstract_declarator.split
  check(split, '* b', '*', 'b')
  check(split, '& b', '&', 'b')
  check(split, '&& b', '&&', 'b')
  check(split, '* [[a]] b', '* [[a]]', 'b')
  check(split, '(*) b', '(*)', 'b')
  check(split, '(&) b', '(&)', 'b')
  check(split, '(&&) b', '(&&)', 'b')
  check(split, '(*)(int) b', '(*)(int)', 'b')
  check(split, '(&)(int) b', '(&)(int)', 'b')
  check(split, '(&&)(int) b', '(&&)(int)', 'b')
  check(split, '(*)[] b', '(*)[]', 'b')
  check(split, '(&)[] b', '(&)[]', 'b')
  check(split, '(&)[] b', '(&)[]', 'b')
  
def test_parameter_declaration():
  split = parameter_declaration.split

  check(split, 'A*', 'A *', '')
  check(split, 'A*a', 'A * a', '')
  check(split, 'A*[[a]]', 'A * [[a]]', '')
  check(split, 'A&', 'A &', '')
  check(split, 'A&&', 'A &&', '')
  check(split, 'A...', 'A ...', '')

  check(split, 'A (*)(int) b', 'A (*)(int)', 'b')
  check(split, 'A (*)() b', 'A (*)()', 'b')
  check(split, 'A (&)() b', 'A (&)()', 'b')
  check(split, 'A (&)[] b', 'A (&)[]', 'b')

def test_keyword_type_specifier():
  split = keyword_type_specifier.split
  check(split, 'int a', 'int', 'a')
  check(split, 'short  int a', 'short int', 'a')
  check(split, 'int int a', 'int', 'int a')
  check(split, 'long long a', 'long long', 'a')

def test_placeholder_type_specifier():
  split = placeholder_type_specifier.split
  check(split, 'auto a', 'auto', 'a')
  
def test_type_specifier():
  split = type_specifier.split
  check(split, 'int a', 'int', 'a')
  check(split, 'auto a', 'auto', 'a')
  check(split, 'decltype(auto) a', 'decltype(auto)', 'a')

  check(split, 'A auto a', 'A auto', 'a')
  check(split, 'C::A auto a', 'C::A auto', 'a')
  check(split, 'A<T> auto a', 'A<T> auto', 'a')
  check(split, 'C::A<T> auto a', 'C::A<T> auto', 'a')

  check(split, 'decltype(A) a', 'decltype(A)', 'a')
  check(split, 'decltype(1+2) a', 'decltype(1+2)', 'a')
  check(split, 'A...[1] a', 'A...[ 1 ]', 'a')
  check(split, 'C::A...[1] a', 'C::A...[ 1 ]', 'a')

  check(split, 'A a', 'A', 'a')
  check(split, 'C::A a', 'C::A', 'a')
  check(split, 'C::A<T  ,   U> a', 'C::A<T, U>', 'a')

  check(split, 'class A a', 'class A', 'a')
  check(split, 'enum A::B a', 'enum A::B', 'a')
  check(split, 'enum A::B<T> a', 'enum A::B<T>', 'a')
  check(split, 'enum A<T>::B a', 'enum A<T>::B', 'a')

  check(split, 'typename A a', 'typename A', 'a')
  check(split, 'typename C::A<T> a', 'typename C::A<T>', 'a')

  check(split, 'class A {} a', 'class A {}', 'a')
  check(split, 'class [[f]] A {} a', 'class [[f]] A {}', 'a')
  check(split, 'class C::A {} a', 'class C::A {}', 'a')
  check(split, 'class A<T> {} a', 'class A<T> {}', 'a')
  check(split, 'class A final {} a', 'class A final {}', 'a')
  check(split, 'class {} a', 'class {}', 'a')
  check(split, 'class [[f]] {} a', 'class [[f]] {}', 'a')

  check(split, 'class A: public B {} a', 'class A : public B {}', 'a')
  check(split, 'class A: virtual B {} a', 'class A : virtual B {}', 'a')
  check(split, 'class A: virtual public B {} a', 'class A : virtual public B {}', 'a')
  check(split, 'class A: public virtual B {} a', 'class A : public virtual B {}', 'a')
  check(split, 'class A: public B {} a', 'class A : public B {}', 'a')
  check(split, 'class A: public B::C {} a', 'class A : public B::C {}', 'a')
  check(split, 'class A: public ::C {} a', 'class A : public ::C {}', 'a')

  check(split, 'class A: public ::template B<T> {} a', 'class A : public ::template B<T> {}', 'a')
  check(split, 'class A: public C::template B<T> {} a', 'class A : public C::template B<T> {}', 'a')

  check(split, 'enum A {} a', 'enum A {}', 'a')
  check(split, 'enum [[f]] A {} a', 'enum [[f]] A {}', 'a')
  check(split, 'enum A : B {} a', 'enum A : B {}', 'a')
  check(split, 'enum A : B::C {} a', 'enum A : B::C {}', 'a')

  check(split, 'enum A { x, y} a', 'enum A { x, y }', 'a')
  check(split, 'enum A { x=1, y} a', 'enum A { x = 1, y }', 'a')
  check(split, 'enum A { x=D(1, 2), y} a', 'enum A { x = D(1, 2), y }', 'a')

def test_decl_specifier():
  split = decl_specifier.split
  check(split, 'int a', 'int', 'a')
  check(split, 'enum A { x=D(1, 2), y} a', 'enum A { x = D(1, 2), y }', 'a')

  check(split, 'int a', 'int', 'a')
  check(split, 'inline int a', 'inline', 'int a')
  check(split, 'constexpr int a', 'constexpr', 'int a')
  check(split, 'consteval int a', 'consteval', 'int a')
  check(split, 'constinit int a', 'constinit', 'int a')
  check(split, 'virtual int a', 'virtual', 'int a')
  check(split, 'friend int a', 'friend', 'int a')
  check(split, 'explicit int a', 'explicit', 'int a')

  check(split, 'register int a', 'register', 'int a')
  check(split, 'static int a', 'static', 'int a')
  check(split, 'extern int a', 'extern', 'int a')
  check(split, 'mutable int a', 'mutable', 'int a')
  check(split, 'thread_local int a', 'thread_local', 'int a')
  check(split, 'int mutable a', 'int', 'mutable a')

  check(split, 'A a', 'A', 'a')
  
def test_decl_specifier_seq():

  def make_split(max_nof_items=None):
    return (lambda ctx, line: decl_specifier_seq.split(ctx, line, max_nof_items=max_nof_items))

  check(make_split(), 'long int a', 'long int', 'a')
  check(make_split(0), 'long int a', None)
  check(make_split(1), 'long int a', 'long int', 'a')
  check(make_split(2), 'int a', 'int', 'a')
  check(make_split(3), 'int a', 'int', 'a')

def test_simple_declaration():
  split = simple_declaration.split
  check(split, 'int a, b; c', 'int a, b;', 'c')
  check(split, 'int a=1, b; c', 'int a = 1, b;', 'c')
  check(split, 'int a, b=1; c', 'int a, b = 1;', 'c')
  check(split, 'int a=1, b=2; c', 'int a = 1, b = 2;', 'c')
  check(split, 'int a=1; c', 'int a = 1;', 'c')
  check(split, 'int a; c', 'int a;', 'c')

  check(split, 'class A {}; c', 'class A {};', 'c')
  check(split, 'class A {} A; c', 'class A {} A;', 'c')

  check(split, 'class A { int a; }; c', 'class A { int a; };', 'c')

def test_function_definition():
  split = function_definition.split
  check(split, 'int foo() {} a', 'int foo() {}', 'a')
  check(split, 'int foo() {\n} a', 'int foo() {}', 'a')
  check(split, 'int foo() { return 1; } a', 'int foo() { return 1; }', 'a')
  check(split, '[[f]]int foo() {} a', '[[f]] int foo() {}', 'a')
  check(split, 'int foo() final {} a', 'int foo() final {}', 'a')
  check(split, 'long int foo() {} a', 'long int foo() {}', 'a')

  check(split, 'int A::foo() {} a', 'int A::foo() {}', 'a')
  check(split, '::B A::foo() {} a', '::B A::foo() {}', 'a')

  check(split, 'int foo(int i) {} a', 'int foo(int i) {}', 'a')
  check(split, 'int foo(A i) {} a', 'int foo(A i) {}', 'a')
  check(split, 'int foo(int i, int a) {} a', 'int foo(int i, int a) {}', 'a')
  check(split, 'int foo(int i, A a) {} a', 'int foo(int i, A a) {}', 'a')
  check(split, 'int foo(A i, int a) {} a', 'int foo(A i, int a) {}', 'a')

def test_declaration_empty():
  ctx = Context()
  tree, rest = declaration.split(ctx, ';;;')
  print(tree, rest)
    
  source = '''
;
  '''.lstrip()
  check_declaration(source, ';', '')
  check_declaration(';;;', ';', ';;')
  check_declaration('namespace {}', None)
  check_declaration('namespace {;}', 'namespace { ; }', '')
  check_declaration('namespace {;;}', 'namespace { ; ; }', '')


def test_declaration_variable():
  source = '''
int a;
  '''.lstrip()
  check_declaration(source, 'int a;', '')


def test_declaration_function():
  source = '''
int foo(int a) {
  return a;
}
  '''.lstrip()
  check_declaration(source, 'int foo(int a) { return a; }', '')
  
def test_declaration_class():

  source = '''

class A {
public:
  int foo() { return 1; }
  A () {}
  A (int a) {}
  A  (int a) : a_(0) {}
private:
  int a_;
};

  '''.lstrip()
  check_declaration(source, 'class A { public: int foo() { return 1; } A() {} A(int a) {} A(int a) : a_(0) {} private: int a_; };', '')

  check_declaration('class A { A() {} };', 'class A { A() {} };', '')
  check_declaration('class A { A(int a) {} };', 'class A { A(int a) {} };', '')
  check_declaration('class A { A(int a=1) {} };', 'class A { A(int a = 1) {} };', '')
  check_declaration('class A;', 'class A;', '')
  
def test_declaration_class_template():
  check_declaration(spanstr('''template <B> class A;'''), 'template <B> class A;', '')
  return    
  check_declaration('''template <> class A {};''', 'template <> class A {};', '')
  check_declaration('''template <typename B> class A {};''', 'template <typename B> class A {};', '')
  check_declaration('''template <typename B, int i> class A {};''', 'template <typename B, int i> class A {};', '')
  check_declaration('''template <typename B, int i=1> class A {};''', 'template <typename B, int i = 1> class A {};', '')
  check_declaration('''template <typename B> class A : public B {};''', 'template <typename B> class A : public B {};', '')


  check_declaration('''template <> class A;''', 'template <> class A;', '')


def test_spanstr():
  from markdown_api_docs.spanstr import spanstr

  source = '''

class A {
public:
  int foo() { return 1; }
  A () {}
  A (int a) {}
  A  (int a) : a_(0) {}
  ~A () {}
private:
  int a_;
};

  '''.lstrip()
  source = spanstr(source)
  
  check_declaration(source, 'class A { public: int foo() { return 1; } A() {} A(int a) {} A(int a) : a_(0) {} ~A() {} private: int a_; };', '')
