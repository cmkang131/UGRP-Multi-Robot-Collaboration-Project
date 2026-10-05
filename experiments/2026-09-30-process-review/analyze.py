#!/usr/bin/env python3
"""Derive PR/CI inventory metrics from collect.py snapshots (offline)."""
import argparse
import collections
import csv
import datetime as dt
import json
import math
from pathlib import Path
import re
import statistics


def stamp(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None


def seconds(a, b):
    return (stamp(b) - stamp(a)).total_seconds() if a and b else None


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    return {'n':len(xs), 'median':statistics.median(xs) if xs else None,
            'p90_nearest_rank':xs[math.ceil(.9*len(xs))-1] if xs else None,
            'min':min(xs) if xs else None, 'max':max(xs) if xs else None,
            'sum':sum(xs)}


def write_csv(out, name, rows):
    if not rows:
        return
    with (out/name).open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path(__file__).parent/'data')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); out=args.out;out.mkdir(parents=True,exist_ok=True)
    read=lambda n:json.loads((args.data/n).read_text())
    prs=read('prs.json');runs=read('runs.json');meta=read('metadata.json')
    cutoff=meta['started_at']
    prmap={x['headRefName']:x['number'] for x in prs}
    run_rows=[];job_rows=[];step_rows=[];all_attempts={}
    for r in runs:
        snap=read(f'jobs_{r["id"]}.json');all_attempts[r['id']]=snap['attempts']
        for a in snap['attempts']:
            for j in a['jobs']:
                wall=seconds(j['started_at'],j['completed_at'])
                if wall is not None and wall < 0:
                    raise ValueError('negative job duration')
                job_rows.append({'run_id':r['id'],'attempt':a['attempt'],'pr':prmap.get(r['head_branch'],''),
                   'job_id':j['id'],'name':j['name'],'conclusion':j['conclusion'],'started_at':j['started_at'],
                   'completed_at':j['completed_at'],'wall_s':wall})
                for s in j['test_steps']:
                    step_rows.append({'run_id':r['id'],'attempt':a['attempt'],'job_id':j['id'],
                      'job':j['name'],'step':s['name'],'conclusion':s['conclusion'],
                      'wall_s':seconds(s['started_at'],s['completed_at'])})
        # Latest attempt: a completed workflow may have skipped jobs without times.
        js=snap['attempts'][-1]['jobs']
        starts=[j['started_at'] for j in js if j['started_at']]
        ends=[j['completed_at'] for j in js if j['completed_at']]
        complete=r['status']=='completed'
        end=max(ends) if ends and complete else None
        start=min(starts) if starts else None
        run_rows.append({'run_id':r['id'],'pr':prmap.get(r['head_branch'],''),'branch':r['head_branch'],
           'event':r['event'],'sha':r['head_sha'],'created_at':r['created_at'],'first_job_at':start,'last_job_at':end,
           'status':r['status'],'conclusion':r['conclusion'],'attempts':r['run_attempt'],
           'created_to_end_s':seconds(r['created_at'],end),'jobs_span_s':seconds(start,end),
           'created_to_first_job_s':seconds(r['created_at'],start),
           'offline_sharded':any(j['name'].startswith('offline-regression-shard (') for j in js),
           'url':r['html_url']})
    annotations=json.loads((Path(__file__).parent/'review_annotations.json').read_text())
    pr_rows=[]
    for x in prs:
        cs=x['commits'];rs=[r for r in run_rows if r['pr']==x['number']]
        ann=annotations.get(str(x['number']),{})
        t=ann.get('first_review_observed_at')
        unique_commits=[c for c in cs if not c['messageHeadline'].startswith('Merge ')]
        first=min(c['committedDate'] for c in unique_commits or cs)
        pr_rows.append({'pr':x['number'],'state':x['state'],'base':x['baseRefName'],
          'created_at':x['createdAt'],'merged_at':x['mergedAt'],'open_to_merge_s':seconds(x['createdAt'],x['mergedAt']),
          'open_age_s_if_unmerged':seconds(x['createdAt'],cutoff) if not x['mergedAt'] else None,
          'first_nonmerge_commit_at':first,'first_commit_to_open_s':seconds(first,x['createdAt']),
          'first_commit_to_merge_s':seconds(first,x['mergedAt']),
          'commits':len(cs),'nonmerge_commits':len(unique_commits),'formal_reviews':len(x['reviews']),
          'comments':len(x['comments']),'review_fix_rounds_documented_min':ann.get('rounds_min',0),
          'first_review_observed_at':t,'first_review_time_kind':ann.get('time_kind','not_observed'),
          'commits_strictly_after_first_review':sum(c['committedDate']>t for c in cs) if t else None,
          'first_review_to_merge_s':seconds(t,x['mergedAt']) if t else None,
          'ci_runs':len(rs),'ci_explicit_rerun_attempts':sum(r['attempts']-1 for r in rs),
          'ci_distinct_head_shas':len({r['sha'] for r in rs}),
          'markdown_only':all(f['path'].endswith('.md') for f in x['files']),
          'changed_files':len(x['files']),'additions':x['additions'],'deletions':x['deletions'],'url':x['url']})
    relevant=[r for r in run_rows if r['pr']!='']
    success=[r for r in relevant if r['conclusion']=='success']
    groups=collections.defaultdict(list)
    for r in runs:
        if r['head_branch'] in prmap:groups[(r['workflow_id'],r['head_sha'])].append(r)
    duplicates=[]
    for key,rr in groups.items():
        push=[r for r in rr if r['event']=='push'];pull=[r for r in rr if r['event']=='pull_request']
        if push and pull:
            push_ids={r['id'] for r in push}
            duplicates.append({'sha':key[1],'pr':prmap[rr[0]['head_branch']],
              'push_runs':[r['id'] for r in push],'pr_runs':[r['id'] for r in pull],
              'push_job_seconds':sum(j['wall_s'] or 0 for j in job_rows if j['run_id'] in push_ids)})
    inv=read('inventory.json');refs=[]
    merged_local=set(inv['merged_local'].splitlines());merged_remote=set(inv['merged_remote'].splitlines())
    for line in inv['refs'].splitlines():
        ref,sha,t=line.split('\t'); remote=ref.startswith('refs/remotes/');short=ref.removeprefix('refs/remotes/').removeprefix('refs/heads/')
        if short=='origin/HEAD':continue
        age=seconds(t,cutoff)/86400
        refs.append({'ref':ref,'sha':sha,'committed_at':t,'age_days':age,'remote':remote,
                     'merged_into_snapshot_main':short in (merged_remote if remote else merged_local),'stale_gt_7d':age>7})
    worktrees=[];bysha={r['sha']:r for r in refs}
    for block in inv['worktrees'].strip().split('\n\n'):
        d=dict(l.split(' ',1) if ' ' in l else [l,''] for l in block.splitlines())
        if 'worktree' not in d:continue
        ref=next((r for r in refs if r['ref']==d.get('branch')),bysha.get(d.get('HEAD'),{}))
        details=inv.get('worktree_head_details',{}).get(d.get('HEAD'),{})
        age=seconds(details['committed_at'],cutoff)/86400 if details else ref.get('age_days')
        worktrees.append({'path':d['worktree'],'branch':d.get('branch','detached'),'sha':d.get('HEAD'),
                         'age_days':age,'merged_into_snapshot_main':details.get('merged',ref.get('merged_into_snapshot_main')),
                         'stale_gt_7d':age>7 if age is not None else None})
    # Select homogeneous successful test-step timings, all attempts; no local execution.
    valid_ids={r['run_id'] for r in relevant}
    stepstats={name:stats(s['wall_s'] for s in step_rows if s['run_id'] in valid_ids and s['step']==name and s['conclusion']=='success')
               for name in sorted({s['step'] for s in step_rows})}
    sharded=[]
    required_gate=[]
    last_jobs=collections.Counter()
    for r in success:
        latest=[j for j in job_rows if j['run_id']==r['run_id'] and j['attempt']==r['attempts']]
        core=[j for j in latest if j['name'] in ['offline-regressions','offline-regression-checks'] or j['name'].startswith('offline-regression-shard (')]
        starts=[j['started_at'] for j in core if j['started_at']]
        ends=[j['completed_at'] for j in core if j['completed_at']]
        pytest=[s['wall_s'] for s in step_rows if s['run_id']==r['run_id'] and s['attempt']==r['attempts'] and s['step'] in ['Run offline regression suite','Run offline regression shard'] and s['conclusion']=='success']
        required_gate.append({'run_id':r['run_id'],'pr':r['pr'],'sharded':r['offline_sharded'],
            'created_to_required_end_s':seconds(r['created_at'],max(ends)) if ends else None,
            'required_span_s':seconds(min(starts),max(ends)) if starts and ends else None,
            'max_pytest_step_s':max(pytest) if pytest else None})
        if r['offline_sharded']:
            last_jobs[max((j for j in latest if j['completed_at']),key=lambda j:j['completed_at'])['name']]+=1
            js=[j for j in job_rows if j['run_id']==r['run_id'] and j['attempt']==r['attempts'] and j['name'].startswith('offline-regression-shard (')]
            sharded.append({'run_id':r['run_id'],'pr':r['pr'],'min_s':min(j['wall_s'] for j in js),
                'max_s':max(j['wall_s'] for j in js),'ratio':max(j['wall_s'] for j in js)/min(j['wall_s'] for j in js)})
    summary={'metadata':meta,'prs':{'count':len(prs),'merged':sum(bool(x['mergedAt']) for x in prs),
       'open_to_merge_s':stats(x['open_to_merge_s'] for x in pr_rows),'first_commit_to_merge_s':stats(x['first_commit_to_merge_s'] for x in pr_rows),
       'formal_reviews':sum(len(x['reviews']) for x in prs),'documented_review_fix_rounds_min':sum(x['review_fix_rounds_documented_min'] for x in pr_rows),
       'markdown_only_prs':[x['pr'] for x in pr_rows if x['markdown_only']]},
       'ci':{'all_window_runs':len(runs),'associated_runs':len(relevant),'associated_rerun_attempts':sum(r['attempts']-1 for r in relevant),
        'success_created_to_end_s':stats(r['created_to_end_s'] for r in success),
        'success_unsharded_created_to_end_s':stats(r['created_to_end_s'] for r in success if not r['offline_sharded']),
        'success_sharded_created_to_end_s':stats(r['created_to_end_s'] for r in success if r['offline_sharded']),
        'associated_conclusions':dict(collections.Counter(r['conclusion'] for r in relevant)),
        'success_queue_s':stats(r['created_to_first_job_s'] for r in success),
        'test_step_seconds':stepstats,'duplicate_push_pr_groups':len(duplicates),
        'duplicate_push_runs':sum(len(x['push_runs']) for x in duplicates),
        'duplicate_push_job_seconds':sum(x['push_job_seconds'] for x in duplicates),
        'shard_max_min_ratio':stats(x['ratio'] for x in sharded),
        'sharded_last_job':dict(last_jobs),
        'required_check_created_to_end_s':{str(flag):stats(x['created_to_required_end_s'] for x in required_gate if x['sharded']==flag) for flag in [False,True]},
        'max_offline_pytest_step_s':{str(flag):stats(x['max_pytest_step_s'] for x in required_gate if x['sharded']==flag) for flag in [False,True]}},
       'inventory':{'worktrees':len(worktrees),'worktrees_merged':sum(x['merged_into_snapshot_main'] is True for x in worktrees),
        'worktrees_stale_gt_7d':sum(x['stale_gt_7d'] is True for x in worktrees),
        'local_branches':sum(not x['remote'] for x in refs),'remote_tracking_branches':sum(x['remote'] for x in refs),
        'local_branches_merged':sum(not x['remote'] and x['merged_into_snapshot_main'] for x in refs),
        'local_branches_stale_gt_7d':sum(not x['remote'] and x['stale_gt_7d'] for x in refs),
        'remote_tracking_merged':sum(x['remote'] and x['merged_into_snapshot_main'] for x in refs),
        'remote_tracking_stale_gt_7d':sum(x['remote'] and x['stale_gt_7d'] for x in refs),
        'all_repository_prs_created_by_cutoff':len(read('all_prs.json')),
        'all_repository_prs_merged_by_cutoff':sum(bool(x['mergedAt']) and stamp(x['mergedAt'])<=stamp(cutoff) for x in read('all_prs.json')),
        'all_repository_prs_closed_unmerged_by_cutoff':sum(bool(x['closedAt']) and stamp(x['closedAt'])<=stamp(cutoff) and not x['mergedAt'] for x in read('all_prs.json')),
        'open_prs':len(read('open_prs.json')),'open_prs_stale_update_gt_48h':sum(seconds(x['updatedAt'],cutoff)>172800 for x in read('open_prs.json'))}}
    for name,rows in [('prs.csv',pr_rows),('ci_runs.csv',run_rows),('ci_jobs.csv',job_rows),('ci_test_steps.csv',step_rows),('shard_balance.csv',sharded),('required_gate.csv',required_gate),('refs.csv',refs),('worktrees.csv',worktrees)]:write_csv(out,name,rows)
    for name,value in [('summary.json',summary),('duplicate_ci.json',duplicates)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
