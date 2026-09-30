"""Missing content edges were PR309's failure: exercise those counterexamples."""
import base64
import gzip
import hashlib
import io
import json
import importlib.util
from pathlib import Path
import sqlite3

import pytest

from scripts import outputs_retention_graph as graph


def refs(value, suffix='.json', *, streaming=False):
    raw = json.dumps(value).encode() if suffix == '.json' else value
    return set(edge for text in graph.structured_strings(io.BytesIO(raw), suffix, streaming=streaming)
               for edge in graph.references(text))


def test_learned_approach_nested_record_is_not_filtered_by_log_name():
    own = b'learned approach RGB'
    data = {'learned_approach': {'report': {'approach_calls': [
        {'images': {'own': {'path': 'rgb/pair-100-phase-1-030-r1.jpg',
                            'sha256': hashlib.sha256(own).hexdigest()}}}]}}}
    assert ('image', 'rgb/pair-100-phase-1-030-r1.jpg') in refs(data)
    assert ('sha256', hashlib.sha256(own).hexdigest()) in refs(data)


def test_dataset_image_hashes_keys_relocate_external_training_source():
    digest = hashlib.sha256(b'training input').hexdigest()
    data = {'train': [{'image_hashes': {
        '/historical/host/outputs/simulation-realtime-20260923/run/rgb/a.jpg': digest}}]}
    edges = refs(data)
    assert ('image', 'simulation-realtime-20260923/run/rgb/a.jpg') in edges
    assert ('sha256', digest) in edges


@pytest.mark.parametrize('suffix,raw', [
    ('.jsonl', b'{"unfamiliar_field":"rgb/raw.png"}\n'),
    ('.csv', b'input_path,digest\n"rgb/raw.png",' + b'a' * 64 + b'\n'),
    ('.tsv', b'input_path\nrgb/raw.png\n'),
])
def test_every_supported_record_field_is_scanned(suffix, raw):
    assert ('image', 'rgb/raw.png') in refs(raw, suffix)


def test_gzipped_frame_log(tmp_path):
    p = tmp_path / 'unconventionally-named.jsonl.gz'
    p.write_bytes(gzip.compress(b'{"file":"frames/00004.jpg"}\n'))
    with graph.open_record(p) as stream:
        edges = {edge for s in graph.structured_strings(stream, graph.structured_suffix(p), streaming=False)
                 for edge in graph.references(s)}
    assert ('image', 'frames/00004.jpg') in edges


def test_decomposed_audit_frame_join():
    row = {'run': 'pair-stage-probes-a', 'case': 'carry_b_s911', 'robot': 'r2', 'frame': 4}
    assert graph.frame_references(row) == ['pair-stage-probes-a/cases/carry_b_s911/frames/r2/00004.jpg']
    assert ('image', graph.frame_references(row)[0]) in refs((json.dumps(row) + '\n').encode(), '.jsonl')
    assert graph.frame_references({'frame': 4}) == []


def test_inline_payload_and_unusual_hash_key():
    image = b'raw encoded input'
    digest = hashlib.sha256(image).hexdigest()
    data = {'opaque': 'data:image/jpeg;base64,' + base64.b64encode(image).decode(), 'unknown': digest}
    assert ('sha256', digest) in refs(data)


def test_worker_log_reference_without_json_filename():
    assert ('image', 'worker/frames/r2/00003.jpg') in refs(
        b'worker input=/a/outputs/worker/frames/r2/00003.jpg\n', '.log')


def test_decoded_json_escapes_and_space_in_full_path():
    assert ('image', 'run/frames/space in name.png') in refs({'file': 'outputs/run/frames/space in name.png'})
    assert ('image', 'run/frames/a.jpg') in refs({'file': r'outputs\run\frames\a.jpg'})
    assert ('image', 'rgb/a.jpg') in refs({'file': '\u0072gb/a.jpg'})


def test_ambiguous_relative_reference_protects_all_matches():
    paths = ['one/rgb/a.jpg', 'two/rgb/a.jpg', 'three/rgb/b.jpg']
    assert [p for p in paths if graph.path_matches(p, 'rgb/a.jpg')] == paths[:2]
    assert not graph.path_matches('one/notrgb/a.jpg', 'rgb/a.jpg')


def test_review_glob_star_includes_path_separators():
    exclusions = {'exclusions': [{'id': 'E3', 'exclude': [
        {'kind': 'glob', 'pattern': 'pair-stage-probes-*/cases/*/frames/*'}]},
        {'id': 'E1', 'exclude': [{'kind': 'folder', 'path': 'realtime'}]}]}
    assert graph.exclusion_ids('pair-stage-probes-a/cases/x/nested/frames/r1/00004.jpg', exclusions) == ['E3']
    assert graph.exclusion_ids('realtime/sub/input.jpg', exclusions) == ['E1']
    assert graph.exclusion_ids('realtime-other/sub/input.jpg', exclusions) == []


@pytest.mark.parametrize('pattern,folder', [
    ('run/frames/**/*.jpg', 'run/frames'), ('run/frames/*.png', 'run/frames'),
    ('run/case*/frames/r1', 'run'), ('run/{dev,test}/frames', 'run'),
])
def test_glob_protects_entire_parent_directory(pattern, folder):
    assert graph.glob_parent(pattern) == folder
    assert graph.under(folder + '/unsampled/last.jpg', folder)


def test_recursive_record_discovery_preserves_matching_runs_not_unread_cache():
    pattern = '**/pair-decisions.json'
    assert graph.matched_glob_folder(pattern, 'realtime/run/pair-decisions.json') == 'realtime/run'
    assert graph.matched_glob_folder(pattern, 'status-video/node_modules/compiler.js') is None
    assert graph.matched_glob_folder('b-v6h-*', 'b-v6h-run.log') is None
    assert graph.matched_glob_folder('b-v6h-*', 'b-v6h-run', is_directory=True) == 'b-v6h-run'


def test_malformed_source_does_not_silently_mean_no_references():
    with pytest.raises(ValueError):
        refs(b'{"broken":"rgb/a.jpg"', '.jsonl')
    with pytest.raises(ValueError, match='inline image'):
        list(graph.references('data:image/jpeg;base64,%%%'))
    with pytest.raises(ValueError, match='inline image'):
        list(graph.references('data:image/jpeg'))


def test_json_streaming_and_stdlib_agree():
    pytest.importorskip('ijson')
    data = {'image_hashes': {'rgb/x.png': 'a' * 64}, 'arbitrary': ['rgb/y.jpg']}
    assert refs(data, streaming=True) == refs(data, streaming=False)
    data['historical_nonfinite'] = float('nan')
    assert refs(data, streaming=True) == refs(data, streaming=False)


def test_round3_classification_excludes_inputs_globs_and_unresolved_media(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'experiments/2026-09-30-outputs-retention/audit/round3_graph.py'
    spec = importlib.util.spec_from_file_location('round3_test_driver', script)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    monkeypatch.setattr(driver, 'DEST', tmp_path)
    root = tmp_path / 'outputs'; root.mkdir()
    c = sqlite3.connect(':memory:')
    c.executescript('''CREATE TABLE files(path TEXT PRIMARY KEY,size INTEGER,allocated INTEGER,
        mtime INTEGER,mode INTEGER,sha TEXT,old_action TEXT,rule TEXT,protection TEXT,source TEXT);
        CREATE TABLE refs(kind TEXT,target TEXT,source TEXT);
        CREATE TABLE folders(folder TEXT,source TEXT,reason TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);''')
    with pytest.raises(RuntimeError, match='classify phase has not completed'):
        driver.emit(c, root)
    assert not (tmp_path / 'manifest.json').exists()
    records = [('review/nested/frame.jpg', 'D1'), ('unexpected/model-input.jpg', 'D1'),
               ('unknown/frame.jpg', 'D1'), ('globbed/not-an-image.bin', 'D3'),
               ('cache/installed.bin', 'D3'), ('duplicate.json', 'D5')]
    for name, rule in records:
        p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(name.encode())
        s = p.stat()
        c.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,NULL,NULL)',
                  (name, s.st_size, s.st_blocks * 512, s.st_mtime_ns, s.st_mode,
                   hashlib.sha256(name.encode()).hexdigest(), 'delete', rule))
    # A running producer may replace an unlisted image after inventory. It is
    # outside the frozen proposal and must stay protected without opening it.
    c.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,NULL,NULL)',
              ('new/live.jpg', 10, 4096, 1, 0o100644, None, None, None))
    reviewed = 'review/nested/frame.jpg'
    s = (root / reviewed).stat()
    (tmp_path / 'reviewer-exclusions.json').write_text(json.dumps({
        'exclusions': [{'id': 'E', 'exclude': [{'kind': 'glob', 'pattern': 'review/*'}]}],
        'union_delete_totals': {'files': 1, 'bytes': s.st_size, 'allocated_bytes': s.st_blocks * 512,
                               'sorted_paths_lf_sha256': hashlib.sha256((reviewed + '\n').encode()).hexdigest()}}))
    for path in ['unexpected/model-input.jpg', 'duplicate.json']:
        c.execute('INSERT INTO refs VALUES(?,?,?)', ('sha256', hashlib.sha256(path.encode()).hexdigest(), 'any-name.json'))
    c.execute('INSERT INTO folders VALUES(?,?,?)', ('globbed', 'analysis.py:20', 'analysis_script_input_directory'))
    c.execute('INSERT INTO refs VALUES(?,?,?)', ('output', 'duplicate.*', 'glob-analysis.json'))
    before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    driver.resolve_references(c, root)
    assert c.execute('SELECT path FROM files WHERE protection IS NULL').fetchall() == [('cache/installed.bin',)]
    assert c.execute("SELECT protection FROM files WHERE path='unknown/frame.jpg'").fetchone() == ('unresolved_producer_consumer',)
    assert c.execute("SELECT protection FROM files WHERE path='new/live.jpg'").fetchone() == ('outside_frozen_round2_scope',)
    assert before == {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
