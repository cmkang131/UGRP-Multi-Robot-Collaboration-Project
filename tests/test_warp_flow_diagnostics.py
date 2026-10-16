"""No MuJoCo/Warp imports: verify dispatch preserves the physics clock."""
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace as NS
import importlib
import numpy as np
import pytest


@pytest.mark.parametrize('fail',[False,True])
def test_verified_dispatch_never_captures_and_restores_global_state(monkeypatch,fail):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    backend=importlib.import_module('warp_act_backend')
    events=[]
    config=NS(verify_cuda=False)
    def launch(kernel,**kwargs):
        assert config.verify_cuda
        events.append(kernel)
    def physics(*args):
        assert config.verify_cuda
        events.append('physics')
        if fail:raise RuntimeError('first failing launch')
    def render(*args):
        assert not config.verify_cuda
        events.append('render')
    array=lambda x:NS(numpy=lambda:np.array(x))
    h=backend.WarpTransport.__new__(backend.WarpTransport)
    h.wp=NS(config=config,launch=launch,synchronize=lambda:None,
        capture_launch=lambda *a:pytest.fail('verification cannot use a CUDA graph'))
    h.mjw=NS(step=physics)
    h.wm=object();h.m=NS(nu=1);h.n=1;h.tape=object()
    h.graph_tick=NS(zero_=lambda:None);h.command_kernel='command';h.advance_kernel='advance'
    h.control_steps,h.graph_chunk,h.graph_repeats=backend.physics_schedule(.1,.00025)
    h.verify_cuda_v1=True;h.workspace_trace_v1=False
    h.prepare_solo_commands=lambda *a:None;h.seconds=defaultdict(float)
    h.sync_render=render;h.tick=0;h.solver_samples=[];h.dof_tree=np.array([0])
    h.wd=NS(ctrl=object(),solver_niter=array([1]),tree_awake=array([[1]]),overflow=array([0]))
    if fail:
        with pytest.raises(RuntimeError,match='first failing launch'):h.step([],np.array([True]))
        assert events==['command','physics']
    else:
        h.step([],np.array([True]))
        assert events==['command','physics','advance']*400+['render']
        assert h.tick==1
    assert not config.verify_cuda
