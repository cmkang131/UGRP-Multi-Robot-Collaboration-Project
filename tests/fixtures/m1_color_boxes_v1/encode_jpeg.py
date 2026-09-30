"""JPEG transport copies; preserves the preimplementation PNGs and labels."""
import hashlib
import json
from pathlib import Path

import cv2

ROOT = Path(__file__).parent
rows = []
for row in json.loads((ROOT/'labels.json').read_text())['frames']:
    path = ROOT/row['file']
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    frame = cv2.imread(str(path))
    payload = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
    target = path.with_suffix('.jpg')
    target.write_bytes(payload)
    rows.append({'source': path.name, 'source_sha256': row['sha256'],
                 'file': target.name, 'sha256': hashlib.sha256(payload).hexdigest()})
(ROOT/'transport.json').write_text(json.dumps({'quality': 95, 'opencv': cv2.__version__,
                                               'label_change': False, 'frames': rows}, indent=2)+'\n')
