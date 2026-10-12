"""Build/load unmodified BSD ROS algorithms, with an explicitly local ABI shim."""
import ctypes
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT/'third_party/mapfree_navigation'
HERE = Path(__file__).parent


def build():
    sources = [VENDOR/'navigation/navfn/src/navfn.cpp',
               VENDOR/'m-explore/explore/src/frontier_search.cpp', HERE/'bridge.cpp']
    inputs = sources + sorted((HERE/'shim').rglob('*.h')) + list(VENDOR.rglob('*.h'))
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()[:16]
    target = ROOT/'outputs/mapfree-public-navigation-build'/f'core-{digest}.so'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        command = ['c++','-std=c++17','-O2','-shared','-fPIC',
                   '-I'+str(HERE/'shim'),'-I'+str(VENDOR/'navigation/navfn/include'),
                   '-I'+str(VENDOR/'m-explore/explore/include'),*map(str,sources),'-o',str(target)]
        subprocess.run(command,check=True,capture_output=True,text=True)
    return target


class PublicCore:
    def __reduce__(self):
        # A stateless library handle cannot be pickled; reload the same hashed
        # native source on resume. All planner inputs/outputs live in Python.
        return type(self), ()

    def __init__(self):
        self.lib = ctypes.CDLL(str(build()))
        array = np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS')
        self.lib.ugrp_navfn.argtypes = [array,*([ctypes.c_int]*6),
            np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS'),ctypes.c_int]
        self.lib.ugrp_frontiers.argtypes = [array,ctypes.c_int,ctypes.c_int,*([ctypes.c_double]*5),
            np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS'),ctypes.c_int]

    def plan(self,costs,start,goal):
        out = np.zeros((costs.size,2),np.float32)
        n = self.lib.ugrp_navfn(np.ascontiguousarray(costs,np.uint8),costs.shape[1],costs.shape[0],
                                *map(int,start),*map(int,goal),out,len(out))
        if n<0:
            raise RuntimeError('NAVFN_OUTPUT_CAPACITY')
        return out[:n].astype(float)

    def frontiers(self,costs,origin,resolution,xy):
        out = np.zeros((costs.size,7),np.float64)
        n = self.lib.ugrp_frontiers(np.ascontiguousarray(costs,np.uint8),costs.shape[1],costs.shape[0],
                                   resolution,*map(float,origin),*map(float,xy),out,len(out))
        return out[:n]
