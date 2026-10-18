"""Raw pilot recount, all native JPEG equality, and measured disk budget."""
from pathlib import Path
import hashlib,json,math,shutil,subprocess
from harness.beampair_recording import existing
from harness.grasp_act_data import read_json,sha256,write_json

ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair8'
SOURCE='72c0e83dab384b4f7d4bb73e37e440e0d1b248f6'


def main():
    proof=read_json(OPS/'identity-proof-72c0e83d.json');assert proof['passed'] and len(proof['runs'])==4
    jpeg=[];sizes=[]
    for row in proof['runs']:
        run=Path(row['path']);old=ROOT/'runs'/f"beampair8-identity-{row['seed']}-ce7438b4"
        images=sorted((run/'raw/rgb').rglob('*.jpg'));before=sorted((old/'raw/rgb').rglob('*.jpg'))
        assert len(images)==len(before)
        assert all(sha256(p)==sha256(old/'raw/rgb'/p.relative_to(run/'raw/rgb')) for p in images)
        jpeg.append(dict(seed=row['seed'],N=len(images),matching=len(images),different=0))
        seen=set();physical=0;decoded_overhead=0
        for p in run.rglob('*'):
            if not p.is_file():continue
            st=p.stat();key=(st.st_dev,st.st_ino)
            if key not in seen:physical+=st.st_size;seen.add(key)
            if p.name.endswith(('.json.zst','.jsonl.zst')):
                decoded_overhead+=max(0,len(subprocess.check_output(['zstd','-qdc',str(p)]))-st.st_size)
        r=read_json(existing(run/'raw','result.json'))
        sizes.append(dict(seed=row['seed'],sim_s=r['sim_s'],unique_inode_bytes=physical,
            decoded_text_overhead_bytes=decoded_overhead,
            cap60_peak_estimate=(physical+decoded_overhead)*60/r['sim_s']))
    write_json(OPS/'jpeg-cache-equivalence.json',dict(passed=True,runs=jpeg,N=sum(x['N'] for x in jpeg),different=0))
    # Existing storage_budget estimator uses a25% margin. Native image sizes
    # and full decoded JSON are measured; cap60 rather than successful length.
    per_run=math.ceil(max(x['cap60_peak_estimate'] for x in sizes)*1.25)
    # Upper bound, retaining every frame (even before handoff):600ticks x2actors
    # x240x320x3 uint8 plus uncompressed context/action/indices/JSON per row.
    # Archive+unpacked temporarily coexist, so reserve twice the full bound.
    pixels=600*2*240*320*3
    metadata=600*2*((252+8*14+8+4)*8+1024)
    dataset_workspace=200*2*(pixels+metadata)
    others={p.name:read_json(p) for p in (ROOT/'leases').glob('*.json') if p.name!='beampair8.json'}
    # Existing beampair7/release queue's256MiB per-run cap estimate. Read the
    # active release gate progress; reserve at least a complete40-run gate if
    # its newly claimed lease has not yet written progress. Reloc17 round4.
    release_remaining=0
    for p in (ROOT/'ops-reviews/release25').glob('*/progress.json'):
        if 'gate' not in p.parent.name:continue
        v=read_json(p);release_remaining=max(release_remaining,len(v.get('running',[]))+len(v.get('not_started',[])))
    if 'release25.json' in others:release_remaining=max(release_remaining,40)
    reloc_remaining=others.get('reloc17.json',{}).get('concurrency',0)
    other_bytes=(release_remaining+reloc_remaining)*256*1024**2
    free=shutil.disk_usage(ROOT).free;expected=200*per_run+dataset_workspace+other_bytes
    budget=dict(ok=free-expected>=8*1024**3,source_sha=SOURCE,pilots=sizes,per_run_budget_bytes=per_run,
        recording_N=200,recording_bytes=200*per_run,dataset_archive_workspace_bytes=dataset_workspace,
        dataset_bound_basis='600 ticks per60SIMs *2actors *uint8(3,240,320), every frame + explicit metadata bytes; archive and expanded copy coexist',
        other_leases=others,other_remaining_runs=dict(release25=release_remaining,reloc17=reloc_remaining),
        other_reserved_bytes=other_bytes,other_basis='existing256MiB per-run queue estimate; release full40 over-reservation includes completed runs',
        free_bytes=free,expected_bytes=expected,projected_free_bytes=free-expected,floor_bytes=8*1024**3,
        arm='not used; gcp2-only task, no ARM transfers',mac='summary/montage only, checked separately')
    assert budget['ok'];write_json(OPS/'storage-budget.json',budget)
    table=ROOT/'ops-reviews/beampair7/rejection_table.json';plan=OPS/'train-plan.json'
    q=dict(stage='record',source_sha=SOURCE,pr=537,status='APPROVED_PINNED',max_parallel=16,
        plan=str(plan),plan_sha256=sha256(plan),episodes=list(range(200)),
        rejection_table=str(table),rejection_table_sha256=sha256(table),
        identity_proof=str(OPS/'identity-proof-72c0e83d.json'),storage_budget=str(OPS/'storage-budget.json'),
        batch=str(OPS/'record200-72c0e83d'),per_run_budget_bytes=per_run,
        disk_floor_bytes=8*1024**3+dataset_workspace+other_bytes,
        continue_on_teacher_failure=True,
        failure_policy='user explicitly requested200 attempts, excluding failed teacher episodes from data but retaining ledger; no tuning/repair of teacher in this batch',
        heldout_plan=str(OPS/'heldout-plan.json'),heldout_recording=False,
        supervisor_path=str(OPS/'queue_record.py'),supervisor_sha256=sha256(OPS/'queue_record.py'))
    write_json(OPS/'record-queue.json',q)
    print(json.dumps(dict(jpeg_N=sum(x['N'] for x in jpeg),per_run_mib=per_run/1024**2,
        projected_free_gib=budget['projected_free_bytes']/1024**3,other_reserved=other_bytes/1024**3)))


if __name__=='__main__':main()
