"""Prepare NEW reloc8 smooth30->180->180 queue. No execution/network."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.prepare_selfmap6_queue import make_queue as previous
from scripts.run_self_map_diagnostic import bundle
from harness.active_relocalization import OPTION


def make_queue(source):
    q=previous(source)
    q.update(task='selfmap7-reloc8-active-own-camera',record='experiments/2026-10-15-self-map/reloc8.md',
        active_relocalization=OPTION,run_count=3,submitted=False,
        offline_verdict='SAVED_SAFETY_REPLAY_ONLY_NEW_VIEW_UNVERIFIED',
        seed_reservation=dict(seeds=[93570,93571,93572],remote_history_checked=False,
                             remote_check_required_before_submission=True))
    previous_name=None
    for run,seed in zip(q['runs'],[93570,93571,93572]):
        old=run['name'];name=f'selfmap7-smooth-{seed}-{source[:8]}'
        run.update(name=name,seed=seed,depends_on=previous_name,raw=run['raw'].replace(old,name),submitted=False)
        run['bundle']=bundle(source,seed,run['cap_sim_s'],bootstrap='command_prior_v1',
            initial_sweep='required_360_v1',recovery_profile='selfmap4_recovery_v1',
            revision_gate='selfmap4_revision_gate_v2',multiframe_registration='selfmap4_multiframe_registration_v1',
            correction_safety='selfmap6_correction_safety_v1',active_relocalization=OPTION)
        run['command']=[s.replace(old,name) for s in run['command']]
        run['command'][run['command'].index('--seed')+1]=str(seed)
        run['command']+=['--active-relocalization',OPTION]
        previous_name=name
    q['texture_deferred'].update(status='WAIT_FOR_MERGE_AND_NEW_SOURCE',ready=False,stage_ready=False,submitted=False,
        scene_version='floor_light_textured_v1',pool_with_smooth=False,code_dependency_connected=False)
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['stages']]:
        obj.update({k:False for k in ('approved','enabled','ready','stage_ready','execute','submitted')})
    q['preconditions'] += [
        'reloc8 arm/look/turn actions use own commands, static map and unresolved own-RGB hypotheses only; prediction is not registration.',
        'Retrieve >=6 own frames per first/middle/final third and every recovery capture; selected local originals are insufficient.',
        'Record candidate separation, command-prior support and next-view discrimination; safety remains selfmap6 unchanged.',
        'Serial30->review->180->review->180; first30 and every stage require explicit approval; all flags remain false.']
    return q


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();q=make_queue(a.source_sha)
    with a.output.open('x') as f:json.dump(q,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    print(json.dumps(dict(path=str(a.output),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())))


if __name__=='__main__':main()
