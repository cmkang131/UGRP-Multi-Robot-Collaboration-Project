"""Compose final review images on owned L4 only; never step physics."""
from pathlib import Path
import hashlib
import json
import sys

B = Path('/home/ugrp/ugrp-sim')
R = B / 'runs/act16w-native-experiment-r1'
S = B / 'src/34d53cfaadc093ac957bbfffc780a76f372041f9'
sys.path.insert(0, str(S / 'scripts'))
from act16w_runtime import require_gcp2
host = require_gcp2(training=True)
from PIL import Image, ImageDraw, ImageFont

selection = json.loads((R / 'final40-playback-selection.json').read_text())
rows = selection['rows'].copy()
if not selection['actual_student_success_examples']:
    reference = json.loads((R / 'native-teacher-87429-playback-review.json').read_text())
    # The immutable earlier review stores remote paths per verified file.
    roots = {str(Path(row['remote']).parent) for row in reference['files']}
    assert len(roots) == 1
    rows.append(dict(seed=87429, out=roots.pop(), teacher_reference=True))
assert len(rows) == 3
font = ImageFont.load_default(size=24)
small = ImageFont.load_default(size=20)
canvas = Image.new('RGB', (1920, 940), '#131722')
draw = ImageDraw.Draw(canvas)
title = ('Native v1: two ACT failures + ACT success' if selection['actual_student_success_examples']
         else 'Native v1: two ACT failures + teacher reference (NOT an ACT success)')
draw.text((12, 8), title, font=font, fill='white')
receipts = []
for row_index, row in enumerate(rows):
    root = Path(row['out'])
    meta = json.loads((root / 'playback-meta.json').read_text())
    frames = sorted((root / 'own').glob('*.jpg'))
    assert len(frames) == meta['full_2hz_frames']
    start, end = meta['sim_range']
    label = ('TEACHER reference, success; NOT ACT' if row.get('teacher_reference')
             else ('ACT A SUCCESS' if row['student_success'] else 'ACT A FAILURE'))
    y = 48 + row_index * 296
    draw.text((12, y), f'{label} | seed {row["seed"]} | own RGB', font=font, fill='white')
    points = []
    # Fractions only choose illustrative review frames, never an action or gate.
    for column, fraction in enumerate((0, .1, .2, .4, .7, 1)):
        index = round((len(frames) - 1) * fraction)
        path = frames[index]
        sim = start + .5 * index
        image = Image.open(path).convert('RGB').resize((320, 240))
        canvas.paste(image, (column * 320, y + 32))
        draw.text((column * 320 + 5, y + 274), f'SIM {sim:.1f}s', font=small, fill='white')
        points.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), SIM=sim))
    receipts.append(dict(label=label, seed=row['seed'], source=str(root),
                         source_metadata_sha256=hashlib.sha256((root / 'playback-meta.json').read_bytes()).hexdigest(),
                         reviewed_range=[start, end], frames=points))
out = R / 'native-final-montage.png'
assert not out.exists()
canvas.save(out)
receipt = dict(host=host, rows=receipts, actual_student_success_examples=selection['actual_student_success_examples'],
               montage_sha256=hashlib.sha256(out.read_bytes()).hexdigest(), bytes=out.stat().st_size,
               script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               scope='illustrative six own-RGB frames per row; timelines differ; whole2Hz and terminal10Hz direct review recorded separately; no physics',
               camera_note='display resized320x240; teacher review stream is separate from native640x480 training camera')
(R / 'native-final-montage.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(status='complete', bytes=out.stat().st_size(), actual_student_success_examples=selection['actual_student_success_examples'])))
