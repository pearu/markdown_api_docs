
from markdown_api_docs.spanstr import spanstr

def test_ctor():
    s = spanstr('ABCD')
    assert str(s) == 'ABCD'
    assert repr(s) == "spanstr('ABCD', span=(0, 4))"

def test_lstrip():
    assert str(spanstr('ABCD').lstrip()) == 'ABCD'
    assert str(spanstr('  ABCD').lstrip()) == 'ABCD'
    assert str(spanstr('  ABCD  ').lstrip()) == 'ABCD  '

def test_removeprefix():
    assert str(spanstr('ABCD').removeprefix('')) == 'ABCD'
    assert str(spanstr('ABCD').removeprefix('AB')) == 'CD'


def test_split():
    assert list(map(str, spanstr('ABCD').split())) == ['ABCD']
    assert list(map(str, spanstr('AB CD').split())) == ['AB', 'CD']
    assert list(map(str, spanstr('AB   CD').split())) == ['AB', 'CD']
    assert list(map(str, spanstr(' AB   CD').split())) == ['AB', 'CD']
    assert list(map(str, spanstr(' AB   CD  ').split())) == ['AB', 'CD']
    assert list(map(str, spanstr('AB,CD').split(','))) == ['AB', 'CD']
    assert list(map(str, spanstr('AB, CD').split(','))) == ['AB', ' CD']
    assert list(map(str, spanstr('AB,, CD').split(','))) == ['AB', '', ' CD']
    assert list(map(str, spanstr('ABCD').split('X'))) == ['ABCD']
    assert list(map(str, spanstr('ABCD').split('BC'))) == ['A', 'D']

def test_splitlines():
    assert list(map(str, spanstr('ABCD').splitlines())) == ['ABCD']
    assert list(map(str, spanstr('AB\nCD').splitlines())) == ['AB', 'CD']

    assert list(map(str, spanstr('ab c\n\nde fg\rkl\r\n').splitlines())) == ['ab c', '', 'de fg', 'kl']
    assert list(map(str, spanstr('ab c\n\nde fg\rkl\r\n').splitlines(keepends=True))) == ['ab c\n', '\n', 'de fg\r', 'kl\r\n']

def test_strip():
    assert str(spanstr('ABCD').strip()) == 'ABCD'
    assert str(spanstr('  ABCD ').strip()) == 'ABCD'
    assert str(spanstr('www.example.com').strip('cmowz.')) == 'example'

def test_getitem():
    assert str(spanstr('ABCD')[0]) == 'A'
    assert str(spanstr('ABCD')[-1]) == 'D'
    assert str(spanstr('ABCD')[-2]) == 'C'


    assert str(spanstr('ABCD')[:1]) == 'A'
    assert str(spanstr('ABCD')[:2]) == 'AB'
    assert str(spanstr('ABCD')[:-1]) == 'ABC'
    assert str(spanstr('ABCD')[-1:]) == 'D'

    assert str(spanstr('ABCD')[-2:]) == 'CD'

    assert str(spanstr('ABCD')[1:1]) == ''
    assert str(spanstr('ABCD')[1:2]) == 'B'
    assert str(spanstr('ABCD')[1:3]) == 'BC'
    assert str(spanstr('ABCD')[0:3][:]) == 'ABC'
    assert str(spanstr('ABCD')[0:3][:4]) == 'ABC'
