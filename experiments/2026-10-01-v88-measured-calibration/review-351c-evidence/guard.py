import os, socket, sys

def forbidden(*args, **kwargs):
    raise RuntimeError('review forbids physics/render/network/model calls')
socket.socket.connect = forbidden
for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
    sys.modules[name] = None

def audit(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if path == '/Users/changmin/projects/ugrp/outputs' or path.startswith('/Users/changmin/projects/ugrp/outputs/'):
            raise RuntimeError('review forbids shared outputs access')
sys.addaudithook(audit)
