"""GCP2-only terminal result/review inventory; no rendering or controller input."""
import datetime,hashlib,json,platform,subprocess
from pathlib import Path
from scripts.analyze_reloc11_selfmap import obj
ROOT=Path('/home/ugrp/ugrp-sim');RUNS=ROOT/'runs'
def actual(p):return p if p.is_file() else Path(str(p)+'.zst')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def file(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def main():
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    out=dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),host=platform.node(),runs=[],reviews=[],source_copies=[])
    for n in (1,2,3):
        batch=RUNS/f'reloc16-round{n}';queue=json.loads((batch/'queue.json').read_text())
        for r in queue['runs']:
            raw=Path(r['raw']);result=obj(raw/'result.json')
            if result.get('status') in ('running',None):raise RuntimeError(f'INCOMPLETE:{raw}')
            manifests=[actual(p) for p in (raw/'artifacts.sha256.json',raw/'manifest.json') if actual(p).is_file()]
            if not manifests:raise RuntimeError(f'MANIFEST_MISSING:{raw}')
            out['runs'].append(dict(round=n,run=r['name'],source_sha=r['source_sha'],raw=str(raw),status=result['status'],
                result=file(actual(raw/'result.json')),manifests=[file(p) for p in manifests],queue=file(batch/'queue.json'),
                rejection_table=file(batch/'rejection-table.json'),parent_meta=file(raw.parent/'RUN_META.json') if (raw.parent/'RUN_META.json').is_file() else None,raw_meta=file(raw/'RUN_META.json') if (raw/'RUN_META.json').is_file() else None))
    for p in sorted(RUNS.glob('reloc16-review-*')):
        if p.is_dir():out['reviews'].append(dict(root=str(p),files=[file(q) for q in sorted(p.iterdir()) if q.is_file()]))
    for p in sorted((ROOT/'src').glob('reloc16-*')):
        if not (p/'.git').exists():continue
        alternates=p/'.git/objects/info/alternates'
        out['source_copies'].append(dict(root=str(p),sha=subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip(),
            alternates=alternates.read_text().strip() if alternates.exists() else None))
    out['environment']=subprocess.check_output([str(ROOT/'ugrp/.venv-sim/bin/python'),'-c','import sys,numpy,scipy,matplotlib,mujoco;print(sys.version);print({k:v.__version__ for k,v in [("numpy",numpy),("scipy",scipy),("matplotlib",matplotlib),("mujoco",mujoco)]})'],text=True)
    out['dependency_install_logs']=[file(p) for p in (RUNS/'reloc16-compiler-install.log',RUNS/'reloc16-matplotlib-install.log') if p.exists()]
    out['analysis_scripts']=[file(p) for p in (Path(__file__),ROOT/'analysis-tools/analyze_reloc16.py') if p.exists()]
    out['raw_disk_usage']=subprocess.check_output(['du','-sb',*[str(p) for p in sorted(RUNS.glob('reloc16-*')) if p.is_dir()]],text=True)
    dest=RUNS/'reloc16-inventory.json';dest.write_text(json.dumps(out,indent=2)+'\n');print(dest)
if __name__=='__main__':main()
