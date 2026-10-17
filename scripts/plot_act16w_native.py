"""Actual native optimizer logs -> standalone curves on owned L4 CPU only."""
import argparse
import json
from pathlib import Path
import statistics

from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    curves={};receipts=[];summaries={}
    for arm in ('A','B','C','D1'):
        points={}
        for stage in ('smoke','main'):
            folder=a.training_root/arm/stage;summary=folder/'summary.json';log=folder/'progress.jsonl'
            if not summary.exists():continue
            value=json.loads(summary.read_text())
            if value.get('contact_profile')!='warp_native_contact_v1':
                raise ValueError('noslip or unlabeled models cannot enter native curves')
            summaries[arm]=value
            receipts.append(dict(path=str(summary),sha256=sha256(summary)))
            if log.exists():
                for line in log.read_text().splitlines():
                    if line.strip():
                        row=json.loads(line);points[row['step']]=row
                receipts.append(dict(path=str(log),sha256=sha256(log)))
        if points:curves[arm]=[points[step] for step in sorted(points)]
    if not curves:raise ValueError('no real optimizer points; do not fabricate curves')
    a.out.mkdir(parents=True,exist_ok=False)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    fields=[('loss','Total training loss'),('movement_l1_loss','Movement L1'),
            ('done_bce_loss','Completion BCE'),('kld_loss','KL divergence')]
    colors={'A':'#2166ac','B':'#e08214','C':'#1b9e77','D1':'#984ea3'}
    for ax,(key,title) in zip(axes.flat,fields):
        for arm,points in curves.items():
            ax.plot([row['step'] for row in points],[row[key] for row in points],
                    color=colors[arm],linewidth=.8,alpha=.8,label=arm)
        ax.set(title=title,xlabel='Optimizer step',ylabel=key,xlim=(0,10000))
        ax.grid(alpha=.2);ax.legend()
    fig.suptitle('ACT16 native MJWarp: actual training losses, not task success')
    fig.savefig(a.out/'learning-curves.png',dpi=140);plt.close(fig)
    summary=dict(source_sha=source,host=host,scope='real optimizer loss logs only; no physical task inference',
        contact_profile='warp_native_contact_v1',raw=receipts,
        arms={arm:dict(step=summaries[arm]['steps_completed'],complete=summaries[arm]['complete'],
            logged_points=len(points),last=points[-1],
            last100_logged_total_loss_median=statistics.median(row['loss'] for row in points[-100:]))
            for arm,points in curves.items()},
        files={'learning-curves.png':sha256(a.out/'learning-curves.png')})
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (a.out/'curve-points.json').write_text(json.dumps(curves)+'\n')
    print(json.dumps(dict(out=str(a.out),arms=list(curves),raw_receipts=len(receipts))))


if __name__=='__main__':main()
