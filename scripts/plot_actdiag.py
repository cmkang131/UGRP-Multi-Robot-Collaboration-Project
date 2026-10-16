"""Headless plots of saved diagnostic summaries, GCP2 only."""
import argparse
from pathlib import Path
import json
import platform


def main():
    if platform.system()!='Linux':raise RuntimeError('GCP2 plots only')
    from scripts.beamact1_runtime import require_gcp2
    require_gcp2(training=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p=argparse.ArgumentParser();p.add_argument('--probe',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();d=json.loads(a.probe.read_text());fig,axes=plt.subplots(1,2,figsize=(10,3.5))
    windows=d['loss_windows'];x=[sum(r['steps'])/2 for r in windows]
    for key,label in [('movement_l1_loss','Movement L1'),('done_bce_loss','Done BCE'),('kld_loss','KL')]:
        axes[0].plot(x,[r[key]['mean'] for r in windows],marker='o',label=label)
    axes[0].set(xlabel='Optimizer step (existing logs)',ylabel='Mean logged loss',yscale='log',title='Training objective components')
    steps=[300,5000,10000]
    for split in ('train','validation'):
        axes[1].plot(steps,[d[f'step{n}'][split]['ACT_decoded']['wheel_mae'] for n in steps],marker='o',label=split)
    axes[1].set(xlabel='Saved checkpoint step',ylabel='Decoded wheel MAE',title='Fixed first/middle/last row per shard')
    for ax in axes:ax.legend();ax.grid(alpha=.25)
    fig.suptitle('Artifact-only ACT diagnosis: no new optimization; probe is not all-row MAE',fontsize=10)
    fig.tight_layout();fig.savefig(a.output,dpi=160);plt.close(fig)


if __name__=='__main__':main()
