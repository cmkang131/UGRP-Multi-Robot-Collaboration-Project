#!/usr/bin/env python3
"""Freeze the first 40 replayable stored planner requests for the paired probe.

Reads the original zstd ledger read-only (never edits another worktree) and
writes a plain JSONL copy into this experiment directory, one row per call:

    {"source_index": i, "case_id": ..., "condition": ..., "request": {"system": ..., "input": {...}}}

The stored planner bundle is text-only; ``own.rgb.source`` says "no image
supplied".  The probe attaches the one stored own-RGB frame that exists in the
same bundle to BOTH arms (the prior llmalt replay method), so the current
planner input profile (1 own RGB) is exercised without fabricating frames.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path('/Users/changmin/projects/ugrp-wt/e2e18-planner/outputs/'
              'task-planner-ling-vl-main-20261013/off-calls.jsonl.zst')
N = 40


def main() -> int:
    raw = subprocess.run(['zstd', '-dc', str(SOURCE)], check=True, capture_output=True).stdout
    rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    out = []
    for index, row in enumerate(rows[:N]):
        audit = [a for a in row.get('audit', []) if isinstance(a, dict) and 'request' in a]
        if not audit:
            raise SystemExit(f'row {index}: no audit request')
        request = audit[0]['request']
        if not isinstance(request.get('system'), str) or not isinstance(request.get('input'), dict):
            raise SystemExit(f'row {index}: request is not system+input')
        out.append({'source_index': index, 'case_id': row.get('case_id'),
                    'condition': row.get('condition'), 'domain': row.get('domain'),
                    'rule_choice': row.get('rule_choice'), 'request': request})
    text = '\n'.join(json.dumps(row, ensure_ascii=True) for row in out) + '\n'
    (HERE / 'replay_inputs.jsonl').write_text(text)
    source_meta = {
        'schema': 'ugrp.llmnomap_replay_source.v1',
        'source_path': str(SOURCE),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'decompressed_sha256': hashlib.sha256(raw).hexdigest(),
        'source_rows': len(rows),
        'selected_rows': len(out),
        'selection': 'first 40 rows with audit[0].request, in file order',
        'replay_inputs_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'case_ids': [row['case_id'] for row in out],
        'conditions': {c: sum(1 for row in out if row['condition'] == c)
                       for c in sorted({row['condition'] for row in out})},
        'image_path': 'raw/own_rgb_r80-r1-00000.jpg',
        'image_sha256': hashlib.sha256(
            (HERE / 'raw/own_rgb_r80-r1-00000.jpg').read_bytes()).hexdigest(),
        'image_usage': ('one stored own-RGB frame from the same planner bundle, attached identically '
                        'to original and variant arms; no new image was rendered or fabricated'),
        'stored_requests_have_images': False,
        'stored_own_rgb_source': 'synthetic format sample; no image supplied',
    }
    (HERE / 'replay_source.json').write_text(json.dumps(source_meta, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'selected': len(out), 'sha256': source_meta['replay_inputs_sha256'],
                      'conditions': source_meta['conditions']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
