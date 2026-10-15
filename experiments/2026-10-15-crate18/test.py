"""Sequential related tests, no Mac MuJoCo stepping/forward/render.

The unmodified upstream test imports release adapters absent from crate17.
Run that test on its exact dependency snapshot, replacing only settle_pulse
with this checkout's byte-identical copy; crate integration runs separately.
"""
from pathlib import Path
import importlib.util
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
PYTHON=sys.executable
if '--child' not in sys.argv:
    for kind in ('common','crate'):
        subprocess.run([PYTHON,__file__,'--child',kind,*sys.argv[1:]],check=True)
    raise SystemExit(0)
kind=sys.argv[sys.argv.index('--child')+1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
if kind=='common':
    ref=ROOT/'outputs/crate18/release20-reference'
    if not ref.is_dir():
        ref.mkdir(parents=True)
        a=subprocess.Popen(['git','archive','097e53da','sim','harness','scripts','tests'],cwd=ROOT,stdout=subprocess.PIPE)
        subprocess.run(['tar','-x','-C',str(ref)],stdin=a.stdout,check=True)
        if a.wait(): raise RuntimeError('reference snapshot missing')
    sys.path.insert(0,str(ref))
    import sim
    spec=importlib.util.spec_from_file_location('sim.settle_pulse',ROOT/'sim/settle_pulse.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
import mujoco

def forbidden(*a,**k):raise AssertionError('Mac physics/render forbidden')
for n in ('mj_step','mj_step1','mj_step2','mj_forward','mj_inverse','Renderer','mjr_render'):setattr(mujoco,n,forbidden)
import pytest
files=['experiments/2026-10-15-crate18/release20-tests/test_settle_pulse.py'] if kind=='common' else ['tests/test_crate18.py']
raise SystemExit(pytest.main(['-q',*files]))
