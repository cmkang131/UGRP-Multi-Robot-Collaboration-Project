#!/usr/bin/env python3
"""Read-only GitHub/git process snapshot. No simulation, pytest, or model calls.
Run with --out NEW_DIRECTORY to preserve the checked-in snapshot.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
from pathlib import Path
import subprocess

REPO = 'kcm0127-dotcom/ugrp'
ROOT = Path(__file__).resolve().parents[2]

def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True)

def gh(*args):
    return json.loads(command('gh', *args))

def save(out, name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')

def compact_job(j):
    keep = ['id', 'name', 'status', 'conclusion', 'started_at', 'completed_at']
    value = {k: j.get(k) for k in keep}
    # Full job timings cover every job. Preserve step timings only for the
    # offline suite and property shards, which are the test-runtime estimands.
    value['test_steps'] = [{k:s.get(k) for k in ['name','conclusion','started_at','completed_at']}
                           for s in j.get('steps', []) if s['name'] in
                           ['Run offline regression suite', 'Run offline regression shard',
                            'Compare additive scheduling against frozen v64']]
    return value

def pr(n):
    fields = 'number,title,url,state,isDraft,createdAt,updatedAt,closedAt,mergedAt,headRefName,headRefOid,baseRefName,baseRefOid,mergeCommit,commits,reviews,comments,files,additions,deletions,body'
    value = gh('pr', 'view', str(n), '--repo', REPO, '--json', fields)
    if len(value['files']) >= 100:
        pages = gh('api', '--paginate', '--slurp', f'repos/{REPO}/pulls/{n}/files?per_page=100')
        value['files'] = [{'path':f['filename'], 'additions':f['additions'], 'deletions':f['deletions']}
                          for page in pages for f in page]
        current = gh('pr','view',str(n),'--repo',REPO,'--json','headRefOid')
        if current['headRefOid'] != value['headRefOid']:
            raise RuntimeError(f'PR {n} changed during pagination; collect again')
    supplement_diff_stats(value)
    return value

def supplement_diff_stats(value):
    if (sum(f['additions'] for f in value['files']),sum(f['deletions'] for f in value['files'])) == (value['additions'],value['deletions']):
        return
    # GitHub sometimes returns zero per-file stats beyond its large-diff limit.
    # Preserve API values, and retain an explicit git fallback with immutable refs.
    rows=[]
    for line in command('git','diff','--numstat',value['baseRefOid']+'...'+value['headRefOid']).splitlines():
        added,deleted,path=line.split('\t')
        rows.append({'path':path,'additions':0 if added=='-' else int(added),'deletions':0 if deleted=='-' else int(deleted)})
    if {r['path'] for r in rows} != {f['path'] for f in value['files']}:
        raise RuntimeError('git/API file paths differ; inspect renames or changing base')
    if (sum(r['additions'] for r in rows),sum(r['deletions'] for r in rows)) != (value['additions'],value['deletions']):
        raise RuntimeError('git/API totals differ; do not silently mix snapshots')
    value['git_file_stats']=rows

def run_jobs(run):
    attempts = []
    for a in range(1, run.get('run_attempt', 1) + 1):
        pages = gh('api', '--paginate', '--slurp', f'repos/{REPO}/actions/runs/{run["id"]}/attempts/{a}/jobs?per_page=100')
        attempts.append({'attempt': a, 'jobs': [compact_job(j) for page in pages for j in page['jobs']]})
    return {'id': run['id'], 'attempts': attempts}

def worktree_details(porcelain, target):
    result={}
    for line in porcelain.splitlines():
        if line.startswith('HEAD '):
            sha=line.split()[1]
            check=subprocess.run(['git','merge-base','--is-ancestor',sha,target],cwd=ROOT,check=False)
            if check.returncode not in [0,1]:
                raise RuntimeError('worktree ancestry unavailable')
            result[sha]={'committed_at':command('git','show','-s','--format=%cI',sha).strip(),
                         'merged':check.returncode==0}
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if list(out.iterdir()):
        p.error('--out must be empty; preserve previous snapshots')
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    meta = {'started_at': now, 'repo': REPO, 'first_pr': 256, 'last_pr': 294,
            'git_head': command('git', 'rev-parse', 'HEAD').strip(),
            'origin_main': command('git', 'rev-parse', 'origin/main').strip(),
            'gh_version': command('gh', '--version').splitlines()[0]}
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        prs = list(pool.map(pr, range(256, 295)))
    save(out, 'prs.json', prs)
    earliest = min([x['createdAt'] for x in prs] +
                   [c['committedDate'] for x in prs for c in x['commits']])
    # REST pagination includes attempt numbers and PR associations omitted by gh run list.
    pages = gh('api', '--paginate', '--slurp', f'repos/{REPO}/actions/runs?per_page=100&created={earliest}..{now[:19]}Z')
    runs = [r for page in pages for r in page['workflow_runs']]
    keep = ['id','name','workflow_id','head_branch','head_sha','event','status','conclusion','created_at','updated_at','run_started_at','run_attempt','html_url','pull_requests','path']
    runs = [{k:r.get(k) for k in keep} for r in runs]
    save(out, 'runs.json', runs)
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        for i, row in enumerate(pool.map(run_jobs, runs), 1):
            save(out, f'jobs_{row["id"]}.json', row)
            if i % 25 == 0:
                print(f'jobs {i}/{len(runs)}', flush=True)
    open_prs = gh('pr','list','--repo', REPO,'--state','open','--limit','1000','--json','number,title,headRefName,createdAt,updatedAt,isDraft')
    save(out, 'open_prs.json', open_prs)
    all_prs=gh('pr','list','--repo',REPO,'--state','all','--limit','1000','--json','number,createdAt,closedAt,mergedAt')
    if len(all_prs)==1000:
        raise RuntimeError('PR inventory may be truncated; increase pagination coverage')
    save(out,'all_prs.json',[r for r in all_prs if dt.datetime.fromisoformat(r['createdAt'].replace('Z','+00:00'))<=dt.datetime.fromisoformat(now)])
    worktrees=command('git','worktree','list','--porcelain')
    save(out, 'inventory.json', {
        'worktrees': worktrees,
        'worktree_head_details':worktree_details(worktrees,meta['origin_main']),
        'refs': command('git','for-each-ref','--format=%(refname)\t%(objectname)\t%(committerdate:iso-strict)','refs/heads/','refs/remotes/origin/'),
        'merged_local': command('git','branch','--merged','origin/main','--format=%(refname:short)'),
        'merged_remote': command('git','branch','-r','--merged','origin/main','--format=%(refname:short)')})
    meta.update({'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'run_count':len(runs),
                 'earliest_pr':min(x['createdAt'] for x in prs),
                 'earliest_commit':min(c['committedDate'] for x in prs for c in x['commits'])})
    save(out,'metadata.json',meta)
    print(json.dumps(meta),flush=True)

if __name__ == '__main__':
    main()
