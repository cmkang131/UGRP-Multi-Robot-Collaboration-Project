"""crate11: contact sheets of SAVED frames (overview + failing robot's own camera) for direct viewing.
No render; reads saved JPEGs only. Usage: crate11_frames.py <run> <rid> <out.jpg> <tick,tick,...>  -> prints per-frame sha256."""
import hashlib, sys, json
from pathlib import Path
from PIL import Image, ImageDraw

RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def main(run, rid, out, ticks):
    raw = RAW / run / 'raw'; cells = []; meta = []
    for tk in ticks:
        a = raw / 'eval-overview' / f'{tk:06d}-grasp.jpg'; b = raw / 'eval-own' / rid / f'{tk:06d}-grasp.jpg'
        im = Image.new('RGB', (320, 480))
        im.paste(Image.open(a).resize((320, 240)), (0, 0)); im.paste(Image.open(b).resize((320, 240)), (0, 240))
        ImageDraw.Draw(im).text((6, 6), f'tick {tk} (+{tk/10:.1f}s)', fill=(255, 255, 0))
        cells.append(im)
        meta.append({'tick': tk, 'elapsed_s_from_grasp_start': tk / 10,
                     'overview': {'path': str(a.relative_to(RAW)), 'sha256': hashlib.sha256(a.read_bytes()).hexdigest()},
                     'own': {'path': str(b.relative_to(RAW)), 'sha256': hashlib.sha256(b.read_bytes()).hexdigest()}})
    cols = 4; rows = (len(cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 320, rows * 480))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * 320, (i // cols) * 480))
    sheet.save(out, quality=88)
    print(json.dumps({'run': run, 'robot': rid, 'sheet': out, 'frames': meta}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], [int(x) for x in sys.argv[4].split(',')])
