#!/usr/bin/env python3
"""Create a new P07 DRAFT or inspect it; no execution/registration/DB interface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import zone_e2e_manifest as plan


def write_new_draft(path, draft):
    """Exclusive file creation; never overwrite a prereg or make raw directories."""
    path = Path(path)
    raw = Path(draft['options']['raw_root']) / draft['options']['plan_id']
    if path.resolve().is_relative_to(raw.resolve()):
        raise plan.PlanError('draft file must be outside the proposed raw destination')
    text = json.dumps(draft, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
    except OSError as exc:
        raise plan.PlanError(f'draft write conflict/unavailable parent: {path}: {exc}') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('draft', help='write one new, unsealed review artifact')
    create.add_argument('--plan-id', required=True)
    create.add_argument('--output', required=True, type=Path)
    create.add_argument('--render-profile', default='shadows_v1')
    create.add_argument('--memory', default='off')
    create.add_argument('--ultrasonic-front', default='off')
    dry = commands.add_parser('dry-run', help='read only; print order/caps/leaders/raw paths/unmet gates')
    dry.add_argument('manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'draft':
            draft = plan.build_draft(plan.default_options(args.plan_id, render_profile=args.render_profile,
                                     memory=args.memory, ultrasonic_front=args.ultrasonic_front))
            summary = plan.check_draft(draft)
            write_new_draft(args.output, draft)
        else:
            summary = plan.check_draft(plan.read_json(args.manifest))
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
    except (plan.PlanError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f'P07 draft refused: {exc}\n')
    # A valid DRAFT still fails execution admission. Both commands expose this
    # without confusing structural validity with permission to start a trial.
    return 3 if summary['unmet_conditions'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
