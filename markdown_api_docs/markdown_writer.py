import os


api_doc_template = '''
# {directory} Public C++ API Documentation[^mad]

[^mad]: This file is generated using [markdown_api_docs](https://github.com/pearu/markdown_api_docs) software.

## Summary

{table_of_content}

---

{function_content}

{struct_content}
'''

struct_doc_template = '''
## <div id="{label}">{namespace_name} {Kind} Reference{src}</div>

{doc}

### Public Methods

{table}

{content}
'''

function_doc_template = '''
## <div id="{label}">{scope_name} {Kind} Reference{src}</div>

{doc}

*Signature:*
{signature}
'''

method_doc_template = '''
#### <div id="{label}">{scope_name} {Kind} Reference{src}</div>

{doc}

*Signature:*
{signature}
'''

def markdown_writer(node):
  if node.kind == 'directory':
    assert os.path.isdir(node.spec), node.spec

    table_of_content = []
    function_content = []
    struct_content = []

    lst = []
    for f in node.collect('function'):
      if f.parent.kind in {'struct', 'class'}:
        continue
      d = markdown_writer(f)
      if d:
        function_content.append(d)
        lst.append(f'[{f.name_prefix}{f.name}](#{f.label})')

    if lst:
      table_of_content.append('*Functions:*')
      table_of_content.append('> ' + ', '.join(lst))

    lst = []
    for f in node.collect('class', 'struct'):
      d = markdown_writer(f)
      if d:
        struct_content.append(d)
        lst.append(f'[{f.name_prefix}{f.name}](#{f.label})')
    if lst:
      if table_of_content:
        table_of_content.append('')
      table_of_content.append('*Classes:*')
      table_of_content.append('> ' + ', '.join(lst))

    lst = []
    for d in node.root.collect('directory'):
      if os.path.dirname(d.path) == node.path:
        p = os.path.relpath(d.path, node.path)
        lst.append(f'[{p}]({p})')
    if lst:
      if table_of_content:
        table_of_content.append('')
      table_of_content.append('*Sub-directories:*')
      table_of_content.append('> ' + ', '.join(lst))
    
      
    doc = api_doc_template.format(
        directory = node.path,
        table_of_content = '\n'.join(table_of_content),
        function_content = '\n'.join(function_content),
        struct_content = '\n'.join(struct_content)
    )

    return doc.lstrip()

  elif node.kind in {'class', 'struct'}:
    lines = ['|   |   |']
    lines.append('|--:|:--|')
    member_docs = []
    for f in node.collect('function', level=1):
      type_prefix = f.type_prefix
      type_prefix = f'<sup>`{type_prefix}`</sup>' if type_prefix else ''
      args = f.data['arguments'][1:-1]
      args = f'` {args} `' if args else ''
      lines.append(f'| {type_prefix}`{f.rtype}` | **[{f.name}](#{f.label})** ({args}) |')
      d = markdown_writer(f)
      if d:
        member_docs.append(d)

    table = '\n'.join(lines) if len(lines) > 2 else ''
    d = node.comment_text
    d = d if d else ''
    src = f' ([source]({node.source_ref}))'

    bases = []
    for basename, access in node.data['bases'].items():
      if access == 'public':
        base = node.find(node.kind, basename, scope=node.data.get('scope'))
        if base is not None:
          if base.directory.spec != node.directory.spec:
            p = os.path.relpath(base.directory.spec, node.directory.spec)
            p = os.path.join(p, node.root.params.get('docfile', 'API.md'))
          else:
            p = ''
          bases.append(f'[{base.name_prefix}{base.name}]({p}#{base.label})')
        else:
          bases.append(basename)

    if bases:
      d += '\n\n*Base Classes*:\n'
      d += '>  ' + ', '.join(bases)
        
    doc = struct_doc_template.format(
        label=node.label,
        Kind=node.kind.title(),
        namespace_name = '::'.join([node.namespace, node.name]),
        doc=d,
        table=table or f'No public methods declared in {node.name}.',
        content='\n'.join(member_docs),
        src=src,
    )

    return doc.lstrip()

  elif node.kind == 'function':
    d = node.comment_text
    d = d if d else ''

    lines = []
    if node.ttype:
      lines.append(f'  <sup>` {node.ttype} `</sup>')

    if len(node.data['args']) == 0:
      lines.append(f'  ` {node.rtype} ` **{node.name}** ( )')
    else:
      lines.append(f'  ` {node.rtype} ` **{node.name}** (')

    print(f'{node.spec=}')
    mx = max([len(atype) for atype, _, _ in node.data['args']] or [0])
    mx_name = max([len(aname or '') for _, aname, _ in node.data['args']] or [0])
    single_line_width = (mx + mx_name) * len(node.data['args'])
    
    for i, (atype, aname, ainit) in enumerate(node.data['args']):
      aname = aname if aname else ''
      s = ')' if i == len(node.data['args']) - 1 else ','
      init = ' = ` {ainit} `' if ainit else ''
      if single_line_width < 80:
          lines.append(f'` {atype} ` {aname}{init} {s}')
      else:
        lines.append(f'\n  `        {{:{mx}}} ` {aname}{init} {s}'.format(atype))


        
    tmpl = method_doc_template if node.parent.kind in {'struct', 'class'} else function_doc_template
    Kind = 'Method' if node.parent.kind in {'struct', 'class'} else node.kind.title()
    src = f' ([source]({node.source_ref}))'
    doc = tmpl.format(
        label=node.label,
        Kind=Kind,
        scope_name = node.name_prefix + node.name,
        signature='>  ' + ''.join(lines),
        doc=node.comment_text or '',
        src=src
    )
    return doc.lstrip()
  else:
    raise NotImplementedError(node.kind)
