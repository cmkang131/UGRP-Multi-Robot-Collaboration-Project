#!/usr/bin/env python3
"""Read immutable git objects for pin/volume/receipt metrics; no code imports."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
from analyze import seconds, write_csv

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent

def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True)
def blob(sha,path):return git('show',f'{sha}:{path}')
def commit(sha):
    full,t,subject=git('show','-s','--format=%H%n%cI%n%s',sha).strip().split('\n',2)
    return {'sha':full,'committed_at':t,'subject':subject}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,default=HERE/'data');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--local-outputs',type=Path,help='optional read-only metadata receipts; no media read')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((a.data/'metadata.json').read_text());sha=meta['git_head'];prs=json.loads((a.data/'prs.json').read_text())
    pins=[];previous={};pinmaps={};pin_history=[]
    for rev,directory in [('v6b','2026-09-28-zone-pair-v6b-boot'),('v6c','2026-09-29-pair-v6c'),('v6d','2026-09-29-pair-v6d-align'),('v6e','2026-09-29-pair-v6e-carry')]:
        path=f'experiments/{directory}/prereg_{rev}.json';text=blob(sha,path);d=json.loads(text);current=d['v6_contract']['source_sha256'];pinmaps[rev]=current
        overlap=current.keys()&previous.keys();changed=[k for k in sorted(overlap) if current[k]!=previous[k]]
        added=sorted(current.keys()-previous.keys());removed=sorted(previous.keys()-current.keys())
        h=[]
        # Walk actual content changes, not merge timestamps that leave this path identical.
        for c in reversed(git('log','--format=%H',sha,'--',path).splitlines()):
            txt=blob(c,path);v=json.loads(txt);digest=hashlib.sha256(txt.encode()).hexdigest()
            if not h or digest!=h[-1]['file_sha256']:
                h.append({**commit(c),'file_sha256':digest,'registration_sha256':v.get('registration_sha256'),
                          'source_count':len(v['v6_contract']['source_sha256'])})
        pin_history.append({'revision':rev,'path':path,'distinct_path_versions':h})
        pins.append({'revision':rev,'policy':'b-v6g' if rev=='v6e' else 'b-'+rev,'path':path,'status':d['status'],
          'source_files':len(current),'unchanged_common':len(overlap)-len(changed),'changed_common':len(changed),
          'added':len(added),'removed':len(removed),'changed_paths':changed,'added_paths':added if previous else [],
          'file_lines':len(text.splitlines()),'first_pin_commit':h[0]['sha'],'latest_pin_commit':h[-1]['sha'],
          'distinct_pin_file_versions':len(h),'registration_sha256':d.get('registration_sha256')})
        previous=current
    for c in ['52264828','3afc61b0']:
        path='experiments/2026-09-30-pair-v6h-carry/source_changes_UNSEALED.json';d=json.loads(blob(c,path));changes=d['changed_sealed_sources']
        pins.append({'revision':'v6h_unsealed','commit':commit(c),'sources':d['sources'],
            'changed_common':sum(x['old_sha256'] is not None and x['new_sha256'] is not None for x in changes),
            'added':sum(x['old_sha256'] is None for x in changes),'removed':sum(x['new_sha256'] is None for x in changes),
            'source_preview_path':path})
    paths=git('ls-tree','-r','--name-only',sha,'experiments').splitlines()
    dirs=sorted({f['path'].split('/')[1] for pr in prs for f in pr['files'] if f['path'].startswith('experiments/') and len(f['path'].split('/'))>=3})
    volume=[]
    for directory in dirs:
        files=[f for f in paths if f.startswith('experiments/'+directory+'/')]
        if not files:continue
        row={'directory':directory,'git_sha':sha,'readme_lines':0,'prereg_lines':0,'all_markdown_lines':0,'python_lines':0,'prereg_files':0}
        for path in files:
            name=Path(path).name
            wanted=name=='README.md' or 'prereg' in name.lower() or path.endswith(('.md','.py'))
            if not wanted:continue
            lines=len(blob(sha,path).splitlines())
            if name=='README.md':row['readme_lines']+=lines
            if 'prereg' in name.lower() and path.endswith(('.md','.json')):row['prereg_lines']+=lines;row['prereg_files']+=1
            if path.endswith('.md'):row['all_markdown_lines']+=lines
            if path.endswith('.py'):row['python_lines']+=lines
        volume.append(row)
    # Open v6h implementation is outside snapshot main: record exact PR head separately.
    hs=next(p['headRefOid'] for p in prs if p['number']==292)
    directory='2026-09-30-pair-v6h-carry';files=git('ls-tree','-r','--name-only',hs,'experiments/'+directory).splitlines()
    volume.append({'directory':directory,'git_sha':hs,'readme_lines':sum(len(blob(hs,f).splitlines()) for f in files if Path(f).name=='README.md'),
      'prereg_lines':sum(len(blob(hs,f).splitlines()) for f in files if 'prereg' in Path(f).name.lower() and f.endswith(('.md','.json'))),
      'all_markdown_lines':sum(len(blob(hs,f).splitlines()) for f in files if f.endswith('.md')),
      'python_lines':sum(len(blob(hs,f).splitlines()) for f in files if f.endswith('.py')),
      'prereg_files':sum('prereg' in Path(f).name.lower() and f.endswith(('.md','.json')) for f in files)})
    for directory in sorted(set(dirs)-{row['directory'] for row in volume}):
        owners=[pr for pr in prs if pr['state']=='OPEN' and any(f['path'].startswith('experiments/'+directory+'/') for f in pr['files'])]
        if not owners:
            raise ValueError('experiment missing from main and open PR heads: '+directory)
        owner=max(owners,key=lambda pr:pr['number']);head=owner['headRefOid']
        files=git('ls-tree','-r','--name-only',head,'experiments/'+directory).splitlines()
        counts={f:len(blob(head,f).splitlines()) for f in files if f.endswith(('.py','.md','.json'))}
        volume.append({'directory':directory,'git_sha':head,
            'readme_lines':sum(n for f,n in counts.items() if Path(f).name=='README.md'),
            'prereg_lines':sum(n for f,n in counts.items() if 'prereg' in Path(f).name.lower() and f.endswith(('.md','.json'))),
            'all_markdown_lines':sum(n for f,n in counts.items() if f.endswith('.md')),
            'python_lines':sum(n for f,n in counts.items() if f.endswith('.py')),
            'prereg_files':sum('prereg' in Path(f).name.lower() and f.endswith(('.md','.json')) for f in counts)})
    churn=collections.defaultdict(lambda:{'file_changes':0,'added':0,'deleted':0})
    for pr in prs:
        for f in pr.get('git_file_stats',pr['files']):
            category='markdown' if f['path'].endswith('.md') else 'python' if f['path'].endswith('.py') else 'other'
            churn[category]['file_changes']+=1;churn[category]['added']+=f['additions'];churn[category]['deleted']+=f['deletions']
    # Result receipt commits are upper bounds, not exact run end timestamps.
    pairs=[('b-v6c_initial','b5234b7a','099f4466'),('b-v6d_execution_tree','052e3eba','29d30234'),
           ('b-v6e_yaw_initial','86cdefc9','b16f7987'),('b-v6e_yaw_reviewed','4fac772d','eb5232c7'),
           ('b-v6g_first_heldout','f844a373','6a07fd8a'),('b-v6g_hR2_changed_staging','f844a373','3c91decd')]
    timeline=[]
    for name,start,end in pairs:
        begin,receipt=commit(start),commit(end)
        timeline.append({'policy_scope':name,'source':begin,'result_receipt':receipt,
            'commit_to_result_receipt_s':seconds(begin['committed_at'],receipt['committed_at']),
            'measurement_type':'stage_probe; not sealed confirmatory completion'})
    bundle_source=blob(sha,'harness/zone_study_integration.py')
    # Parse constants as data, without importing runtime modules.
    import ast
    module=ast.parse(bundle_source)
    retired=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RETIRED_BUNDLE_IDS' for t in n.targets))
    receipts=[]
    if a.local_outputs:
        selected=['pair-stage-probes-b5234b7a-v6c-align','pair-stage-probes-b534a9b5-v6c-bound-e2e',
           'pair-stage-probes-052e3eba-v6d-venv-align-0','pair-stage-probes-052e3eba-v6d-venv-align-1',
           'pair-stage-probes-4714263a-v6d-final-align-subset','pair-stage-probes-4714263a-v6d-final-bound-e2e',
           'pair-stage-probes-f2186414-yawcal','pair-stage-probes-4fac772d-yawcal',
           'pair-stage-probes-3f6ca985-ghR2','pair-stage-probes-3f6ca985-ghR2L7']
        for name in selected:
            path=a.local_outputs/name/'manifest.json'
            if not path.exists():receipts.append({'run':name,'available':False});continue
            data=path.read_bytes();d=json.loads(data);src=d['source'];tree=src.get('execution_tree',{})
            receipts.append({'run':name,'available':True,'manifest_sha256':hashlib.sha256(data).hexdigest(),
              'state':d.get('state'),'wall_s':d.get('wall_s'),'cases':d.get('cases'),'source_sha':src['source_sha'],
              'source_changed':d.get('source_changed'),'tree_sha256':tree.get('sha256'),'tree_files':len(tree.get('files',[])),
              'utc_start_or_end_present':any(k in d for k in ['created_at','started_at','ended_at','finished_at'])})
    for name,value in [('pins.json',pins),('pin_history.json',pin_history),('timeline.json',timeline),('diff_volume.json',dict(churn)),('retired_bundles.json',list(retired))]:
        (a.out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    write_csv(a.out,'docs_volume.csv',volume)
    if receipts:(a.out/'local_manifest_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    print(json.dumps({'pins':[{k:v for k,v in x.items() if k in ['revision','source_files','sources','changed_common','added','removed','file_lines','distinct_pin_file_versions']} for x in pins],
         'timeline_minutes':[(x['policy_scope'],round(x['commit_to_result_receipt_s']/60,2)) for x in timeline],
         'retired_bundle_count':len(retired),'volume':volume[-3:],'diff_volume':dict(churn)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
