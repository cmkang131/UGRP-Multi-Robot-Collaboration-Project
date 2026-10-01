"""Private dependency injection for frozen, pure functions.

No module globals, imported classes, files or process import hooks are patched.
The original code object/defaults/closure are reused with a private globals
dictionary. Call sites name every replaced dependency; bundle hashes cover
both this adapter and the original function's source.
"""
from types import FunctionType


def bind(function, **dependencies):
    if not dependencies.keys() <= function.__globals__.keys():
        raise ValueError('cannot bind an undeclared frozen dependency')
    result = FunctionType(function.__code__, {**function.__globals__, **dependencies},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result
