"""Assemble local, reviewable records from gcp2 summaries; no raw mutation."""
import json,pathlib
root=pathlib.Path(__file__).resolve().parents[3];b=root/'experiments/2026-10-16-beampair6'
read=lambda n:json.loads((b/n).read_bytes())
r=read('r1-summary.json');c=read('placement-validity.json');table=read('r1-rejection_table.json');first=read('r1-first30.json');integrity=read('r1-integrity.json')
assert [e['seed'] for e in r['runs']]==[8318726,8318620,8318600,8318604,8318611,8318631]
passed=(r['N']==r['n']==6 and not any(r[k] for k in ('cap_end_N','incomplete_N','held_world_reads','invisible_measurements','missing_rejection_audit_N')))
status='READY_HOLD_SCENE' if passed else 'NOT_READY'
table.update(schema='ugrp.beampair6.rejection_table.v1',status=status,branch='A',
    placement_validity=str((b/'placement-validity.json').resolve()),placement_validity_csv=str((b/'placement-validity.csv').resolve()),
    pre_edit_rejection_table=str((b/'rejection_table-before.json').resolve()),
    setup_funnel=str((b/'setup-funnel.json').resolve()),setup_rejections_with_scene_names=str((b/'setup-rejections-resolved.json').resolve()),
    population_note='setup proposals / seeded target ends / candidates / frames / protocol events / episodes are separate denominators')
(b/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
summary=dict(schema='ugrp.beampair6.summary.v1',status=status,branch='A',
    source_sha=r['source_sha'],generator_source_sha='7facb60b921e80831ad50a20a8ae2ee89d0d2b25',dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247',
    host='gcp2',project='ugrp-sim-b-1014',machine_type='n4-highcpu-64',scenario_source_sha=c['scenario_source_sha'],
    placement_census=dict(v7_unique_beams=7,v7_seeded_ends_N=42,v7_distribution=c['v7_distribution'],v7_inserted_fixed_event_seeded_ends_N=6,v7_event_distribution={'91':6},
        old_gate_N=40,old_gate_ends_N=80,old_gate_distribution=c['gate_distribution'],original_8318626='out_of_research_placement_support; original preserved and not rerun',k=91,k_basis=c['k_basis'],
        new_gate_seed_range=[8318700,8318739],new_gate_N=40,new_gate_ends_distribution={'91':80},new_setup_recheck_N=40),
    toggles=dict(setup='beampair_gate_valid_v2',wall_layer='beampair_wall_clear_v1',approach_repair='beampair_approach_v2',peer_rendezvous='peer_rendezvous_v2',default='off',planning='search24_checks_v1 + search25_checks_v1',failure_tail='recording-only last10SIMs at10Hz'),
    scene='cargo_v7 / grasp_act_teal_blue_v1 / floor_light_v1',held_object_hidden_v1=True,weld=False,training=False,LLM_calls=0,
    rounds_executed=1,round_limit=3,planned_N=6,started_N=r['N'],successful_N=r['n'],unstarted_N=r['unstarted_N'],HOST_ERROR_N=r['HOST_ERROR_N'],cap_end_N=r['cap_end_N'],
    invisible_measurements=r['invisible_measurements'],held_world_reads=r['held_world_reads'],missing_rejection_audit_N=r['missing_rejection_audit_N'],
    runs=r['runs'],first30=first,wall_layer=r['wall_layer'],
    integrity=dict(raw_manifest_files=sum(v['raw_manifest_verified'] or 0 for v in integrity),adapter_manifest_files=sum(v['adapter_manifest_verified'] or 0 for v in integrity),detail='r1-integrity.json'),
    gate40=dict(status='HOLD_SCENE' if passed else 'not_created',ready=False,approved=False,submitted=False,measured_N=0,max_parallel=16,training=False,rejection_table=str((b/'rejection_table.json').resolve())),
    tests=dict(scope='nonphysics targeted8',passed=8,failed=0,command='/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_beampair6.py tests/test_beampair5.py'),
    limits=['All v7 authored initial beams exhaustively checked; gate v1 is a finite40-seed sample, not an analytic continuous RNG distribution.',
            'Placement table checks existing chassis goal geometry against map fixed obstacles; runtime still checks path, body/arm sweep, view and protocol.',
            'Short6 are mixed new-placement sentinel plus seen regressions, never counted as gate40 research samples.',
            'No student, training, transport, release or hardware result; no results from earlier teachers/gcp1 pooled.',
            '16-concurrent speed and scene approval remain pending; VM scheduling was24h, command cap8h; no VM guard modified.',
            'Raw stays only on gcp2 persistent disk; this is not a separate raw backup.',
            'Wall clear toggle enabled but activated0/12 robot-runs; clearing path has no new physical coverage in short6.'])
(b/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(status=status,N=r['N'],n=r['n'],cap_end_N=r['cap_end_N'],manifest_files=summary['integrity'])))
