from markdown_api_docs import utils
from markdown_api_docs.utils import *

def test_split_identifier():
  assert utils.split_identifier('a1') == ('a1', '')
  assert utils.split_identifier('a1 b') == ('a1', 'b')
  assert utils.split_identifier('a1-b') == ('a1', '-b')
  assert utils.split_identifier('1a-b') == (None, '1a-b')

def test_split_unqualified_identifier():
  assert utils.split_unqualified_identifier('a1 b') == ('a1', 'b')
  assert utils.split_unqualified_identifier('a1 ') == ('a1', '')
  assert utils.split_unqualified_identifier('1a b') == (None, '1a b')
  assert utils.split_unqualified_identifier('ns::a1 b') == (None, 'ns::a1 b')
  assert utils.split_unqualified_identifier('::a1 b') == (None, '::a1 b')
  assert utils.split_unqualified_identifier('a:: b') == (None, 'a:: b')
  assert utils.split_unqualified_identifier('operator+  ()') == ('operator+', '()')
  assert utils.split_unqualified_identifier('operator       new a') == ('operator new', 'a')
  assert utils.split_unqualified_identifier('operator delete   [] ;') == ('operator delete []', ';')
  assert utils.split_unqualified_identifier('a1<T> b') == (simple_template_id('a1', 'T'), 'b')
  assert utils.split_unqualified_identifier('a1<T,   K> b') == (simple_template_id('a1', 'T,   K'), 'b')

def test_split_qualified_identifier():
  assert utils.split_qualified_identifier('a1 b') == (None, 'a1 b')
  assert utils.split_qualified_identifier('a1 ') == (None, 'a1 ')
  assert utils.split_qualified_identifier('ns::a1 b') == ((utils.scope_list(['ns']), 'a1'), 'b')
  assert utils.split_qualified_identifier('::a1 b') == ((utils.scope_list(['']), 'a1'), 'b')
  assert utils.split_qualified_identifier('::cls<T>::a1 b') == ((utils.scope_list(['', simple_template_id('cls', 'T')]), 'a1'), 'b')
  assert utils.split_qualified_identifier('ns::cls::a1 b') == ((utils.scope_list(['ns', 'cls']), 'a1'), 'b')
  assert utils.split_qualified_identifier('ns::cls::a1<T> b') == ((utils.scope_list(['ns', 'cls']), simple_template_id('a1', 'T')), 'b')
  assert utils.split_qualified_identifier('ns::cls<T>::a1 b') == ((utils.scope_list(['ns', simple_template_id('cls', 'T')]), 'a1'), 'b')
  assert utils.split_qualified_identifier('cls<T>::a1 b') == ((utils.scope_list([simple_template_id('cls', 'T')]), 'a1'), 'b')
  assert utils.split_qualified_identifier('ns::operator* b') == ((utils.scope_list(names=['ns']), 'operator*'), 'b')
  assert utils.split_qualified_identifier('ns::cls<T>::operator* b') == ((utils.scope_list(names=['ns', simple_template_id(name='cls', args='T')]), 'operator*'), 'b')
  assert utils.split_qualified_identifier('ns::cls<T>::operator new[] b') == ((utils.scope_list(names=['ns', simple_template_id(name='cls', args='T')]), 'operator new []'), 'b')

def test_split_declarator():
  assert utils.split_declarator('a1 b') == (utils.unqualified_id_declarator('a1'), 'b')
  assert utils.split_declarator('a1') == (utils.unqualified_id_declarator('a1'), '')
  assert utils.split_declarator('::a1 b') == (utils.qualified_id_declarator(scope=scope_list(names=['']), id='a1'), 'b')
  assert utils.split_declarator('cls<T>::a1 b') == (qualified_id_declarator(scope_list([simple_template_id('cls', 'T')]), 'a1'), 'b')

  assert utils.split_declarator('a1[[attrs]] b') == (utils.unqualified_id_declarator('a1', '[[attrs]]'), 'b')
  assert utils.split_declarator('ns::a1<T>[[attrs, debug]] b') == (qualified_id_declarator(scope=scope_list(names=['ns']), id=simple_template_id(name='a1', args='T'), attr='[[attrs, debug]]'), 'b')

  assert utils.split_declarator('*a1 b') == (utils.pointer_to_declarator(declarator=utils.unqualified_id_declarator('a1')), 'b')
  assert utils.split_declarator('*[[attr1]]a1 b') == (pointer_to_declarator(attr='[[attr1]]', cv=None, declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')
  assert utils.split_declarator('*const a1 b') == (pointer_to_declarator(attr=None, cv='const', declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')
  assert utils.split_declarator('*[[debug]]const a1 b') == (pointer_to_declarator(attr='[[debug]]', cv='const', declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')
  assert utils.split_declarator('*[[debug]]const ns::a1 b') == (pointer_to_declarator(attr='[[debug]]', cv='const', declarator=qualified_id_declarator(scope=scope_list(names=['ns']), id='a1', attr=None)), 'b')
  assert utils.split_declarator('*[[debug]]const ns::a1[[attr]] b') == (pointer_to_declarator(attr='[[debug]]', cv='const', declarator=qualified_id_declarator(scope=scope_list(names=['ns']), id='a1', attr='[[attr]]')), 'b')

  assert utils.split_declarator('&a1 b') == (lvalue_reference_declarator(attr=None, declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')
  assert utils.split_declarator('&&[[debug]]a1 b') == (rvalue_reference_declarator(attr='[[debug]]', declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')
  assert utils.split_declarator('foo() b') == (function_declarator(noptr_declarator=unqualified_id_declarator(id='foo', attr=None), parameter_list=[], cv=None, ref=None, except_=None, attr=None), 'b')

  ab_lst = [parameter_declaration(kind='(4)', decl_specifier_seq=[type_specifier_sequence(content=[simple_type_specifier(content=declared_type_name(tname=unqualified_id_declarator(id='a')))])]), parameter_declaration(kind='(4)', decl_specifier_seq=[type_specifier_sequence(content=[simple_type_specifier(content=declared_type_name(tname=unqualified_id_declarator(id='b')))])])]
  assert utils.split_declarator('foo(int a, int b)') == (function_declarator(noptr_declarator=unqualified_id_declarator(id='foo'), parameter_list=ab_lst), '')

  #(function_declarator(noptr_declarator=unqualified_id_declarator(id='foo', attr=None), parameter_list=ab_lst, cv=None, ref=None, except_=None, attr=None), 'b')
  assert utils.split_declarator('(*foo)(a, b) b') == (function_declarator(noptr_declarator=pointer_to_declarator(attr=None, cv=None, declarator=unqualified_id_declarator(id='foo', attr=None)), parameter_list=ab_lst, cv=None, ref=None, except_=None, attr=None), 'b')
  assert utils.split_declarator('(*foo [[attr]])(a, b) const && [[debug]] b') == (function_declarator(noptr_declarator=pointer_to_declarator(attr=None, cv=None, declarator=unqualified_id_declarator(id='foo', attr='[[attr]]')), parameter_list=ab_lst, cv='const', ref='&&', except_=None, attr='[[debug]]'), 'b')
  assert utils.split_declarator('(*const foo[[attr]])(a, b) const && [[debug]] b') == (function_declarator(noptr_declarator=pointer_to_declarator(attr=None, cv='const', declarator=unqualified_id_declarator(id='foo', attr='[[attr]]')), parameter_list=ab_lst, cv='const', ref='&&', except_=None, attr='[[debug]]'), 'b')
  assert utils.split_declarator('(*[[bug]]const foo[[attr]])(a, b) const && [[debug]] b') == (function_declarator(noptr_declarator=pointer_to_declarator(attr='[[bug]]', cv='const', declarator=unqualified_id_declarator(id='foo', attr='[[attr]]')), parameter_list=ab_lst, cv='const', ref='&&', except_=None, attr='[[debug]]'), 'b')

  assert utils.split_declarator('ns::* a1 b') == (pointer_to_member_declarator(nested_name_specifier=scope_list(names=['ns']), attr=None, cv=None, declarator=unqualified_id_declarator(id='a1', attr=None)), 'b')

def test_declarator_name():
  assert split_declarator('a1')[0].name == 'a1'
  assert split_declarator('a1')[0].qname == 'a1'
  assert split_declarator('A::a1')[0].name == 'a1'
  assert split_declarator('A::a1')[0].qname == 'A::a1'
  assert split_declarator('...a1')[0].name == 'a1'
  assert split_declarator('...a1')[0].qname == 'a1'
  assert split_declarator('*a1')[0].name == 'a1'
  assert split_declarator('*a1')[0].qname == 'a1'
  assert split_declarator('*A::a1')[0].name == 'a1'
  assert split_declarator('*A::a1')[0].qname == 'A::a1'
  assert split_declarator('C::*A::a1')[0].name == 'a1'
  assert split_declarator('C::*A::a1')[0].qname == 'A::a1'
  assert split_declarator('&a1')[0].name == 'a1'
  assert split_declarator('&a1')[0].qname == 'a1'
  assert split_declarator('&A::a1')[0].name == 'a1'
  assert split_declarator('&A::a1')[0].qname == 'A::a1'
  assert split_declarator('&&a1')[0].name == 'a1'
  assert split_declarator('&&a1')[0].qname == 'a1'
  assert split_declarator('&&A::a1')[0].name == 'a1'
  assert split_declarator('&&A::a1')[0].qname == 'A::a1'

  assert split_declarator('foo[]')[0].name == 'foo'
  assert split_declarator('foo[]')[0].qname == 'foo'
  assert split_declarator('foo[5]')[0].name == 'foo'
  assert split_declarator('foo[5]')[0].qname == 'foo'
  assert split_declarator('(*foo)[]')[0].name == 'foo'
  assert split_declarator('(*foo)[]')[0].qname == 'foo'
  assert split_declarator('(&&foo)[5]')[0].name == 'foo'
  assert split_declarator('(&&foo)[5]')[0].qname == 'foo'

  assert split_declarator('A::foo[]')[0].name == 'foo'
  assert split_declarator('A::foo[]')[0].qname == 'A::foo'
  assert split_declarator('A::foo[5]')[0].name == 'foo'
  assert split_declarator('A::foo[5]')[0].qname == 'A::foo'
  assert split_declarator('(*A::foo)[]')[0].name == 'foo'
  assert split_declarator('(*A::foo)[]')[0].qname == 'A::foo'
  assert split_declarator('(&&A::foo)[5]')[0].name == 'foo'
  assert split_declarator('(&&A::foo)[5]')[0].qname == 'A::foo'

  assert split_declarator('foo(a)')[0].name == 'foo'
  assert split_declarator('foo(a)')[0].qname == 'foo'
  assert split_declarator('foo()')[0].name == 'foo'
  assert split_declarator('foo()')[0].qname == 'foo'
  assert split_declarator('(*foo)(a, b)')[0].name == 'foo'
  assert split_declarator('(*foo)(a, b)')[0].qname == 'foo'
  assert split_declarator('(&&foo)(a, b)')[0].name == 'foo'
  assert split_declarator('(&&foo)(a, b)')[0].qname == 'foo'

  assert split_declarator('A::foo(a)')[0].name == 'foo'
  assert split_declarator('A::foo(a)')[0].qname == 'A::foo'
  assert split_declarator('A::foo()')[0].name == 'foo'
  assert split_declarator('A::foo()')[0].qname == 'A::foo'
  assert split_declarator('(*A::foo)(a, b)')[0].name == 'foo'
  assert split_declarator('(*A::foo)(a, b)')[0].qname == 'A::foo'
  assert split_declarator('(&&A::foo)(a, b)')[0].name == 'foo'
  assert split_declarator('(&&A::foo)(a, b)')[0].qname == 'A::foo'

def test_split_decltype_specifier():
  assert split_decltype_specifier('decltype(a->b) c') == (decltype_specifier('a->b'), 'c')
  assert split_decltype_specifier('decltype(auto) c') == (None, 'decltype(auto) c')


def test_split_class_or_computed():
  assert split_class_or_computed('A') == (class_or_computed(nested_name_spec=None, istemplate=False, tname='A'), '')
  assert split_class_or_computed('A::B b') == (class_or_computed(nested_name_spec=scope_list(names=['A']), istemplate=False, tname='B'), 'b')
  assert split_class_or_computed('A::template B<T> b') == (class_or_computed(nested_name_spec=scope_list(names=['A']), istemplate=True, tname=simple_template_id(name='B', args='T')), 'b')

def test_split_base_clause():
  assert split_base_clause(': A b') == (base_clause(base_specifiers=[base_specifier(attr=None, access_spec=None, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='A'))]), 'b')
  assert split_base_clause(': public A, private B<T> b') == (base_clause(base_specifiers=[base_specifier(attr=None, access_spec='public',  class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='A')), base_specifier(attr=None, access_spec='private', class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname=simple_template_id(name='B', args='T')))]), 'b')

def test_split_class_specifier():
  assert split_class_specifier('class A {} b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=None, member_specs=''), 'b')
  assert split_class_specifier('class A; b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=None, member_specs=None), 'b')
  assert split_class_specifier('class A final; b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=True, base_clause=None, member_specs=None), 'b')
  assert split_class_specifier('class A') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=None, member_specs=None), '')
  assert split_class_specifier('class A<T>') == (named_class_definition(key='class', attr=None, headname=simple_template_id(name='A', args='T'), isfinal=False, base_clause=None, member_specs=None), '')
  assert split_class_specifier('class B::A<T>') == (named_class_definition(key='class', attr=None, headname=(scope_list(names=['B']), simple_template_id(name='A', args='T')), isfinal=False, base_clause=None, member_specs=None), '')
  assert split_class_specifier('class A { int a; } b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=None, member_specs='int a;'), 'b')

  assert split_class_specifier('class A: B {} b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=base_clause(base_specifiers=[base_specifier(attr=None, access_spec=None, isvirtual=False, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='B'))]), member_specs=''), 'b')
  assert split_class_specifier('class A: virtual B {} b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=base_clause(base_specifiers=[base_specifier(attr=None, access_spec=None, isvirtual=True, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='B'))]), member_specs=''), 'b')

  assert split_class_specifier('class A: public B {} b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=base_clause(base_specifiers=[base_specifier(attr=None, access_spec='public', isvirtual=False, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='B'))]), member_specs=''), 'b')

  assert split_class_specifier('class A: public B, private C {} b') == (named_class_definition(key='class', attr=None, headname='A', isfinal=False, base_clause=base_clause(base_specifiers=[base_specifier(attr=None, access_spec='public', isvirtual=False, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='B')), base_specifier(attr=None, access_spec='private', isvirtual=False, class_or_computed=class_or_computed(nested_name_spec=None, istemplate=False, tname='C'))]), member_specs=''), 'b')

def test_split_enum_specifier():
  assert split_enum_specifier('enum A {a1, a2}') == (enum_specifier(key='enum', attr=None, headname='A', base=None, enumerator_list='a1, a2'), '')
  assert split_enum_specifier('enum A {}') == (enum_specifier(key='enum', attr=None, headname='A', base=None, enumerator_list=''), '')
  assert split_enum_specifier('enum A;') == (enum_specifier(key='enum', attr=None, headname='A', base=None, enumerator_list=None), '')
  assert split_enum_specifier('enum A: long long {}') == (enum_specifier(key='enum', attr=None, headname='A', base=enum_base(type_spec_seq=['long', 'long']), enumerator_list=''), '')

def test_split_type_specifier():
  assert split_type_specifier('int a') == ('int', 'a')
  assert split_type_specifier('foo a') == (declared_type_name(tname=unqualified_id_declarator(id='foo', attr=None)), 'a')
  assert split_type_specifier('A::foo a') == (declared_type_name(qualified_id_declarator(scope=scope_list(names=['A']), id='foo', attr=None)), 'a')
  assert split_type_specifier('foo<T> a') == (declared_type_name(unqualified_id_declarator(id=simple_template_id(name='foo', args='T'), attr=None)), 'a')

  assert split_type_specifier('class A a') == (elaborated_type_specifier(key='class', tname=unqualified_id_declarator(id='A', attr=None)), 'a')
  assert split_type_specifier('class B::A a') == (elaborated_type_specifier(key='class', tname=qualified_id_declarator(scope=scope_list(names=['B']), id='A', attr=None)), 'a')
  assert split_type_specifier('typename B::A a') == (typename_specifier(tname=qualified_id_declarator(scope=scope_list(names=['B']), id='A', attr=None)), 'a')
  assert split_type_specifier('volatile a') == ('volatile', 'a')
  assert split_type_specifier('decltype(t) a') == (decltype_specifier(expr='t'), 'a')
  assert split_type_specifier('C auto a') == (placeholder_type_specifier(type_constraint=unqualified_id_declarator(id='C', attr=None), auto='auto'), 'a')
  assert split_type_specifier('C decltype(auto) a') == (placeholder_type_specifier(type_constraint=unqualified_id_declarator(id='C', attr=None), auto='decltype(auto)'), 'a')
  assert split_type_specifier('A::C auto a') == (placeholder_type_specifier(type_constraint=qualified_id_declarator(scope=scope_list(names=['A']), id='C', attr=None), auto='auto'), 'a')
  assert split_type_specifier('auto a') == (placeholder_type_specifier(type_constraint=None, auto='auto'), 'a')
  assert split_type_specifier('decltype(auto) a') == (placeholder_type_specifier(type_constraint=None, auto='decltype(auto)'), 'a')

def test_split_type_specifier_sequence():
  assert split_type_specifier_sequence('long int *a') == (['long', 'int'], '*a')
  assert split_type_specifier_sequence('long int a') == (['long', 'int'], 'a')
  assert split_type_specifier_sequence('long int a;') == (['long', 'int'], 'a;')
  assert split_type_specifier_sequence('int a') == (['int'], 'a')
  assert split_type_specifier_sequence('int') == (['int'], '')
  assert split_type_specifier_sequence('long int') == (['long', 'int'], '')
  assert split_type_specifier_sequence('foo') == ([declared_type_name(unqualified_id_declarator(id='foo', attr=None))], '')
  assert split_type_specifier_sequence('foo a') == ([declared_type_name(unqualified_id_declarator(id='foo', attr=None))], 'a')

  assert split_type_specifier_sequence('const const') == (None, 'const const')
  assert split_type_specifier_sequence('int int') == (None, 'int int')
  assert split_type_specifier_sequence('long long') == (['long', 'long'], '')
  assert split_type_specifier_sequence('unsigned long long int') == (['unsigned', 'long', 'long', 'int'], '')

def test_split_type_declaration_sequence():
  assert split_declaration_specifier_sequence('long int *a') == (['long', 'int'], '*a')
  assert split_declaration_specifier_sequence('static long int *a') == (['static', 'long', 'int'], '*a')
  assert split_declaration_specifier_sequence('typedef struct A {} B b') == (typedef_declaration(type_specifer=named_class_definition(key='struct', attr=None, headname='A', isfinal=False, base_clause=None, member_specs=''), tname='B'), 'b')


def test_split_init_declarator():
  assert init_declarator.split('a = 1, b') == (init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(1)', content='1')), 'b')
  assert init_declarator.split('a = {1}, b') == (init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(2)', content='1')), 'b')
  assert init_declarator.split('a(1), b') == (init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(3)', content='1')), 'b')
  assert init_declarator.split('a{1}, b') == (init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(4)', content='1')), 'b')


def test_split_parameter_declaration():
  assert parameter_declaration.split('void') == ('void', '')
  assert parameter_declaration.split('int a') == (parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), '')
  assert parameter_declaration.split('this int a') == (parameter_declaration(kind='(2)', attr=None, decl_specifier_seq=['int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), '')
  assert parameter_declaration.split('int') == (parameter_declaration(kind='(4)', attr=None, decl_specifier_seq=['int'], declarator=None, initializer=None), '')
  assert parameter_declaration.split('this int') == (parameter_declaration(kind='(5)', attr=None, decl_specifier_seq=['int'], declarator=None, initializer=None), '')
  assert parameter_declaration.split('int =1') == (parameter_declaration(kind='(6)', attr=None, decl_specifier_seq=['int'], declarator=None, initializer='1'), '')

  assert parameter_declaration.split('static int a') == (parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['static', 'int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), '')
  assert parameter_declaration.split('const int a') == (parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['const', 'int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), '')
  assert parameter_declaration.split('static const int a') == (parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['static', 'const', 'int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), '')
  assert parameter_declaration.split('static int') == (parameter_declaration(kind='(4)', attr=None, decl_specifier_seq=['static', 'int'], declarator=None, initializer=None), '')
  assert parameter_declaration.split('const int') == (parameter_declaration(kind='(4)', attr=None, decl_specifier_seq=['const', 'int'], declarator=None, initializer=None), '')
  assert parameter_declaration.split('static const int') == (parameter_declaration(kind='(4)', attr=None, decl_specifier_seq=['static', 'const', 'int'], declarator=None, initializer=None), '')

def test_split_parameter_list():
  assert parameter_list.split('void') == (['void'], '')
  assert parameter_list.split('int a') == ([parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None)], '')
  assert parameter_list.split('int a, int b=1') == ([parameter_declaration(kind='(1)', attr=None, decl_specifier_seq=['int'], declarator=unqualified_id_declarator(id='a', attr=None), initializer=None), parameter_declaration(kind='(3)', attr=None, decl_specifier_seq=['int'], declarator=unqualified_id_declarator(id='b', attr=None), initializer='1')], '')

def test_simple_declaration():
  assert simple_declaration.split('int a;') == (simple_declaration(attr=None, decl_specifier_seq=['int'], init_declarator_list=[unqualified_id_declarator(id='a', attr=None)]), '')
  assert simple_declaration.split('const int a;') == (simple_declaration(attr=None, decl_specifier_seq=['const', 'int'], init_declarator_list=[unqualified_id_declarator(id='a', attr=None)]), '')
  assert simple_declaration.split('int a=1;') == (simple_declaration(attr=None, decl_specifier_seq=['int'], init_declarator_list=[init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(1)', content='1'))]), '')
  assert simple_declaration.split('int a, b;') == (simple_declaration(attr=None, decl_specifier_seq=['int'], init_declarator_list=[unqualified_id_declarator(id='a', attr=None), unqualified_id_declarator(id='b', attr=None)]), '')
  assert simple_declaration.split('int a=2, *b=nullptr;') == (simple_declaration(attr=None, decl_specifier_seq=['int'], init_declarator_list=[init_declarator(declarator=unqualified_id_declarator(id='a', attr=None), initializer=initializer(kind='(1)', content='2')), init_declarator(declarator=pointer_to_declarator(attr=None, cv=None, declarator=unqualified_id_declarator(id='b', attr=None)), initializer=initializer(kind='(1)', content='nullptr'))]), '')

  assert simple_declaration.split('struct A { int a; };') == ()
