"""Summarize completed evaluation artifacts; no new prediction or fitting."""
from pathlib import Path
import json
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'code'))
import kinematics_audit as a
sys.path.insert(0,str(a.ROOT/'outputs/self-map-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    full=a.read(a.RAW/'recorded-frames/summary.json')
    derived=a.EXP/'results/recorded-frames.json'
    # Preserve the first large derived copy too; raw summary is already separate.
    if derived.exists() and derived.stat().st_size>1024**2:
        archive=a.RAW/'recorded-frames/experiment-full-summary.json'
        assert not archive.exists()
        derived.rename(archive)
    compact={}
    for case,row in full.items():
        compact[case]={k:v for k,v in row.items() if k!='groups'}
        if 'groups' in row:
            compact[case]['groups']={k:v for k,v in row['groups'].items() if k in ('all','open','closed')}
    a.write(derived,dict(scope='all/open-command/closed-command; all PWM group details in raw',
        raw_full=str(a.RAW/'recorded-frames/summary.json'),raw_full_sha256=a.sha(a.RAW/'recorded-frames/summary.json'),cases=compact))
    figure,axes=plt.subplots(2,2,figsize=(11,6.8),sharex='col')
    yaws=a.read(a.RAW/'recorded-frames/yaw.json')
    for col,case in enumerate(('tape-north','tape-south')):
        rows=a.read(a.RAW/'recorded-frames'/f'{case}-frames.json')
        t=[r['t'] for r in rows]
        top,bottom=axes[0,col],axes[1,col]
        top.plot(t,[r['pitch_actual_minus_command_deg'] for r in rows],label='Actual - command FK')
        top.plot(t,[r['pitch_body_relative_actual_minus_command_deg'] for r in rows],label='Arm relative to chassis')
        top.plot(t,[r['pitch_body_attitude_contribution_deg'] for r in rows],label='Chassis attitude term')
        top.set_title(case+' / evaluation only')
        top.set_ylabel('Pitch difference (deg)')
        f=yaws[case]['frames']
        ft=np.array([r['t'] for r in f])
        dr=np.degrees([r['dr_yaw_rad'] for r in f])
        actual=np.degrees([r['actual_yaw_from_start_rad'] for r in f])
        bottom.plot(ft,dr-dr[0],label='M1 command DR')
        bottom.plot(ft,actual-actual[0],label='Recorded body rotation')
        bottom.axvspan(4.7,6.5,color='gray',alpha=.13,label='Original accepted pair')
        bottom.set_ylabel('Yaw since first eligible frame (deg)')
        bottom.set_xlabel('Recorded SIM time (s)')
        for ax in (top,bottom):
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    figure.suptitle('Same-qpos FK agrees; command-state mismatch remains',fontsize=12)
    figure.tight_layout()
    a.EXP.joinpath('figures').mkdir(exist_ok=True)
    figure.savefig(a.EXP/'figures/frame-residuals.png',dpi=140)
    plt.close(figure)
    files=[dict(path=str(p.relative_to(a.RAW)),bytes=p.stat().st_size,sha256=a.sha(p))
        for p in sorted(a.RAW.rglob('*')) if p.is_file()]
    a.write(a.EXP/'results/raw-manifest.json',dict(root=str(a.RAW),files=files,
        count=len(files),total_bytes=sum(r['bytes'] for r in files),remote_backup=False))
    print('raw',len(files),sum(r['bytes'] for r in files),'plot',a.EXP/'figures/frame-residuals.png')


if __name__=='__main__':main()
