"""gcp2 ffmpeg place phase first/middle/end two frames each, with source hashes."""
import hashlib, json, platform, subprocess, tempfile
from pathlib import Path

RUNS = Path('/home/ugrp/ugrp-sim/runs')


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    source = RUNS/'reloc18-round3/place-predicates.json'
    data = json.loads(source.read_text())
    out = RUNS/'reloc18-place-frames'
    out.mkdir(exist_ok=True)
    records = []
    for run in data['runs']:
        frames = run.get('frames', [])
        if not frames:
            records.append(dict(run=run['run'], phase_missing=True))
            continue
        indices = [0, 1, len(frames)//2-1, len(frames)//2, len(frames)-2, len(frames)-1]
        chosen = [frames[i] for i in indices]
        target = out/(run['run']+'.jpg')
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            for i, item in enumerate(chosen):
                p = Path(item['frame'])
                assert hashlib.sha256(p.read_bytes()).hexdigest() == item['sha256']
                (Path(tmp)/f'{i:02}.jpg').symlink_to(p)
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-i',str(Path(tmp)/'%02d.jpg'),'-vf','scale=320:240,tile=3x2:nb_frames=6:padding=2:margin=2','-frames:v','1','-q:v','3',str(target)],check=True)
        records.append(dict(run=run['run'], scope='actual final zone_place_view; first/middle/end two native own-camera exposures each',
                            frames=[{k:f[k] for k in ('t','frame','sha256')} for f in chosen],
                            plate=dict(name=target.name, bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())))
    (out/'manifest.json').write_text(json.dumps(dict(records=records, source=str(source)),indent=2)+'\n')
    print(len(records), 'place records')


if __name__ == '__main__':
    main()
