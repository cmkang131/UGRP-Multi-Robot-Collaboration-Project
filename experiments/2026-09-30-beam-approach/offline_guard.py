"""pytest plugin: refuse simulator/model imports and network access, no host lock."""
import importlib.abc
import sys
import socket

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'torch', 'openai', 'anthropic', 'google'}:
            raise AssertionError('No physics/model import: ' + fullname)

sys.meta_path.insert(0, Block())

def refuse(*args, **kwargs):
    raise AssertionError('No network calls')

socket.socket.connect = refuse
