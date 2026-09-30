"""Pytest plugin for T03's local no-physics/no-network boundary."""
import importlib.abc
import socket
import sys


class NoPhysics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch'):
            raise RuntimeError(f'T03 offline guard: {fullname} is forbidden')


def forbidden(*args, **kwargs):
    raise RuntimeError('T03 offline guard: network is forbidden')


sys.meta_path.insert(0, NoPhysics())
socket.socket.connect = forbidden
socket.create_connection = forbidden
