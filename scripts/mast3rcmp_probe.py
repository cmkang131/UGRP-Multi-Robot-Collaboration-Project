"""Passive per-frame ledger for the pinned upstream comparison, no truth reads."""
import dataclasses
import json
import os
from pathlib import Path
import time

import numpy as np
import torch
import lietorch


@dataclasses.dataclass
class WindowMsg:
    is_terminated: bool = False
    is_paused: bool = False
    next: bool = False
    C_conf_threshold: float = 1.5  # upstream visualization default, not a gate here


class Probe:
    def __init__(self):
        self.out = Path(os.environ['MAST3RCMP_OUTPUT'])
        self.out.mkdir(parents=True,exist_ok=False)
        self.inputs=json.loads(Path(os.environ['MAST3RCMP_INPUT_RECEIPT']).read_text())
        self.rows=[]
        self.references=[]
        self.start=time.perf_counter()
        torch.cuda.reset_peak_memory_stats()

    def begin(self,i,timestamp):
        torch.cuda.synchronize()
        self.i=i
        self.timer=time.perf_counter()

    def end(self,frame,status,keyframes,K):
        torch.cuda.synchronize()
        ok=status in ('initialized','tracked','relocalized')
        if ok and not torch.isfinite(frame.T_WC.data).all().item():
            status='nonfinite_pose'
            ok=False
        # Keep Sim(3) scale as well as rotation/translation for final graph warp.
        pose=frame.T_WC.data.detach().cpu().numpy().reshape(-1).tolist() if ok else None
        ref=len(keyframes)-1
        ref_pose=keyframes[ref].T_WC.data.detach().cpu().numpy().reshape(-1).tolist()
        self.references.append((ref,ref_pose))
        row=dict(index=self.i,t_sim_s=self.inputs['frames'][self.i]['t_sim_s'],status=status,
                 success=ok,pose_sim3_online=pose,seconds=time.perf_counter()-self.timer,
                 reason_category='none' if ok else status,
                 blocking_object='not_observed_offline_rgb',minimum_gap='not_measured_offline_rgb')
        self.rows.append(row)
        if self.i==0:
            np.savez_compressed(self.out/'initial-pointmap.npz',
                xyz=frame.X_canon.detach().cpu().numpy(),rgb=frame.uimg.numpy(),
                K=K.detach().cpu().numpy() if K is not None else np.empty(0),
                image_shape=frame.img_shape.detach().cpu().numpy())
        with (self.out/'frames-online.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n')

    def finish(self,keyframes):
        for row,(idx,old) in zip(self.rows,self.references):
            if row['success']:
                final=keyframes[idx].T_WC
                old=lietorch.Sim3(torch.tensor([old],device=final.data.device,dtype=final.data.dtype))
                online=lietorch.Sim3(torch.tensor([row['pose_sim3_online']],device=final.data.device,dtype=final.data.dtype))
                row['pose_sim3_final']=(final*old.inv()*online).data.cpu().numpy().reshape(-1).tolist()
        n=self.inputs['all_frames']
        # Every omitted/unprocessed frame remains an explicit failure, never zero motion.
        for i in range(len(self.rows),n):
            self.rows.append(dict(index=i,t_sim_s=self.inputs['frames'][i]['t_sim_s'],
                status='unprocessed',success=False,reason_category='unprocessed',
                blocking_object='not_observed_offline_rgb',minimum_gap='not_measured_offline_rgb'))
        (self.out/'trajectory.json').write_text(json.dumps(dict(frames=self.rows),indent=2)+'\n')
        counts={s:sum(r['status']==s for r in self.rows) for s in sorted({r['status'] for r in self.rows})}
        summary=dict(total_frames=n,success=sum(r['success'] for r in self.rows),
            failures=sum(not r['success'] for r in self.rows),status_counts=counts,
            initialized_not_motion_measurement=counts.get('initialized',0),
            torch_max_allocated_bytes=torch.cuda.max_memory_allocated(),
            torch_max_reserved_bytes=torch.cuda.max_memory_reserved(),
            frame_seconds=[r.get('seconds') for r in self.rows],
            processing_seconds=time.perf_counter()-self.start,
            truth_reads=0,command_reads=0,top_reads=0,
            trajectory_scope='online_and_final_reference_keyframe_corrected_dense_poses')
        (self.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
