"""Recording-only launch experiment; qualified teacher and physics stay pinned.

Default OFF. Re-capture the exact control_steps kernels in one CUDA graph
rather than launching the existing graph_chunk graph repeatedly. This removes
host launches only. No timestep, solver setting, geometry, camera, command or
teacher decision changes. A fresh recording qualification is still required.
Reference: official MJWarp Performance Tuning / Graph capture and NVIDIA Warp
ScopedCapture documentation, inspected 2026-10-16. This is a measured candidate,
not a claim of deterministic trajectories (the pinned baseline is stochastic).
"""
import hashlib
import json
from pathlib import Path
import runpy
import sys

API = Path('/home/ugrp/ugrp-sim/src/0362037280c6cbc4677f70366db43b9892b23690')
QUALIFIED = Path('/home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c')

def main():
    if '--whole-control-graph-v1' not in sys.argv:
        raise ValueError('candidate is default OFF; explicit launch toggle required')
    sys.argv.remove('--whole-control-graph-v1')
    sys.path.insert(0,str(QUALIFIED/'scripts'))
    import warp_act_backend
    original = warp_act_backend.WarpTransport.initialize
    def initialize(self, *args, **kwargs):
        original(self,*args,**kwargs)
        import numpy as np
        wp=self.wp
        fields=('qpos','qvel','ctrl','time','tree_asleep','qacc_warmstart')
        before={k:getattr(self.wd,k).numpy().copy() for k in fields}
        original_chunk,original_repeats=self.graph_chunk,self.graph_repeats
        # Reusing the original graph as a child would be unsupported for CUDA
        # conditional nodes. Record the unchanged primitive calls directly.
        with wp.ScopedCapture() as capture:
            for _ in range(self.control_steps):
                wp.launch(self.command_kernel,dim=(self.n,self.m.nu),inputs=[self.tape,self.graph_tick,self.wd.ctrl])
                self.mjw.step(self.wm,self.wd)
                wp.launch(self.advance_kernel,dim=1,inputs=[self.graph_tick])
        state_equal={k:bool(np.array_equal(value,getattr(self.wd,k).numpy())) for k,value in before.items()}
        if not all(state_equal.values()):raise RuntimeError('graph capture advanced persistent simulation state')
        self.original_graph=self.graph  # retain allocation lifetime
        self.graph=capture.graph;self.graph_chunk=self.control_steps;self.graph_repeats=1
        self.capacities.update(graph_chunk=self.graph_chunk,graph_repeats=self.graph_repeats)
        audit=dict(mode='whole_control_graph_v1',original_chunk=original_chunk,original_repeats=original_repeats,
                   physics_steps=self.control_steps,period_s=.1,timestep_s=self.dt,state_equal_after_capture=state_equal,
                   teacher_source_unchanged=True,physics_parameters_changed=False,
                   adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (self.out/'launch-adapter.json').write_text(json.dumps(audit,indent=2)+'\n')
    warp_act_backend.WarpTransport.initialize=initialize
    sys.path.insert(0,str(API/'scripts'))
    try:runpy.run_path(str(API/'scripts/run_warp_act_record.py'),run_name='__main__')
    finally:warp_act_backend.WarpTransport.initialize=original

if __name__=='__main__':main()
