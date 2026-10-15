"""GCP2 ffmpeg six-frame plates, never a substitute for a missing place phase."""
import hashlib,json,platform,subprocess,tempfile
from pathlib import Path
import numpy as np
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    out=RUNS/'reloc18-six-frames';out.mkdir(exist_ok=True);records=[]
    runs=sorted(RUNS.glob('reloc17-decomp-*/raw'))+sorted(RUNS.glob('reloc17-r*-selfmap-*/raw'))+sorted(RUNS.glob('reloc17-r*-carry-*/raw'))
    for raw in runs:
        name=raw.parent.name
        if 'selfmap' in name or 'decomp' in name:
            fr=[json.loads(x) for x in load(raw/'robots/r3/frames.jsonl').splitlines()];camera='r3';items=[dict(t=x['sim_time'],path=str(raw/x['path'])) for x in fr]
            phase_scope='localization-only diagnostic; no place task exists'
        else:
            m=json.loads((raw/'playback/manifest.json').read_text());fr=m['frames'];camera='r1'
            items=[]
            for x in fr:
                # Playback manifests record synchronized snapshots, one path per camera.
                items.append(dict(t=x['t'],path=str(raw/'playback'/x['files']['r1'])))
            phase_scope='whole transport first/middle/end; original ledger has zero final place phase ticks'
        chosen=[items[i] for i in np.linspace(0,len(items)-1,6,dtype=int)]
        target=out/(name+'.jpg')
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            for i,x in enumerate(chosen):(Path(tmp)/f'{i:02d}.jpg').symlink_to(x['path'])
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-i',str(Path(tmp)/'%02d.jpg'),'-vf','scale=320:240,tile=3x2:nb_frames=6:padding=2:margin=2','-frames:v','1','-q:v','3',str(target)],check=True)
        records.append(dict(run=name,camera=camera,phase_scope=phase_scope,frames=[dict(x,sha256=hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()) for x in chosen],plate=dict(path=str(target),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
    (out/'manifest.json').write_text(json.dumps(dict(records=records,reproduce=f'python {__file__}'),indent=2)+'\n')
    print(len(records),'plates')
if __name__=='__main__':main()
