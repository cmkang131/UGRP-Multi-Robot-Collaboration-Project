"""Join original CPU audits with scoped guard provenance on the execution VM.

No actor/physics/render calls. Partial log flags are observations, never final
outcomes. All acceptance expressions remain in the original audit modules.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('new provenance summary path required')
    hashes = {}

    def read(path):
        data = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    root = args.root
    meta = read(root/'RUN_META.json')
    arms, episodes = {}, []
    for arm in ('arm_s', 'arm_c'):
        name = arm.replace('_', '-')
        audit_path = root/('analysis-'+name)/'audit.json'
        audit = read(audit_path) if audit_path.exists() else {}
        guard_path = root/(name+'.cpu-init.json')
        guard = read(guard_path) if guard_path.exists() else None
        by_world = {row['world']: row for row in audit.get('episodes', [])}
        cpu = {row['world']: row for row in guard['episodes']} if guard else {}
        summary_path = root/name/'summary.json'
        batch = read(summary_path) if summary_path.exists() else {}
        disposition = meta['arms'][arm]['status']
        resource_path = root/(name+'.host-resource-stop.json')
        resource = read(resource_path) if resource_path.exists() else None
        for i in range(20):
            row = dict(by_world.get(i, {}), arm=arm, world=i, seed=8342000+i)
            row.setdefault('normal_complete', False)
            row.setdefault('success', None)
            row.setdefault('reason_category', meta['arms'][arm].get('reason', disposition))
            row.setdefault('funnel', None)
            row.setdefault('blocked_object', 'UNKNOWN:not_observed')
            row.setdefault('min_gap_m', None)
            row.setdefault('gap_scope', 'not measured; no obstacle identity inferred')
            row['cpu_init_mj_step_count'] = cpu[i]['cpu_init_mj_step_count'] if i in cpu else (
                0 if disposition.startswith('NOT_EXECUTED') else None)
            row['cpu_guard_phase'] = cpu[i]['phase'] if i in cpu else 'NOT_EXECUTED_OR_UNOBSERVED'
            if resource and not row['normal_complete']:
                row['original_audit_reason_category'] = row['reason_category']
                row['reason_category'] = resource['reason']
                row['resource_stop_source'] = str(resource_path)
            row['raw_dir'] = str(root/name/f'world-{i:03d}'/'raw')
            # For incomplete lanes retain the actual last stored flags/stages.
            # These are deliberately separate from the completed sequential funnel.
            log_path = Path(row['raw_dir'])/'student-eval.jsonl'
            if not row['normal_complete'] and log_path.exists():
                data = log_path.read_bytes()
                hashes[str(log_path)] = hashlib.sha256(data).hexdigest()
                lines = data.splitlines()
                try:
                    last = json.loads(lines[-1])
                    row['last_observed'] = dict(t=last.get('t'), rows=len(lines),
                        eval_passed=last.get('eval_passed'),
                        policy_stages={k: v.get('stage') for k, v in last.get('issued', {}).items()},
                        scope='stored prefix only; incomplete is not a task failure')
                except (ValueError, IndexError) as error:
                    row['last_observed_error'] = str(error)
            episodes.append(row)
        arms[arm] = dict(disposition=disposition, batch_status=batch.get('status'),
            planned_N=20, started_N=batch.get('started_N', 0), completed_N=batch.get('completed_N', 0),
            observed_normal_complete_N=audit.get('N_eff', 0),
            observed_successes=audit.get('successes'),
            original_audit_integrity_pass=audit.get('integrity_pass'),
            cpu_init_mj_step_count=guard['cpu_init_mj_step_count'] if guard else (0 if disposition.startswith('NOT_EXECUTED') else None),
            template_cpu_init_mj_step_count=guard['template']['cpu_init_mj_step_count'] if guard else (0 if disposition.startswith('NOT_EXECUTED') else None),
            host_resource_stop=resource,
            rollout_cpu_denial_events=guard['rollout_cpu_denial_events'] if guard else None,
            candidate_funnel=audit.get('candidate_funnel'), frame_funnel=audit.get('frame_funnel'),
            event_gate_funnel=audit.get('event_gate_funnel'),
            speed=audit.get('speed'), pilot=audit.get('pilot'), audit_issues=audit.get('audit_issues'))
        if guard and guard['cpu_init_mj_step_count'] != sum(r['cpu_init_mj_step_count'] for r in cpu.values()) + guard['template']['cpu_init_mj_step_count']:
            raise ValueError('CPU-init episode/arm count mismatch')
    result = dict(schema='ugrp.pair.scoped-retry-summary.v1', SIM=True, REAL=False,
        research_result=False, pooled_with_existing_study=False, classification='separate_diagnostic',
        original_audit_labels_scope='original study conventions; no confirmatory interpretation for this retry',
        raw_root=str(root), arms=arms, episodes=episodes,
        rejection_distribution=dict(Counter(r['reason_category'] for r in episodes if r.get('success') is not True)),
        source_sha256=hashes, reproduce=[sys.executable, str(Path(__file__).resolve()), '--root', str(root), '--out', 'NEW.json'])
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(arms, indent=2))


if __name__ == '__main__':
    main()
