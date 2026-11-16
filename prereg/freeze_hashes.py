#!/usr/bin/env python3
"""Freeze record for the UGRP team-structure study (standard library only).

  python3 freeze_hashes.py                  write FREEZE-HASHES.json next to this script (the real freeze, run once)
  python3 freeze_hashes.py --out PATH       write the record to PATH instead (trial runs)
  python3 freeze_hashes.py --check          compare the files now with the record (default FREEZE-HASHES.json)
  python3 freeze_hashes.py --check --out P  compare with the record at P
Exit codes: 0 same/written, 1 --check found differences, 2 error (missing file or symbol, bad record).

Records: git HEAD and dirty state of this repository, sha256 of every tracked harness/ and scripts/ file,
planner files, the prompt-building source segments (found with ast, never imported), scene files, analysis tools and
the two documents. The time of recording is shown in KST but is NOT compared by --check.
It reads files only. It runs no simulation, calls no LLM, uses no network.
Not covered (cannot be read from this host): the run script and ACT checkpoint on the work VMs.
"""
import argparse
import ast
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent          # repository root
WT = ROOT                   # the runner code (harness/, scripts/) is in this repository
BR = ROOT / 'team'          # the planner: brain_server.py and brain/
KST = datetime.timezone(datetime.timedelta(hours=9))
DEFAULT_OUT = HERE / 'FREEZE-HASHES.json'

PLANNER_FILES = sorted(['brain_server.py', 'brain/__init__.py', 'brain/llm.py', 'brain/planning.py'])
SCENE_FILES = [ROOT / 'scenes/scenes_designed_v2.json',
               ROOT / 'scenes/scenes_random_v2.json',
               ROOT / 'scenes/scenes_coop.json']
ANALYSIS_FILES = [ROOT / 'analysis/compare.py',
                  ROOT / 'analysis/causes.py',
                  ROOT / 'analysis/analyze_main.py']
DOCUMENT_FILES = [HERE / 'PREREG.md', HERE / 'FREEZE-CHECKLIST.md']

# Prompt-building source: (file, [top-level names or Class.method]). A missing name is a hard error, not a skip.
PROMPT_SEGMENTS = [
    (BR / 'brain/planning.py', ['HEAD', 'T0_HEAD_DROPS', 'SEEDS', 'FINAL', 'TABLES',
                                'PlanningPolicy.__init__', 'PlanningPolicy._progress', 'PlanningPolicy._prompt',
                                'PlanningPolicy._recent', 'PlanningPolicy._label', 'PlanningPolicy._candidate',
                                'PlanningPolicy._menu', 'PlanningPolicy._select']),
    (BR / 'brain/__init__.py', ['PLANNER_VERSION', 'RECEIVED_WINDOW', 'OWN_WINDOW', 'message_body', '_Planner',
                                'TeamBrain._recipients', 'TeamBrain._receive', 'TeamBrain.decide',
                                'MESSAGE_RULE', 'CHANCE_NOTE', 'TeamBrain.chance']),
    (BR / 'brain_server.py', ['GOAL', 'run_ceiling', 'parse_args', 'main']),
    (BR / 'brain/llm.py', ['HARD_EPISODE_CALLS', 'HARD_CAMPAIGN_USD', 'RealLLM.__init__', 'RealLLM._call_once']),
    (WT / 'scripts/run_team_carry.py', ['ZONES', 'SIGN_ZONES', 'SIGN_RECT', 'RETHINK_S', 'DEST_LISTEN_S',
                                        'CAPABLE_COLOURS', 'REDECIDE_POLL_S', 'REDECIDE_MAX_ASKS',
                                        'OTHER_ROBOT_OUTCOMES', 'FixedPlan', 'RemoteBrain', 'room_of', 'box_label',
                                        'relation_text', 'box_where', 'carry_end_text', 'capability_text',
                                        'destination_options', 'hooks']),
]
NOT_COVERED = ['run script and ACT checkpoint on the work VMs',
               'the model provider side (system prompt, routing), OpenRouter account state']


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def hash_files(paths, base):
    """{relative name: sha256 or 'MISSING'}"""
    result = {}
    for path in paths:
        path = Path(path)
        name = str(path.relative_to(base)) if base in path.parents else str(path)
        result[name] = sha256_file(path) if path.is_file() else 'MISSING'
    return result


def git(*args):
    done = subprocess.run(['git', '-C', str(WT)] + list(args), capture_output=True, check=True)
    return done.stdout.decode('utf-8', 'replace')


def git_state():
    lines = [l for l in git('status', '--porcelain').splitlines() if l.strip()]
    return {'worktree': '<repository root>', 'head': git('rev-parse', 'HEAD').strip(),
            'head_tree': git('rev-parse', 'HEAD^{tree}').strip(),
            'dirty_lines': sorted(lines),
            'dirty_non_pyc_lines': sorted(l for l in lines if not l.rstrip().endswith('.pyc'))}


def integration_hashes():
    names = git('ls-files', '-z', '--', 'harness', 'scripts').split('\0')
    names = sorted(n for n in names if n and not n.endswith('.pyc') and '__pycache__' not in n)
    return {n: (sha256_file(WT / n) if (WT / n).is_file() else 'MISSING') for n in names}


def find_node(tree, dotted):
    parts = dotted.split('.')
    body = tree.body
    node = None
    for index, part in enumerate(parts):
        node = None
        for item in body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and item.name == part:
                node = item
            elif isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == part for t in item.targets):
                node = item
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.target.id == part:
                node = item
            if node is not None:
                break
        if node is None:
            return None
        body = getattr(node, 'body', []) if index < len(parts) - 1 else body
    return node


def prompt_segments():
    """({'file::name': {sha256, lines}}, [missing 'file::name'])"""
    result, missing = {}, []
    for path, names in PROMPT_SEGMENTS:
        label = str(path.relative_to(ROOT))
        if not path.is_file():
            missing += [label + '::' + n for n in names]
            continue
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for name in names:
            node = find_node(tree, name)
            key = label + '::' + name
            if node is None:
                missing.append(key)
                continue
            segment = ast.get_source_segment(source, node)
            result[key] = {'sha256': sha256_text(segment), 'lines': '%d-%d' % (node.lineno, node.end_lineno)}
    return result, missing


def build_record():
    segments, missing = prompt_segments()
    record = {
        'schema': 'ugrp-freeze-v1',
        'recorded_kst': datetime.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST'),
        'python': sys.version.split()[0],
        'freeze_hashes_py_sha256': sha256_file(Path(__file__).resolve()),
        'git': git_state(),
        'integration_files': integration_hashes(),
        'planner_files': hash_files([BR / n for n in PLANNER_FILES], BR),
        'prompt_segments': segments,
        'scene_files': hash_files(SCENE_FILES, ROOT),
        'analysis_tools': hash_files(ANALYSIS_FILES, ROOT),
        'documents': hash_files(DOCUMENT_FILES, HERE),
        'not_covered': NOT_COVERED,
    }
    record['prompt_templates_sha256'] = sha256_text(
        json.dumps({k: v['sha256'] for k, v in sorted(segments.items())}, sort_keys=True))
    return record, missing


def flatten(record):
    """{key: comparable value}. The recording time and line ranges are not compared."""
    flat = {'git.head': record['git']['head'], 'git.head_tree': record['git']['head_tree'],
            'git.dirty_non_pyc_lines': json.dumps(record['git']['dirty_non_pyc_lines']),
            'prompt_templates_sha256': record['prompt_templates_sha256']}
    for group in ('integration_files', 'planner_files', 'scene_files', 'analysis_tools', 'documents'):
        for name, value in record[group].items():
            flat[group + ':' + name] = value
    for name, value in record['prompt_segments'].items():
        flat['prompt_segments:' + name] = value['sha256']
    return flat


def compare(old, new):
    old_flat, new_flat = flatten(old), flatten(new)
    diffs = []
    for key in sorted(set(old_flat) | set(new_flat)):
        if key not in new_flat:
            diffs.append(('removed', key, old_flat[key], ''))
        elif key not in old_flat:
            diffs.append(('added', key, '', new_flat[key]))
        elif old_flat[key] != new_flat[key]:
            diffs.append(('changed', key, old_flat[key], new_flat[key]))
    return diffs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT, help='record file to write (or to read with --check)')
    parser.add_argument('--check', action='store_true', help='compare the files now with the record; exit 1 on differences')
    args = parser.parse_args(argv)
    try:
        record, missing = build_record()
    except (OSError, subprocess.CalledProcessError, SyntaxError) as error:
        print('ERROR: %s: %s' % (type(error).__name__, error), file=sys.stderr)
        return 2
    if args.check:
        try:
            old = json.loads(args.out.read_text(encoding='utf-8'))
            flatten(old)
        except (OSError, ValueError, KeyError) as error:
            print('ERROR: cannot read the record %s: %s' % (args.out, error), file=sys.stderr)
            return 2
        diffs = compare(old, record)
        for name in missing:
            diffs.append(('missing-symbol', name, '', 'not found now'))
        print('record: %s (recorded %s, HEAD %s)' % (args.out, old.get('recorded_kst'), old['git']['head'][:7]))
        print('now:    HEAD %s' % record['git']['head'][:7])
        if not diffs:
            print('SAME: %d integration files, %d prompt segments, %d other files unchanged'
                  % (len(record['integration_files']), len(record['prompt_segments']),
                     sum(len(record[g]) for g in ('planner_files', 'scene_files', 'analysis_tools', 'documents'))))
            return 0
        print('DIFFERENT: %d item(s)' % len(diffs))
        for kind, key, before, after in diffs:
            print('  %-14s %s  %s -> %s' % (kind, key, before[:12] or '-', after[:12] or '-'))
        return 1
    if missing:
        print('ERROR: prompt-building symbols not found (renamed? fix PROMPT_SEGMENTS, then freeze):', file=sys.stderr)
        for name in missing:
            print('  ' + name, file=sys.stderr)
        return 2
    absent = [g + ':' + n for g in ('planner_files', 'scene_files', 'analysis_tools', 'documents')
              for n, v in record[g].items() if v == 'MISSING']
    if absent:
        print('ERROR: files missing: ' + ', '.join(absent), file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    git = record['git']
    print('wrote %s at %s' % (args.out, record['recorded_kst']))
    print('git HEAD %s, dirty lines %d (non-.pyc %d)' % (git['head'][:7], len(git['dirty_lines']),
                                                       len(git['dirty_non_pyc_lines'])))
    print('hashed: %d integration files, %d planner files, %d prompt segments, %d scene files, %d analysis tools, %d documents'
          % (len(record['integration_files']), len(record['planner_files']), len(record['prompt_segments']),
             len(record['scene_files']), len(record['analysis_tools']), len(record['documents'])))
    if git['dirty_non_pyc_lines']:
        print('WARNING: the worktree has uncommitted non-.pyc changes; commit before the real freeze:')
        for line in git['dirty_non_pyc_lines']:
            print('  ' + line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
