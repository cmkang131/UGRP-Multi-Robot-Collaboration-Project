"""Append provenance corrections beside completed native teacher originals.

Never rewrites RUN_META, scene, result, manifests, qualifications or datasets.
Retains gate_eligible=false: the formal teacher queue was absent; coordinator
accepted the measured gate in a separate recount note, not retroactive admission.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT=Path(__file__).resolve().parents[1]
B=Path('/home/ugrp/ugrp-sim')
PROFILE_SHA='a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
RUNS=(('act16w-native-gate-r2','milestone','e40ff44ce97219d075b1a58eabd48007b6f8b2ac'),
      ('act16w-native-record-r1','dev','c27a9d537eaae873c7e7bc2ceaeeada69696cc48'))


def read(p):return json.loads(p.read_text())
def append(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--coordinator-note',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    host,source=require_gcp2(training=True),frozen_source(ROOT)
    note=a.coordinator_note.read_text()
    if 'admission 없이 실행' not in note or '관문 통과를 인정' not in note:
        raise ValueError('exact separate coordinator acceptance note required')
    authority=dict(path=str(a.coordinator_note),sha256=sha256(a.coordinator_note))
    original_hashes={};annotations=[];utc=datetime.now(timezone.utc).isoformat()
    for name,classification,dispatch in RUNS:
        run=B/'runs'/name
        if not read(run/'summary.json')['complete']:raise ValueError('completed originals only')
        metas=sorted(run.glob('group-*/controller/world-*/RUN_META.json'))
        if len(metas)!=40:raise ValueError('exact40 closed worlds required')
        for meta_path in metas:
            world=meta_path.parent;scene_path=world/'scene.json'
            result=world/'result.json'
            if not result.exists():result=Path(str(result)+'.zst')
            result_value=json.loads(result.read_bytes() if result.suffix!='.zst' else subprocess.check_output(['zstd','-dc',str(result)]))
            if result_value.get('gate_eligible') is not False:
                raise ValueError('expected original formal-queue flag false')
            runtime=world.parent/'native-contact.json';contact=read(runtime)
            if (contact['profile']!='warp_native_contact_v1' or contact['profile_source_sha256']!=PROFILE_SHA
                    or contact['gpu_noslip']!=0 or set(contact['cpu_noslip'])!={0}):
                raise ValueError('actual native0 runtime proof required')
            meta=read(meta_path);scene=read(scene_path)
            evidence=[meta_path,scene_path,result,runtime]
            for path in evidence:original_hashes[str(path)]=sha256(path)
            corrected={**meta,'class':classification,'branch':'claude/act16w','pr':539,'batch':name,
                'sha':dispatch,'sha_role':'native dispatcher execution source; controller source preserved separately',
                'controller_source_sha':meta['sha']}
            value=dict(schema='ugrp.act16w.provenance_annotation.v1',created_utc=utc,annotation_source_sha=source,
                original_files=[dict(path=str(x),sha256=original_hashes[str(x)]) for x in evidence],
                original_run_metadata=meta,reported_run_metadata=corrected,
                original_scene_contact={k:scene.get(k) for k in ('cargo_contact_profile','contact_solver_profile')},
                actual_contact=dict(profile=contact['profile'],profile_source_sha256=PROFILE_SHA,
                    cpu_noslip=contact['cpu_noslip'],gpu_noslip=contact['gpu_noslip'],
                    runtime_receipt=dict(path=str(runtime),sha256=sha256(runtime))),
                formal_admission=dict(original_gate_eligible=False,teacher_gate_queue_supplied=False,
                    reason='run_warp_act_teacher executed without --teacher-gate-queue; no retroactive queue admission',
                    coordinator_acceptance=authority if classification=='milestone' else None,
                    measured_recording_gate_is_separate=classification!='milestone'),
                scope='metadata/contact-label correction only; no change to physics, scores, policy inputs, data, original qualification or gate_eligible flag')
            path=world/'act16w-native-provenance-annotation.json';append(path,value)
            annotations.append(dict(path=str(path),sha256=sha256(path)))
        path=run/'native-admission-and-provenance-note.json'
        append(path,dict(classification=classification,source_sha=source,original_gate_eligible=False,
            formal_queue_supplied=False,coordinator_acceptance=authority,
            note='native0 is measured in runtime receipts; scene.json still describes pre-application cargo_noslip_v1(10); originals retained',
            world_annotations=[x for x in annotations if str(run)+'/' in x['path']]))
        annotations.append(dict(path=str(path),sha256=sha256(path)))
    for path,expected in original_hashes.items():
        if sha256(path)!=expected:raise ValueError('original changed during annotation '+path)
    report=dict(status='complete',complete=True,host=host,source_sha=source,created_utc=utc,
        coordinator_note=authority,annotations=annotations,original_files_checked=len(original_hashes),
        originals_unchanged=True,formal_queue_flags_unchanged=True,physical_scores_changed=False)
    append(a.out,report)
    print(json.dumps(dict(status='complete',annotations=len(annotations),original_files_checked=len(original_hashes))))


if __name__=='__main__':main()
