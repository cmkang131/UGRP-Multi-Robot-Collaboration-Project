"""Fetch-lite export of terminal derived evidence, never a full raw backup."""
import hashlib, json, platform, shutil, subprocess
from pathlib import Path

RUNS = Path('/home/ugrp/ugrp-sim/runs')


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    assert (RUNS/'reloc18-round3/ANALYSIS_DONE.json').is_file()
    out = RUNS/'reloc18-terminal-export-v2'
    out.mkdir(exist_ok=False)
    sources = {'integrity.json': RUNS/'reloc18-integrity.json'}
    for n in (1, 2, 3):
        for stem in ('summary', 'rejection-table', 'queue', 'speed-gate'):
            sources[f'round{n}-{stem}.json'] = RUNS/f'reloc18-round{n}/{stem}.json'
    for stem in ('selfmap-results', 'place-predicates', 'ANALYSIS_DONE'):
        sources[f'round3-{stem}.json'] = RUNS/f'reloc18-round3/{stem}.json'
    records = []
    for name, src in sources.items():
        data = src.read_bytes()
        target = out/name
        if len(data)>65536:
            target = out/(name+'.zst')
            subprocess.run(['zstd','-q','-o',str(target)],input=data,check=True)
            restored = subprocess.check_output(['zstd','-dc',str(target)])
            assert restored == data
        else:
            target.write_bytes(data)
        records.append(dict(source=str(src), name=target.name, bytes=target.stat().st_size,
                            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                            uncompressed_bytes=len(data), uncompressed_sha256=hashlib.sha256(data).hexdigest()))
    (out/'manifest.json').write_text(json.dumps(dict(scope='derived summary export only; originals remain on gcp2',files=records),indent=2)+'\n')
    for n in (1, 2, 3):
        for t in json.loads((RUNS/f'reloc18-round{n}/queue.json').read_text())['runs']:
            p=Path(t['raw']).parent/'RUN_META.json'
            meta=json.loads(p.read_text());meta['pr']=538
            if t['name']=='reloc18-r3-carry-candidate-93315-133c12f4':
                meta.update({'class':'milestone','note':'version representative failure video and original data preserved; no success claim'})
            p.write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(dict(files=len(records),bytes=sum(x['bytes'] for x in records))))


if __name__ == '__main__':
    main()
