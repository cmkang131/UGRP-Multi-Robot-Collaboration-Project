#!/usr/bin/env python3
"""Visualize wall extraction benchmark results on a 2D map."""
import json, math
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from harness import opencv_wall_observation as ow
from harness import vision_loc_protocol as vp
from harness import zone_pair_highpose_contract as contract
from harness.vision_pose_source_highpose import HighPoseSource

def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))

def main():
    bm = json.loads(Path('wall_extraction_benchmark.json').read_text())
    rows = bm['rows']

    # --- Read static map ---
    case = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-case-carry-a3415342-s911-wtX-n0/zone_wide_door_geometry_v3')
    static_map = json.loads((case / 'inputs/static_map.json').read_text())
    trajectory = [json.loads(l) for l in (case / 'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts = np.array([r['t'] for r in trajectory])

    bounds = static_map['bounds_m']  # [xmin, xmax, ymin, ymax]
    obstacles = static_map['obstacles']

    # --- Compute counts ---
    total = len(rows)
    pass_n = sum(1 for r in rows if r['label'] == 'pass')
    wrong_n = sum(1 for r in rows if r['label'] == 'wrong')
    miss_n = sum(1 for r in rows if r['label'] == 'miss')
    rate = wrong_n / total * 100 if total else 0
    goal_met = rate <= 3

    fig = plt.figure(figsize=(14, 10))

    # --- Plot 1: 2D Arena Map with Walls ---
    ax1 = fig.add_subplot(2, 2, 1)
    ax1.set_title('2D Map — Wall Extraction (seed 0)', fontsize=11)
    ax1.set_xlim(bounds[0] - 0.2, bounds[1] + 0.2)
    ax1.set_ylim(bounds[2] - 0.2, bounds[3] + 0.2)
    ax1.set_aspect('equal')
    ax1.set_xlabel('x (east, m)')
    ax1.set_ylabel('y (north, m)')

    # Draw obstacles (walls)
    for obs in obstacles:
        cx, cy = obs['center_m']
        hx, hy = obs['half_extents_m']
        rect = FancyBboxPatch((cx - hx, cy - hy), 2*hx, 2*hy,
                               boxstyle="round,pad=0.02", linewidth=2,
                               edgecolor='black', facecolor='lightgray')
        ax1.add_patch(rect)
        ax1.text(cx, cy, obs['id'], fontsize=6, ha='center', va='center', rotation=0)

    ax1.set_facecolor('#f8f8f8')

    # --- Plot 2: Image-space extraction quality ---
    ax2 = fig.add_subplot(2, 2, 2)
    ax2.set_title('Wall Extraction Quality (all seeds, pan=1500/1230)', fontsize=11)
    ax2.set_xlabel('Image column index')
    ax2.set_ylabel('Image row (px, 0=top)')
    ax2.invert_yaxis()  # row 0 is top

    for pan_val, color in [(1500, 'steelblue'), (1230, 'coral')]:
        pan_rows = [r for r in rows if r['pan'] == pan_val]
        total_p = len(pan_rows)
        wrong_p = sum(1 for r in pan_rows if r['label'] == 'wrong')
        rate_p = wrong_p / total_p * 100 if total_p else 0
        # Scatter observed rows
        for label, marker in [('pass', 'o'), ('wrong', 'x')]:
            label_rows = [r for r in pan_rows if r['label'] == label]
            if label_rows:
                cols = [r['col'] for r in label_rows]
                rows_obs = [r['obs_row'] for r in label_rows]
                ax2.scatter(cols, rows_obs, c=color, marker=marker, s=8, alpha=0.5,
                           label=f'pan={pan_val} {label}')

    ax2.legend(fontsize=8, loc='upper right')
    ax2.set_ylim(500, 0)

    # --- Plot 3: Error rate by pan value ---
    ax3 = fig.add_subplot(2, 2, 3)
    ax3.set_title('Error Rate by Pan Angle', fontsize=11)
    for pan_val, color in [(1500, 'steelblue'), (1230, 'coral')]:
        pan_rows = [r for r in rows if r['pan'] == pan_val]
        total_p = len(pan_rows)
        wrong_p = sum(1 for r in pan_rows if r['label'] == 'wrong')
        rate_p = wrong_p / total_p * 100 if total_p else 0
        ax3.bar(f'pan={pan_val}', rate_p, color=color, label=f'n={total_p}, {rate_p:.1f}% error')
    ax3.set_ylabel('Error rate (%)')
    ax3.set_ylim(0, 5)
    ax3.axhline(y=3, color='red', linestyle='--', alpha=0.5, label='3% target')
    ax3.legend(fontsize=8)

    # --- Plot 4: Summary text ---
    ax4 = fig.add_subplot(2, 2, 4)
    ax4.axis('off')
    ax4.text(0.1, 0.85, 'Wall Extraction Benchmark Summary', fontsize=14, fontweight='bold', transform=ax4.transAxes)
    ax4.text(0.1, 0.7, f'Total observations: {total}', fontsize=11, transform=ax4.transAxes)
    ax4.text(0.1, 0.6, f'Seeds: 30', fontsize=11, transform=ax4.transAxes)
    ax4.text(0.1, 0.5, f'PASS: {pass_n} ({pass_n/total*100:.1f}%)', fontsize=11, color='green', transform=ax4.transAxes)
    ax4.text(0.1, 0.4, f'WRONG: {wrong_n} ({wrong_n/total*100:.1f}%)', fontsize=11, color='red', transform=ax4.transAxes)
    ax4.text(0.1, 0.3, f'MISS: {miss_n}', fontsize=11, color='orange', transform=ax4.transAxes)
    ax4.text(0.1, 0.2, f'Error rate: {rate:.2f}%', fontsize=13, fontweight='bold',
             color='green' if rate <= 3 else 'red', transform=ax4.transAxes)
    goal_str = 'Goal (<=3%): MET' if goal_met else 'Goal (<=3%): NOT MET'
    ax4.text(0.1, 0.1, goal_str, fontsize=13, fontweight='bold',
             color='green' if rate <= 3 else 'red', transform=ax4.transAxes)
    ax4.text(0.1, 0.0, f'Map: {static_map["map_id"]}', fontsize=9, transform=ax4.transAxes)
    ax4.text(0.1, -0.05, f'Gates: {json.dumps(bm["gates"], indent=1)}', fontsize=8, transform=ax4.transAxes)

    plt.tight_layout()
    out1 = '/Users/changmin/projects/ugrp-wt/light-ext/wall_extract_vis/wall_extraction_2d_map.png'
    plt.savefig(out1, dpi=150)
    print(f'Saved {out1}')

    # --- Also create a world-coordinate scatter ---
    fig2, ax = plt.subplots(1, 1, figsize=(10, 8))
    ax.set_title('2D Map: Wall Extraction Results', fontsize=12)
    ax.set_xlim(bounds[0] - 0.2, bounds[1] + 0.2)
    ax.set_ylim(bounds[2] - 0.2, bounds[3] + 0.2)
    ax.set_aspect('equal')
    ax.set_xlabel('x (east, m)')
    ax.set_ylabel('y (north, m)')

    # Draw walls
    for obs in obstacles:
        cx, cy = obs['center_m']
        hx, hy = obs['half_extents_m']
        rect = Rectangle((cx - hx, cy - hy), 2*hx, 2*hy, linewidth=2,
                          edgecolor='black', facecolor='lightgray', alpha=0.5)
        ax.add_patch(rect)
        ax.text(cx, cy, obs['id'], fontsize=7, ha='center', va='center')

    ax.set_facecolor('#f0f0f0')
    plt.tight_layout()
    out2 = '/Users/changmin/projects/ugrp-wt/light-ext/wall_extract_vis/wall_extraction_map_layout.png'
    plt.savefig(out2, dpi=150)
    print(f'Saved {out2}')

if __name__ == '__main__':
    main()