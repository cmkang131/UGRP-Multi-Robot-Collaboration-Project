"""Conservative v2 import analysis; legacy closure/seals remain byte-identical.

Search the repository and every declared script directory, retaining ALL local
resolutions (not just the first match). Wildcard packages pin their whole Python
subtree, including computed __all__. Never import inspected candidate code.
"""
from __future__ import annotations

import ast
from pathlib import Path


def source_closure(root, paths, *, modules=(), script_dirs=()):
    root = Path(root).resolve()
    search = sorted({'', *script_dirs})
    found, pending = set(), []

    def add_path(path):
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError(f'missing or nonlocal source: {path}')
        name = path.relative_to(root).as_posix()
        if name not in found:
            found.add(name)
            pending.append(name)

    def add_module(module, *, required=False, wildcard=False, absolute=True):
        parts = module.split('.')
        # importlib accepts dated/hyphenated package directories even though
        # they cannot appear in an ``import`` statement. Keep separators and
        # empty components forbidden; add_path still enforces the root boundary.
        if not all(part and ('_' + part.replace('-', '_')).isidentifier() for part in parts):
            raise ValueError(f'invalid module: {module!r}')
        exists = False
        for prefix in search if absolute else ['']:
            base = root / prefix
            stem = base.joinpath(*parts)
            for candidate in (stem.with_suffix('.py'), stem / '__init__.py'):
                if candidate.is_file():
                    exists = True
                    add_path(candidate)
            # Namespace packages need not have __init__.py.
            exists |= stem.is_dir()
            for index in range(1, len(parts) + 1):
                init = base.joinpath(*parts[:index], '__init__.py')
                if init.is_file():
                    add_path(init)
            if wildcard and stem.is_dir():
                if not stem.resolve().is_relative_to(root):
                    raise ValueError(f'nonlocal wildcard package: {module}')
                # Includes siblings even if __all__ is assembled at runtime.
                for candidate in sorted(stem.rglob('*.py')):
                    add_path(candidate)
        if required and not exists:
            raise ValueError(f'missing local module: {module}')

    for name in paths:
        add_path(root / name)
        if name.endswith('.py'):
            add_module(name.removesuffix('/__init__.py').removesuffix('.py').replace('/', '.'),
                       absolute=False)
    for module in modules:
        add_module(module, required=True)
    while pending:
        name = pending.pop()
        if not name.endswith('.py'):
            continue
        tree = ast.parse((root / name).read_bytes(), filename=name)
        package = name.removesuffix('/__init__.py').removesuffix('.py').split('/')
        if not name.endswith('/__init__.py'):
            package = package[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level > len(package):
                        raise ValueError(f'import outside package: {name}')
                    base = package[:len(package) - node.level + 1]
                    if node.module:
                        base += node.module.split('.')
                    module = '.'.join(base)
                else:
                    module = node.module or ''
                add_module(module, absolute=not node.level,
                           wildcard=any(a.name == '*' for a in node.names))
                for alias in node.names:
                    if alias.name != '*':
                        add_module(module + '.' + alias.name, absolute=not node.level)
    return tuple(sorted(found))


def dynamic_calls(path):
    """Follow loader aliases conservatively; reject loader references that escape.

    No control-flow pruning or alias overwrite: every possible loader binding is
    retained. A per-file declaration covers one unresolved direct call only; it
    cannot authorize an escaped loader or silently cover a second unknown call.
    """
    tree = ast.parse(path.read_bytes(), filename=str(path))
    nodes = list(ast.walk(tree))
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    bindings = {'__import__': {'builtin'}}

    def bind(name, kinds):
        previous = bindings.setdefault(name, set())
        added = kinds - previous
        previous.update(kinds)
        return bool(added)

    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in {'importlib', 'builtins'} and not ('.' in alias.name and alias.asname):
                    module = alias.name.split('.')[0]
                    bind(alias.asname or module, {'module:' + module})
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if node.module == 'importlib' and alias.name == 'import_module':
                    bind(alias.asname or alias.name, {'import_module'})
                if node.module == 'builtins' and alias.name == '__import__':
                    bind(alias.asname or alias.name, {'builtin'})
                if node.module in {'importlib', 'builtins'} and alias.name == '*':
                    raise ValueError(f'unresolved dynamic loader wildcard: {path}')

    def kinds(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id, set())
        if isinstance(node, ast.NamedExpr):
            return kinds(node.value)
        if isinstance(node, ast.Attribute):
            owner, attr = kinds(node.value), node.attr
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == 'getattr' and len(node.args) >= 2):
            owner = kinds(node.args[0])
            key = node.args[1]
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                if owner & {'module:importlib', 'module:builtins'}:
                    raise ValueError(f'unresolved dynamic loader getattr: {path}')
                return set()
            attr = key.value
        elif isinstance(node, ast.Call) and kinds(node.func) & {'import_module', 'builtin'}:
            arg = node.args[0] if node.args else next(
                (k.value for k in node.keywords if k.arg == 'name'), None)
            if isinstance(arg, ast.Constant) and arg.value in ('importlib', 'builtins'):
                return {'module:' + arg.value}
            return set()
        else:
            return set()
        if owner & {'module:importlib', 'module:builtins'} and attr in {'__dict__', '__getattribute__'}:
            raise ValueError(f'unresolved dynamic loader introspection: {path}')
        result = set()
        if 'module:importlib' in owner and attr == 'import_module':
            result.add('import_module')
        if 'module:builtins' in owner and attr == '__import__':
            result.add('builtin')
        return result

    assignments = [n for n in nodes if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr))]
    while True:
        changed = False
        for node in assignments:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = kinds(node.value)
            if value:
                if any(not isinstance(target, ast.Name) for target in targets):
                    raise ValueError(f'escaped dynamic loader assignment: {path}')
                for target in targets:
                    changed |= bind(target.id, value)
        if not changed:
            break

    calls = []
    for node in nodes:
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            continue
        value = kinds(node)
        parent = parents.get(node)
        if value & {'import_module', 'builtin'}:
            if isinstance(parent, ast.Call) and parent.func is node:
                arg = parent.args[0] if parent.args else next(
                    (k.value for k in parent.keywords if k.arg == 'name'), None)
                module = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
                # Nontrivial __import__ fromlist/level requires reviewed coverage.
                extra = 'builtin' in value and (len(parent.args) > 1 or any(
                    k.arg != 'name' for k in parent.keywords))
                calls.append(None if extra else module)
                # Preserve even the constant package when fromlist is unresolved.
                if extra and module is not None:
                    calls.append(module)
            elif not (parent in assignments and parent.value is node):
                raise ValueError(f'escaped dynamic loader reference: {path}')
        elif value & {'module:importlib', 'module:builtins'}:
            # Passing/storing the module could hide its loader behind an object.
            allowed = (isinstance(parent, ast.Attribute) and parent.value is node
                       and parent.attr not in {'__dict__', '__getattribute__'})
            allowed |= parent in assignments and parent.value is node
            allowed |= (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name)
                        and parent.func.id == 'getattr' and parent.args and parent.args[0] is node)
            if not allowed:
                raise ValueError(f'escaped dynamic loader module: {path}')
    if sum(module is None or module.startswith('.') for module in calls) > 1:
        raise ValueError(f'multiple unresolved dynamic imports require separate reviewed wrappers: {path}')
    return calls
