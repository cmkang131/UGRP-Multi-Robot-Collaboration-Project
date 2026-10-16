"""Static local Python import closure; never import/execute the inspected code.

Include function-local imports, relative imports and package initializers.
Configuration-selected modules must be supplied as explicit entry points.
Third-party packages are identified by the run's environment, not copied here.
"""
from __future__ import annotations

import ast
from pathlib import Path


def source_closure(root: Path, paths, *, modules=()) -> tuple[str, ...]:
    root = Path(root).resolve()
    found, pending = set(), []

    def add_path(name):
        path = root / name
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError(f'missing or nonlocal source: {name}')
        if name not in found:
            found.add(name)
            pending.append(name)

    def add_module(module, *, required=False):
        parts = module.split('.')
        if not all(part.isidentifier() for part in parts):
            raise ValueError(f'invalid module: {module!r}')
        candidates = ('/'.join(parts) + '.py', '/'.join(parts) + '/__init__.py')
        existing = [name for name in candidates if (root / name).is_file()]
        if required and not existing:
            raise ValueError(f'missing local module: {module}')
        # A namespace package may have no initializer of its own.
        for index in range(1, len(parts) + 1):
            name = '/'.join(parts[:index]) + '/__init__.py'
            if (root / name).is_file():
                add_path(name)
        for name in existing:
            add_path(name)

    for name in paths:
        add_path(name)
        if name.endswith('.py'):
            add_module(name.removesuffix('/__init__.py').removesuffix('.py').replace('/', '.'))
    for module in modules:
        add_module(module, required=True)
    while pending:
        name = pending.pop()
        if not name.endswith('.py'):
            continue
        tree = ast.parse((root / name).read_text(), filename=name)
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
                add_module(module)
                for alias in node.names:
                    if alias.name != '*':
                        add_module(module + '.' + alias.name)
    return tuple(sorted(found))
