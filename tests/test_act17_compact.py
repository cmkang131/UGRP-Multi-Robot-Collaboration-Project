import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import act17_compact_records as m


def test_closed_manifest_stays_valid_after_hardlinks_and_lossless_text_archive(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'frozen_source',lambda *_:'0'*40)
    capture=tmp_path/'capture';capture.mkdir();controller=tmp_path/'controller';controller.mkdir()
    image=b'original JPEG bytes remain unchanged'
    for p in [capture/'a.jpg',capture/'b.jpg']:p.write_bytes(image)
    text=(b'{"frame":"'+b'a'*70000+b'"}\n');p=capture/'trace.jsonl';p.write_bytes(text)
    inventory={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in capture.iterdir()}
    (capture/'summary.json').write_text(json.dumps(dict(sha256=inventory)))
    (controller/'summary.json').write_text(json.dumps(dict(sha256={})))
    report=m.compact(tmp_path,tmp_path/'receipt.json')
    assert report['complete'] and report['producer_manifest_files_verified']==3
    assert (capture/'a.jpg').stat().st_ino==(capture/'b.jpg').stat().st_ino
    assert (capture/'a.jpg').read_bytes()==image
    assert not p.exists() and Path(str(p)+'.zst').exists()
    assert m.original_sha256(p)==hashlib.sha256(text).hexdigest()
    assert report['allocated_bytes_after']<report['allocated_bytes_before']
