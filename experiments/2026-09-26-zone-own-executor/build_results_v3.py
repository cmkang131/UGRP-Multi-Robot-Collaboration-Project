"""Results + TensorBoard snapshot for the executor smoke v3: ``build_results_v2.py`` with the v3 episodes.

Usage: python experiments/2026-09-26-zone-own-executor/build_results_v3.py <smoke-v3-dir> [--tensorboard <snapshot>]
Writes ``results_v3.json`` / ``raw_index_v3.json``; v1 and v2 results are shown for reference, never pooled.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_results_v2 as b  # noqa: E402

b.VERSION = 'v3'
b.EPISODES = ('smoke-v3-s700', 'smoke-v3-s701')
b.EARLIER = {'v1': HERE / 'results.json', 'v2': HERE / 'results_v2.json'}

if __name__ == '__main__':
    b.main()
