"""Post-seal evaluation only. No controller imports this module."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,importlib.util,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/teach-return-dev-v1')
from scripts.run_teach_return_dev import SEEDS
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(l) for l in p.read_text().splitlines()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def classify(r,ret):
    if r['acquisition']['status']=='HOST_ERROR':return 'HOST_ERROR'
    if r['acquisition']['status']=='PHYSICAL_FAILURE':return 'physical_failure'
    if r['arrived'] and not r['false_declarations']:return 'success'
    if not r['goal_observed']:return 'goal_unobserved'
    if not r['B_route']:return 'disconnected_graph'
    if not r['match_accepted']:return 'entry_localization'
    if ret['failure'] or (ret['matches'] and ret['matches'][-1]['status']!='accepted'):return 'node_localization'
    if not r['correct_convergence'] or r['final_xy_m'] is None or r['final_xy_m']>.25:return 'global_localization'
    return 'path_or_budget'


def score(seed):
    ep=RAW/f'seed{seed}'
    before=module('eg49_report',ROOT/'experiments/2026-10-08-own-map-return-repeat/code/report.py')
    before.RAW=RAW;before.EXP=RAW/'evaluation'
    r=before.score(seed)  # verifies original artifact hashes before any GT reads
    graph=load(ep/'teach-graph.json');ret=load(ep/'teach-return.json');trace=rows(ep/'own-controller.jsonl')
    returns=[x for x in trace if x['stage'] in ('return','declared')];first=returns[0]['teach']['match'] if returns else None
    matched=sum(x['status']=='accepted' for x in ret['matches']);n=len(ret['matches'])
    following=sum(x['status'] in ('traversal_forward','traversal_rotate_forward') and x['command']['kind']!='hold' for x in returns)
    rotation=module('eg53_rotation',ROOT/'experiments/2026-10-09-teach-capture/code/analysis.py').rotation(ep)
    r.update(valid_teach_trial=r['acquisition']['status']=='RECORDED',B_route=ret['loss_route'] is not None,
        B_node=graph['goal_node'],nodes=len(graph['nodes']),edges=len(graph['edges']),uncertain_edges=graph['uncertain_edges'],
        first_match=first,match_accepted=matched,match_attempts=n,match_success_fraction=matched/n if n else None,
        match_reasons=dict(Counter(x['status']+'/'+x['reason'] for x in ret['matches'])),
        following_command_frames=following,return_frames=len(returns),path_use_fraction=following/len(returns) if returns else None,
        matched_nodes=len({x['node'] for x in ret['matches'] if x['status']=='accepted'}),rotation=rotation,
        return_elapsed_s=0 if not returns else r['last_truth_t']-returns[0]['t'],
        gate=bool(ret['loss_route'] is not None and first and first['status']=='accepted' and r['arrived'] and not r['false_declarations']))
    r['failure_class']=classify(r,ret)
    dump(EXP/'results'/f'{seed}.json',r)
    print(json.dumps(dict(seed=seed,arrived=r['arrived'],reason=r['failure_class'],matched=f'{matched}/{n}',end_error=r['final_xy_m'])))
    return r


def summarize(reports):
    assert len(reports)==4 and {r['seed'] for r in reports}==set(SEEDS)
    errors=[r['final_xy_m'] for r in reports if r['final_xy_m'] is not None]
    total=sum(r['match_attempts'] for r in reports);accepted=sum(r['match_accepted'] for r in reports)
    return dict(registered_new=4,physical_attempts_new=sum(r['started'] for r in reports),
        arrivals_new=sum(r['arrived'] for r in reports),false_declarations=sum(r['false_declarations'] for r in reports),
        gate_passed=sum(r['gate'] for r in reports),prior_HOST_ERROR=2,total_registered_with_prior=6,
        total_attempts_with_prior=2+sum(r['started'] for r in reports),
        failure_classes=dict(Counter(r['failure_class'] for r in reports)),
        end_error_median_m=float(np.median(errors)) if errors else None,end_error_max_m=max(errors) if errors else None,end_error_samples=len(errors),
        match_success_fraction=accepted/total if total else None,match_accepted=accepted,match_attempts=total,
        over_3sigma=sum(r['over_3sigma'] is True for r in reports),
        wall_contacts=sum(r['contacts']['wall']['episodes'] for r in reports),robot_contacts=sum(r['contacts']['robot']['episodes'] for r in reports),
        excluded=[],qualification='Four fresh DEV seeds; prior two HOST_ERROR attempts kept separately; not real hardware.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('score','aggregate'));p.add_argument('--seed',type=int,choices=SEEDS);a=p.parse_args()
    if a.mode=='score':score(a.seed)
    else:
        r=summarize([load(EXP/'results'/f'{s}.json') for s in SEEDS]);dump(EXP/'results/summary.json',r);print(json.dumps(r))
