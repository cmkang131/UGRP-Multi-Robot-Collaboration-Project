"""Recount raw v7 Score and actual XML options/appearance; never step physics."""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act17_open_loop import read
from act17_compact_records import original_sha256
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_v7 import ROOT,T,PROFILE,SCENE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT)
    sys.path.insert(0,str(T))
    from sim.grasp_act_solo_evaluation import Score
    summary=read(a.run/'gate-recount.json')
    if not summary['complete'] or summary.get('cohort')!='act17-v7-native':raise ValueError('completed new v7 stage required')
    rows=[];all_files=0
    for group in sorted(a.run.glob('group-*')):
        controller=group/'controller';raw_manifest=read(controller/'summary.json')
        for name,digest in raw_manifest['sha256'].items():
            if original_sha256(controller/name)!=digest:raise ValueError('closed controller manifest changed')
            all_files+=1
        for folder in sorted(controller.glob('world-*')):
            if not folder.is_dir():continue
            plan=read(folder/'plan.json');original=read(folder/'result.json');samples=read(folder/'eval-only.jsonl',lines=True)
            model=ET.fromstring((folder/'scene.xml').read_text());options=model.find('option').attrib
            if options.get('noslip_iterations')!='0' or options.get('cone')!='elliptic' or options.get('integrator')!='implicitfast' or options.get('impratio')!='5':
                raise ValueError('actual native contact options differ')
            cargo=[b.get('name') for b in model.findall('.//body') if b.get('name','').startswith('cargo_')]
            if any(any(token in name for token in ['_can','_tile','_crate','_frame']) for name in cargo):
                raise ValueError('retired cargo remains in actual v7 scene')
            fields={e.get('name'):e.get('data') for e in model.findall('custom/text')}
            if fields.get('scene_profile')!=SCENE or fields.get('end_color_scene')!=PROFILE:
                raise ValueError('actual scene profile declaration missing')
            colors={g.get('name'):g.get('rgba') for g in model.findall('.//geom') if g.get('name','').startswith('cargo_beam_1__band_')}
            if colors and (tuple(map(float,colors.get('cargo_beam_1__band_neg','').split()))!=(.02,.95,.60,1.) or tuple(map(float,colors.get('cargo_beam_1__band_pos','').split()))!=(.02,.02,.95,1.)):
                raise ValueError('actual long-beam end colors differ')
            score=Score();n=0
            for sample in samples:
                if 'min_z' not in sample:continue
                score.add(sample['t'],**{k:sample[k] for k in ['min_z','support_z','tilt_deg','finger_forces','speed','open_issued','placement_offset','weld_active']});n+=1
            recalculated=score.record(original['teacher']['command_result']=='command_complete')
            if not n or any(original[k]!=v for k,v in recalculated.items()):raise ValueError('recomputed Score differs')
            audit=original['input_audit']
            if any(audit[k] for k in ['invisible_measurements','held_world_reads']):raise ValueError('teacher input leak')
            proof=dict(classification='milestone' if summary['passed'] else 'dev',pr=539,branch='claude/act16w',
                cohort='act17-v7-native',adapter_source_sha=summary['source_sha'],audit_source_sha=source,
                scenario_version='v7',cargo_version='v6',actual_cargo_bodies=cargo,end_color_scene=PROFILE,
                actual_beam_band_colors=colors,beam_present=bool(colors),scene_profile=SCENE,
                contact_profile='warp_native_contact_v1',actual_XML_options=options,
                legacy_metadata_note='base grasp_act_scene.colors=off and cargo_noslip_v1 may describe the input before the ACT17/native XML adapters; this proof records final XML and runtime native-contact.json',
                scene_xml_sha256=sha256(folder/'scene.xml'),plan_sha256=sha256(folder/'plan.json'),
                actual_native_runtime=read(controller/'native-contact.json'),input_audit=audit,
                physics_steps=0,score_matches=True)
            proof_path=folder/'act17-effective-runtime.json'
            with proof_path.open('x') as f:json.dump(proof,f,indent=2)
            rows.append(dict(seed=plan['seed'],kind=plan['kind'],success=original['physical_success'] and original['status']=='complete' and not original['cap_end'],
                score_matches=True,samples=n,runtime_proof=dict(path=str(proof_path),sha256=sha256(proof_path))))
    if len(rows)!=summary['N'] or sum(r['success'] for r in rows)!=summary['n']:raise ValueError('independent stage count differs')
    report={**summary,'independent_v7_audit':dict(source_sha=source,host=host,rows=rows,manifest_files_verified=all_files,
        source_score_sha256=sha256(T/'sim/grasp_act_solo_evaluation.py'),physics_steps=0,rendered_frames=0,
        scope='original Score, final scene XML, native options and input boundary audits; no CPU physical success claim')}
    with a.out.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(n=report['n'],N=report['N'],passed=report['passed'],verified_files=all_files)))


if __name__=='__main__':main()
