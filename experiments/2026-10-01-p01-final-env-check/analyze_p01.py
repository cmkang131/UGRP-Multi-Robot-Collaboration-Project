#!/usr/bin/env python3
"""P01 raw -> handoff-criteria checks + TensorBoard derived views. Reads raw only (offline)."""
import argparse, collections, hashlib, json, math, re
from pathlib import Path

MAPS = ['zone_wide_door_geometry_v3', 'zone_wide_two_doors_final_v3', 'zone_wide_corridor_final_v3']
SHORT = {'zone_wide_door_geometry_v3': 'door1', 'zone_wide_two_doors_final_v3': 'door2',
         'zone_wide_corridor_final_v3': 'corridor'}
sha = lambda b: hashlib.sha256(b).hexdigest()


def jl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def check_case(root, m):
    c = root / m
    bundle = json.loads((c / 'bundle.json').read_text())
    applied = json.loads((c / 'eval_only/applied.json').read_text())
    scene = json.loads((c / 'scene.json').read_text())
    setup = json.loads((c / 'eval_only/setup.json').read_text())
    res = json.loads((c / 'result.json').read_text())
    xml = (c / 'scene.xml').read_text()
    out = {'map_id': m, 'short': SHORT[m]}
    out['map_hash_consistent'] = (bundle['map_sha256'] == applied['static_map_sha256'] == scene['static_map_sha256'])
    out['scene_xml_hash_ok'] = sha((c / 'scene.xml').read_bytes()) == scene['scene_xml_sha256'] == applied['scene_xml_sha256']
    out['robot_model'] = applied['robot_model']
    out['weld'] = bundle['weld']
    out['timestep_s'] = applied['timestep_s']
    out['noslip_iterations'] = applied['noslip_iterations']
    out['contact_profile'] = bundle['contact_profile']
    out['render_profile'] = bundle['render_profile']
    out['tag_geom_count'] = len(applied['tag_geom_names'])
    out['tag_words_in_xml'] = len(re.findall(r'tag|landmark|marker', xml, re.I))
    out['wall_height_m'] = scene['wall_profile']['height_m']
    out['wall_half_z_in_xml'] = sorted({float(s.split()[2]) for s in re.findall(r'name="[^"]*wall[^"]*"[^>]*size="([^"]+)"', xml)} or
                                       {float(s.split()[2]) for s in re.findall(r'wall[^>]*size="([^"]+)"', xml)})
    out['cameras'] = {r: {'fovy': v['fovy'], 'size': v['size']} for r, v in applied['cameras'].items()}
    out['unexpected_obstacles'] = len(setup['unexpected_obstacles'])
    # contacts (0.05 s samples, not every substep)
    n = 0; min_d = 0.0; worst = None; nonfloor = collections.Counter(); penetr_nonfloor = 0
    for row in jl(c / 'eval_only/contacts.jsonl'):
        n += 1
        for k in row['contacts']:
            pair = tuple(sorted((k['geom1'], k['geom2'])))
            is_floor = 'floor' in pair[0] or 'floor' in pair[1]
            if not is_floor:
                nonfloor[' | '.join(pair)] += 1
                if k['dist_m'] < 0: penetr_nonfloor += 1
            if k['dist_m'] < min_d: min_d, worst = k['dist_m'], [row['t'], *pair]
    out['contact_samples'] = n
    out['nonfloor_contact_rows'] = sum(nonfloor.values())
    out['nonfloor_contact_pairs'] = dict(nonfloor)
    out['min_contact_dist_mm'] = min_d * 1000
    out['min_contact_dist_pair'] = worst
    # frames / drift
    fr = {}
    drift_max = 0.0; yaw_max = 0.0; ok_all = True; nfr = 0
    for r in ('r1', 'r2', 'r3'):
        frames = jl(c / f'robots/{r}/frames.jsonl')
        labels = jl(c / f'eval_only/{r}/camera_labels.jsonl')
        hash_ok = all(sha((c / f['path']).read_bytes()) == f['sha256'] for f in frames)
        ok_all &= hash_ok; nfr += len(frames)
        p0 = labels[0]['base_position_m']; R0 = labels[0]['base_rotation']
        y0 = math.atan2(R0[1][0], R0[0][0])
        d = max(math.dist(l['base_position_m'], p0) for l in labels)
        dy = max(abs(math.degrees(math.atan2(l['base_rotation'][1][0], l['base_rotation'][0][0]) - y0)) for l in labels)
        drift_max = max(drift_max, d); yaw_max = max(yaw_max, dy)
        fr[r] = {'frames': len(frames), 'times': [round(f['t'], 3) for f in frames], 'png_hash_ok': hash_ok,
                 'unique_png_hashes': len({f['sha256'] for f in frames}),
                 'commands': len(jl(c / f'robots/{r}/commands.jsonl')),
                 'base_drift_mm': d * 1000, 'yaw_drift_deg': dy}
    out['robots'] = fr
    out['png_hash_ok_all'] = ok_all
    out['frames_total'] = nfr
    out['max_base_drift_mm'] = drift_max * 1000
    out['max_yaw_drift_deg'] = yaw_max
    out['reset_sim_s'] = res['reset_sim_s']; out['check_sim_s'] = res['check_sim_s']
    out['loadavg_start'] = res['loadavg_start']; out['loadavg_end'] = res['loadavg_end']
    out['model_calls'] = res['model_calls']; out['student_control'] = res['student_control']
    out['result_status'] = res['status']
    # handoff criteria (mechanical parts only; camera view judged visually separately)
    out['criteria'] = {
        'identity_hashes_consistent': out['map_hash_consistent'] and out['scene_xml_hash_ok'],
        'v3_model_weld_off_noslip': out['robot_model'] == 'masterpi_v3' and out['weld'] == 'off' and out['noslip_iterations'] == 10 and out['contact_profile'] == 'cargo_noslip_v1',
        'no_tag_geoms_or_textures': out['tag_geom_count'] == 0 and out['tag_words_in_xml'] == 0,
        'wall_height_0p40': abs(out['wall_height_m'] - 0.40) < 1e-9,
        'reset_le_5s': out['reset_sim_s'] <= 5.0,
        'observation_30s_exact': abs(out['check_sim_s'] - 30.0) < 1e-6,
        'no_initial_nonfloor_contact': out['nonfloor_contact_rows'] == 0 and penetr_nonfloor == 0,
        'drift_lt_1mm_and_0p1deg': drift_max * 1000 < 1.0 and yaw_max < 0.1,
        'png_hashes_match': ok_all,
        'student_commands_and_model_calls_zero': out['model_calls'] == 0 and out['student_control'] is False,
    }
    out['mechanical_criteria_pass'] = all(out['criteria'].values())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True, type=Path)   # .../p01
    ap.add_argument('--out', required=True, type=Path)   # analysis json dir (experiment)
    ap.add_argument('--derived', required=True, type=Path)  # derived views root (outputs)
    ap.add_argument('--source-sha', required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    allc = {}
    for m in MAPS:
        r = check_case(a.raw, m)
        allc[m] = r
        (a.out / f'{SHORT[m]}.json').write_text(json.dumps(r, indent=1) + '\n')
        src = a.raw / m / 'result.json'
        view = {
            'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
            'offline_source': {'path': str(src.resolve()), 'sha256': sha(src.read_bytes())},
            'offline_scalar_scope': 'P01 reset/stationary 30 SIM s 자료의 오프라인 기계 점검(접촉 0.05 s 표본·관측 7프레임 기준). 환경 적합 PASS도 로봇 임무 성공도 아님.',
            'family': 'p01_final_env', 'policy': 'none_stationary', 'case': SHORT[m], 'condition': 'v84_default_render',
            'contact_profile': 'cargo_noslip_v1', 'seed': 911, 'source_sha': a.source_sha, 'clock': 'sim',
            'outcome': 'COLLECTED_UNQUALIFIED', 'scope': 'reset+30s stationary collection; 0 model calls; no controller',
            'sim_s': r['reset_sim_s'] + r['check_sim_s'], 'commands': sum(v['commands'] for v in r['robots'].values()), 'model_calls': 0,
            'offline_scalars': {
                'offline/reset_sim_s': r['reset_sim_s'], 'offline/observe_sim_s': r['check_sim_s'],
                'offline/nonfloor_contact_rows': r['nonfloor_contact_rows'],
                'offline/min_contact_dist_mm': r['min_contact_dist_mm'],
                'offline/max_base_drift_mm': r['max_base_drift_mm'], 'offline/max_yaw_drift_deg': r['max_yaw_drift_deg'],
                'offline/tag_geom_count': r['tag_geom_count'], 'offline/frames_saved': r['frames_total'],
                'offline/png_hash_ok': int(r['png_hash_ok_all']), 'offline/wall_height_m': r['wall_height_m'],
                'offline/loadavg_start': r['loadavg_start'][0],
                'gate/mechanical_criteria_pass': int(r['mechanical_criteria_pass'])},
            'success': r['mechanical_criteria_pass'],
            'success_definition': 'P01 handoff의 기계적 점검(해시 일치·v3/weld off/noslip·표식 0·벽 0.40 m·reset<=5 s·관측 30 s·초기 접촉/관통 0·정지 drift·PNG 해시). 카메라 시야 판정과 환경 적합(PASS)·임무 성공은 포함하지 않음.',
            'hparam_metrics': ['offline/nonfloor_contact_rows', 'offline/max_base_drift_mm', 'offline/min_contact_dist_mm', 'result/sim_s'],
        }
        d = a.derived / SHORT[m]
        d.mkdir(parents=True, exist_ok=False)
        (d / 'result.json').write_text(json.dumps(view, indent=1) + '\n')
    (a.out / 'summary.json').write_text(json.dumps({m: {'pass': v['mechanical_criteria_pass'], 'criteria': v['criteria']} for m, v in allc.items()}, indent=1) + '\n')
    print(json.dumps({SHORT[m]: v['mechanical_criteria_pass'] for m, v in allc.items()}))


main()
