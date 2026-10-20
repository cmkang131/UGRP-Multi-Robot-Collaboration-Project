"""TRAIN-only start-state curriculum metadata; never model input.

Difficulty is the sum of within-kind distance and absolute-yaw percentile
ranks. Eligible episode count grows linearly with optimizer progress, from
the easiest episode per kind to all episodes. This schedule is an explicit
coordinator design, not an empirically established task-optimal threshold.
"""
import math
import numpy as np


class StartCurriculum:
    def __init__(self, data, starts):
        episodes = [e for e in data.manifest['episodes'] if e['split'] == 'train']
        seeds = {int(e['seed']) for e in episodes}
        if seeds != {int(r['seed']) for r in starts} or len(starts) != len(seeds):
            raise ValueError('curriculum metadata must cover exactly unique TRAIN seeds')
        if any(not math.isfinite(r[k]) or r[k] < 0 for r in starts
               for k in ('start_distance_m', 'abs_start_yaw_rad')):
            raise ValueError('finite nonnegative start difficulty required')
        self.groups = {}
        for row in starts:
            self.groups.setdefault(row['object_kind'], []).append(row)
        self.order = {}
        for kind, rows in self.groups.items():
            ranks = {}
            for key in ('start_distance_m', 'abs_start_yaw_rad'):
                # Stable, tie-aware empirical CDF; no evaluation values used.
                values = sorted(r[key] for r in rows)
                for row in rows:
                    ranks.setdefault(row['seed'], 0.)
                    ranks[row['seed']] += sum(v < row[key] for v in values) / len(values)
            self.order[kind] = sorted((r['seed'] for r in rows), key=lambda seed: (ranks[seed], seed))
        if len(episodes) != len(data.shards):
            raise ValueError('dataset episode/shard alignment mismatch')
        self.rows = {}
        for index, (shard, _) in enumerate(data.index):
            self.rows.setdefault(episodes[shard]['seed'], []).append(index)
        if set(self.rows) != seeds:
            raise ValueError('curriculum has an empty or unaligned TRAIN episode')

    def eligible(self, progress):
        if not math.isfinite(progress) or not 0 <= progress <= 1:
            raise ValueError('optimizer progress must be in [0,1]')
        seeds = [s for order in self.order.values()
                 for s in order[:max(1, math.ceil(progress * len(order)))]]
        return np.array(sorted(i for s in seeds for i in self.rows[s]), dtype=np.int64)
