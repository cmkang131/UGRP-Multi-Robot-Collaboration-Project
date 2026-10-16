"""Produce the small final record from terminal, integrity-verified rounds."""
import collections
import hashlib
import json
import platform
import subprocess
from pathlib import Path

R = Path('/home/ugrp/ugrp-sim/runs')


def obj(p):
    return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-dc', str(p)+'.zst']))


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    out = R/'reloc20-delivery'
    out.mkdir(exist_ok=False)
    reports, records, sources = [], [], []
    for n in (1, 2, 3):
        b = R/f'reloc20-round{n}'
        assert (b/'DONE').exists()
        d = obj(b/'summary.json')
        assert all(x['integrity']['verified'] for x in d['integrity'])
        reports.append(dict(round=n, source_sha=obj(b/'queue.json')['source_sha'], speed=d['speed'],
                            files_verified=sum(x['integrity']['files'] for x in d['integrity'])))
        for name in ('summary.json', 'rejection-table.json', 'queue.json', 'speed-gate.json', 'full-plan-audit.json'):
            p = b/name
            if not p.exists():
                p = Path(str(p)+'.zst')
            if not p.exists():
                continue
            sources.append(dict(path=str(p), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        for x in d['runs']:
            record = {k: x[k] for k in (
                'name', 'source_sha', 'kind', 'condition', 'seed', 'raw', 'status',
                'termination', 'termination_normalized', 'sim_s', 'place_success', 'lift',
                'phase', 'input_audit', 'errors', 'aligned_command_errors', 'phase_metrics',
                'gate_cumulative', 'acquisition_frame_funnel', 'acquisition_frame_rejections',
                'geometry_risk_intervals', 'geometry_risk_sim_s', 'geometry_scope',
                'route_frame_rejections', 'visual_stall_frame_reasons', 'visual_stall_intervals',
                'lateral_pulse_ticks', 'drivetrain_evaluation', 'drive_errors', 'registered_errors',
                'registration_frame_funnel', 'known_mode_measurement_funnel', 'gate_reasons',
                'failure_six', 'error') if k in x}
            record['round'] = n
            # The generic interval helper used 0 only as a grouping sentinel.
            # Pixel stationarity cannot identify a metric obstacle clearance.
            record['visual_stall_intervals'] = [dict(i, category='visual_stall',
                blocked_object='unidentified_own_rgb_stall', minimum_gap_m=None,
                gap_scope='not_observed_pixel_stationarity_only') for i in x.get('visual_stall_intervals', [])]
            original = obj(Path(x['raw'])/'result.json')
            record['raw_terminal_reason'] = original.get('termination_reason', original.get('termination_category'))
            record['error'] = original.get('error', record.get('error'))
            if original.get('status') == 'HOST_ERROR':
                record['failure_class'] = ('controller_relocalization_exhausted' if 'selfmap4_relocalization_exhausted' in str((record['error'], record['raw_terminal_reason']))
                                           else 'precontrol_configuration' if original.get('sim_s') is None else 'unclassified_HOST_ERROR')
            motion = x.get('reloc20_motion') or {}
            record['motion_final'] = {k: v for k, v in motion.items() if k not in ('footprint', 'stall')}
            stall = motion.get('stall') or {}
            record['stall_enabled'] = bool(motion.get('stall'))
            record['motion_final']['stall'] = {k: stall[k] for k in ('stall_ticks', 'stall_sim_s', 'recovering', 'metric_vo', 'rotation_stationarity_v1') if k in stall}
            footprint = motion.get('footprint') or {}
            record['route_funnel'] = footprint.get('plan_funnel')
            record['route_rejections'] = footprint.get('rejections')
            record['stall_count'] = len(x.get('visual_stall_intervals', []))
            record['stall_sim_s'] = sum(i['sim_s'] for i in x.get('visual_stall_intervals', []))
            records.append(record)
    carry = [x for x in records if x['kind'] == 'carry']
    physical = [x for x in carry if x.get('errors')]
    measured = [x for x in records if x.get('input_audit')]
    report = dict(schema='ugrp.reloc20.delivery.v1', status='NOT_READY',
                  analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scope='three finite gcp2 DEV rounds; repeated seeds and differing sources are not independent cohorts; no hardware validation',
                  rounds=reports, attempts=len(records), carry_attempts=len(carry),
                  carry_control_started=len(physical), place_success=sum(x.get('place_success') is True for x in physical),
                  terminations=dict(collections.Counter(x.get('termination_normalized') for x in records)),
                  input_audit=dict(measured_runs=len(measured), unmeasured_runs=[x['name'] for x in records if not x.get('input_audit')],
                                   invisible_measurements=sum(x['input_audit']['invisible_measurements'] for x in measured),
                                   held_world_reads=sum(x['input_audit']['held_world_reads'] for x in measured)),
                  metric_scope='full-run authored-frame command shadow vs RGB/stall-corrected posterior, plus carry/destination phase distributions. Different coverage prevents causal full-route improvement claims.',
                  sources=sources, runs=records)
    (out/'summary.json').write_text(json.dumps(report, separators=(',', ':'))+'\n')
    lines = ['|R/조건|seed|종료|place|보정 xy 중앙/p95(m)|명령 xy 중앙/p95(m)|보정/명령 yaw p95(°)|RGB 막힘 구간/초|평가 기하 위험 초|횡펄스|',
             '|---|---|---|---|---|---|---|---|---|---|']
    def value(e, key, pct):
        return f"{e[key][pct]:.3f}" if pct in e.get(key, {}) else '—'
    for x in carry:
        e = x.get('errors', {})
        stall_cell = f"{x['stall_count']}/{x['stall_sim_s']:.1f}" if x['stall_enabled'] else 'off/미측정'
        lines.append(f"|{x['round']}/{x['condition']}|{x['seed']}|{x.get('termination_normalized')}|{int(x.get('place_success') is True)}|"
                     f"{value(e,'xy','p50')}/{value(e,'xy','p95')}|{value(e,'command_xy','p50')}/{value(e,'command_xy','p95')}|"
                     f"{value(e,'yaw','p95')}/{value(e,'command_yaw','p95')}|{stall_cell}|"
                     f"{x.get('geometry_risk_sim_s',0):.1f}|{x.get('lateral_pulse_ticks','—')}|")
    (out/'metrics.md').write_text('\n'.join(lines)+'\n\n기하 위험은 평가 SAT proxy이며 접촉력·RGB 막힘 판정과 다르다. precontrol HOST_ERROR의 0초는 관측 부재다. 기준선 RGB 막힘 검사는 off이므로 미측정이다.\n')
    manifest = {p.name: dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir() if p.is_file()}
    (out/'retrieval-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(status=report['status'], attempts=len(records), carry_control_started=len(physical), audits=report['input_audit'])))


if __name__ == '__main__':
    main()
