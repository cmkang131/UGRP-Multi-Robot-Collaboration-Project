"""Recorded RGB annotations and scientific own-coordinate plot; no rendering."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw


def figures(base, output, plot_dependencies):
    choices = [('s1045', 81, 1, 'Floor / pickup colour: false B'),
               ('s1045', 12001, 1, 'Wall: false floor intersection'),
               ('s912-r2', 1041, 1, 'Robot detail: false B')]
    canvas = Image.new('RGB', (1280, 1030), 'white')
    draw = ImageDraw.Draw(canvas)
    for i, (case, fid, component, title) in enumerate(choices):
        row = next(r for r in map(json.loads, (base/case/'predictions.jsonl').read_text().splitlines())
                   if r['frame_id'] == fid)
        rgb = cv2.cvtColor(cv2.imread(row['rgb_path']), cv2.COLOR_BGR2RGB)
        mask = (cv2.imread(str(base/case/row['labels']), cv2.IMREAD_UNCHANGED) == component).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(rgb, contours, -1, (255, 25, 15), 3)
        x, y = i % 2 * 640, i // 2 * 515
        canvas.paste(Image.fromarray(rgb), (x, y))
        draw.text((x+8, y+482), f'{case}, t={row["t"]}s | {title}', fill='black')
    raw = Image.open(row['rgb_path'])
    canvas.paste(raw.crop((225, 135, 285, 205)).resize((300, 350)), (730, 570))
    draw.text((730, 930), 'Robot patch enlarged for inspection (82 pixels)', fill='black')
    canvas.save(output/'false-positives.jpg', quality=85)
    # Reuse an existing plotting-only directory from #405; no venv installation.
    if plot_dependencies:
        sys.path.append(str(plot_dependencies))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    rows = list(map(json.loads, (base/'s1045/predictions.jsonl').read_text().splitlines()))
    xy = np.array([r['pose'][:2] for r in rows])
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(*xy.T, color='.45', linewidth=1, label='M1 command DR')
    colors = ['#c0392b', '#2980b9', '#8e44ad']
    used = set()
    for r in rows:
        for patch in r['patches']:
            track = patch['track_id']
            hull = np.array(patch['hull_odom_m'])
            hull = np.concatenate([hull, hull[:1]])
            ax.plot(*hull.T, color=colors[track-1], linewidth=.9,
                    label=f'Candidate {track}' if track not in used else None)
            used.add(track)
            ax.scatter(*patch['center_odom_m'], color=colors[track-1], s=12)
            if patch['confirmed_t'] == r['t']:
                ax.annotate(f'False confirmation\n{r["t"]} s', patch['center_odom_m'],
                            xytext=(25, 5), textcoords='offset points', fontsize=9,
                            arrowprops={'arrowstyle': '->'})
    ax.set(xlabel='Own odom x (m)', ylabel='Own odom y (m)',
           title='s1045: observed colour patches\nAll 12 accepted patches are false B')
    ax.set_aspect('equal')
    ax.grid(alpha=.2)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(output/'own-goal-candidates.png', dpi=130)
    plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--predictions', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plot-dependencies', type=Path)
    a = p.parse_args()
    figures(a.predictions, a.output, a.plot_dependencies)
