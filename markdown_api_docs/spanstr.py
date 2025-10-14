
class spanstr:
    """Provides a string that is a slice of a storage object.

    The aim of providing the object is to preserve the location
    information of sliced strings with respect to the start of the
    storage object.

    The storage object is typically str instance but could be any
    bytes-like object.

    String methods that construct a string with new content
    (e.g. padding, etc), are not supported.
    """
    def __init__(self, storage, span=None):
        if span is None:
            span = (0, len(storage))
        self.span = span
        self.storage = storage

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return f'{type(self).__name__}({self.data!r}, span={self.span})@{self.lineno}'

    @property
    def lineno(self):
        return self.storage[:self.span[0]].count('\n') + 1

    @property
    def start(self):
        i = self.storage[:self.span[0]].rfind('\n')
        if i == -1:
            return self.span[0] + 1
        return self.span[0] - i

    @property
    def end(self):
        return self.start + self.span[1] - self.span[0]

    def tostring(self, with_location=True, compress=-1):
        s = str(self)
        if compress > 0 and len(s) > compress:
            s = s[:compress//2] + '......' + s[-compress//2:]
        if with_location:
            return f'{s!r}@{self.lineno}:{self.start}..{self.end}'
        return s
    
    @property
    def data(self):
        return self.storage[slice(*self.span)]
    
    def capitalize(self): return type(self)(self.storage.capitalize(), self.span)
    def casefold(self): return type(self)(self.storage.casefold(), self.span)
    def center(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.center is not supported')
    def count(self, *args, **kwargs): return self.data.count(*args, **kwargs)
    def encode(self, *args, **kwargs): return type(self)(self.storage.encode(*args, **kwargs), self.span)
    def endswith(self, *args, **kwargs): return self.data.endswith(*args, **kwargs)
    def expandtabs(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.expandtabs is not supported')
    def find(self, *args, **kwargs): return self.data.find(*args, **kwargs)
    def format(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.format is not supported')
    def format_map(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.format_map is not supported')
    def index(self, *args, **kwargs): return self.data.index(*args, **kwargs)
    def isalnum(self, *args, **kwargs): return self.data.isalnum(*args, **kwargs)
    def isalpha(self, *args, **kwargs): return self.data.isalpha(*args, **kwargs)
    def isascii(self, *args, **kwargs): return self.data.isascii(*args, **kwargs)
    def isdecimal(self, *args, **kwargs): return self.data.isdecimal(*args, **kwargs)
    def isdigit(self, *args, **kwargs): return self.data.isdigit(*args, **kwargs)
    def isidentifier(self, *args, **kwargs): return self.data.isidentifier(*args, **kwargs)
    def islower(self, *args, **kwargs): return self.data.islower(*args, **kwargs)
    def isnumeric(self, *args, **kwargs): return self.data.isnumeric(*args, **kwargs)

    def isprintable(self, *args, **kwargs): return self.data.isprintable(*args, **kwargs)
    def isspace(self, *args, **kwargs): return self.data.isspace(*args, **kwargs)
    def istitle(self, *args, **kwargs): return self.data.istitle(*args, **kwargs)
    def isupper(self, *args, **kwargs): return self.data.isupper(*args, **kwargs)
    def join(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.join is not supported')
    def ljust(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.ljust is not supported')
    def lower(self, *args, **kwargs): return type(self)(self.storage.lower(*args, **kwargs), self.span)
    def lstrip(self, *args, **kwargs):
        d = self.data
        s = d.lstrip(*args, **kwargs)
        return type(self)(self.storage, span=(self.span[0] + (len(d) - len(s)), self.span[1]))
    def maketrans(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.maketrans is not supported')
    def partition(self, *args, **kwargs):
        t = self.data.partition(*args, **kwargs)
        l1, l2, l3 = map(len(t))
        return (
            type(self)(self.storage, span=(self.span[0], self.span[0] + l1)),
            type(self)(self.storage, span=(self.span[0] + l1, self.span[0] + l1 + l2)),
            type(self)(self.storage, span=(self.span[0] + l1 + l2, self.span[1])),
            )
    def removeprefix(self, *args, **kwargs):
        r = self.data.removeprefix(*args, **kwargs)
        return type(self)(self.storage, span=(self.span[0] + (len(self.data) - len(r)), self.span[1]))
    def removesuffix(self, *args, **kwargs):
        r = self.data.removesuffix(*args, **kwargs)
        return type(self)(self.storage, span=(self.span[0], self.span[1] - (len(self.data) - len(r))))
    def replace(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.replace is not supported')
    def rfind(self, *args, **kwargs): return self.data.rfind(*args, **kwargs)
    def rindex(self, *args, **kwargs): return self.data.rindex(*args, **kwargs)
    def rjust(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.rjust is not supported')
    def rpartition(self, *args, **kwargs):
        t = self.data.rpartition(*args, **kwargs)
        l1, l2, l3 = map(len(t))
        return (
            type(self)(self.storage, span=(self.span[0], self.span[0] + l1)),
            type(self)(self.storage, span=(self.span[0] + l1, self.span[0] + l1 + l2)),
            type(self)(self.storage, span=(self.span[0] + l1 + l2, self.span[1])),
            )
    def rstrip(self, *args, **kwargs):
        d = self.data
        s = d.rstrip(*args, **kwargs)
        return type(self)(self.storage, span=(self.span[0], self.span[1] - (len(d) - len(s))))
    def split(self, sep=None, maxsplit=-1):
        d = self.data
        lst = []
        for s in d.split(sep=sep, maxsplit=maxsplit):
            if not lst:
                start = d.find(s, 0)
                lst.append(type(self)(self.storage, span=(start, start + len(s))))
            else:
                start = d.find(s, lst[-1].span[1])
                lst.append(type(self)(self.storage, span=(start, start + len(s))))
        return lst
    def splitlines(self, keepends=False):
        d = self.data
        lst = []
        for s in d.splitlines(keepends=keepends):
            if not lst:
                start = d.find(s, 0)
                lst.append(type(self)(self.storage, span=(start, start + len(s))))
            else:
                start = d.find(s, lst[-1].span[1])
                lst.append(type(self)(self.storage, span=(start, start + len(s))))
        return lst

    def startswith(self, *args, **kwargs): return self.data.startswith(*args, **kwargs)
    def strip(self, chars=None):
        d = self.data
        s = d.strip(chars)
        start = d.find(s)
        return type(self)(self.storage, span=(self.span[0] + start, self.span[0] + start + len(s)))

    def swapcase(self, *args, **kwargs): return type(self)(self.storage.swapcase(*args, **kwargs), self.span)
    def title(self, *args, **kwargs): return type(self)(self.storage.title(*args, **kwargs), self.span)
    def translate(self, *args, **kwargs): return type(self)(self.storage.translate(*args, **kwargs), self.span)
    def upper(self, *args, **kwargs): return type(self)(self.storage.upper(*args, **kwargs), self.span)
    def zfill(self, *args, **kwargs):
        raise RuntimeError(f'{type(self).__name__}.zfill is not supported')

    def __bytes__(self): return bytes(self.data)
    def __lt__(self, other): return self.data < other
    def __le__(self, other): return self.data <= other
    def __gt__(self, other): return self.data > other
    def __ge__(self, other): return self.data >= other
    def __eq__(self, other): return self.data == other
    def __ne__(self, other): return self.data != other
    def __bool__(self): return bool(self.data)
    def __hash__(self): return hash(self.data)
    def __len__(self): return len(self.data)

    def __getitem__(self, key):
        if isinstance(key, int):
            while key < 0:
                key += len(self)
            if key >= len(self):
                raise IndexError('span string index out of range')
            return type(self)(self.storage, span=(self.span[0] + key, self.span[0] + key +1))
        elif isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step != 1:
                # support requires introducing step/stride to span
                raise RuntimeError(f'{type(self).__name__}.__getitem__ on slice with step(={step}) != 1 is not supported')
            return type(self)(self.storage, span=(self.span[0] + start, self.span[0] + stop))
        else:
            raise TypeError(type(key))

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]
    def __reversed__(self):
        raise RuntimeError(f'{type(self).__name__}.__reverse__ is not supported')
    def __contains__(self, item):
        return item in self.data

    def __add__(self, other):
        if self.span[0] == 0 and self.span[1] == len(self.storage):
          return type(self)(self.storage + other)
        return NotImplemented

    def __iadd__(self, other):
        if type(other) is type(self) and self.storage == other.storage:
          if self.span[1] == other.span[0]:
            return type(self)(self.storage, span=(self.span[0], other.span[1]))
        return NotImplemented
