"""gcp2 saved-trace causal decomposition; no physical stepping or control."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--fixture', type=Path, required=True)
    a = p.parse_args()
    from simalt_host import gcp2_identity
    gcp2_identity()
    import mujoco
    import numpy as np
    prev = a.root.parent/'simalt4'
    paths = {'C312': prev/'c312-grip', 'C316': prev/'c316-grip',
             'Warp316': prev/'legacy-r3-grip', 'Warp312': a.root/'warp-compiled312-grip',
             'C312_damping316': a.root/'c312-damping316-grip',
             'C316_damping312': a.root/'c316-damping312-grip'}
    meta = {k: json.loads((v/'result.json').read_text()) for k, v in paths.items()}
    nc = len(meta['C312']['columns'])
    arrays = {k: np.load(v/'steps.npz')['records'] for k, v in paths.items()}
    if any(v['status'] != 'complete' for v in meta.values()):
        raise ValueError('incomplete trace')
    if len({v['fixture_sha256'] for v in meta.values()}) != 1:
        raise ValueError('different command tape')
    m = mujoco.MjModel.from_xml_path(str(a.fixture/'scene.xml'))
    base = nc+int(m.jnt_qposadr[m.body_jntadr[m.body('r1__robot').id]])
    dt = meta['C312']['dt']
    end = {k: v[-1, base:base+3] for k, v in arrays.items()}
    total = end['Warp316']-end['C312']
    damping = end['Warp316']-end['Warp312']
    residual = end['Warp312']-end['C312']
    # These are vector counterfactuals. Norms are not additive; projections
    # onto the original error vector sum to one, including interactions.
    decomposition = {'total_vector_m': total.tolist(), 'total_norm_m': float(np.linalg.norm(total)),
        'Warp_damping_counterfactual_vector_m': damping.tolist(),
        'Warp_damping_counterfactual_norm_m': float(np.linalg.norm(damping)),
        'matched_damping_residual_vector_m': residual.tolist(),
        'matched_damping_residual_norm_m': float(np.linalg.norm(residual)),
        'damping_projection_fraction': float(damping@total/(total@total)),
        'residual_projection_fraction': float(residual@total/(total@total)),
        'C312_damping_only_norm_m': float(np.linalg.norm(end['C312_damping316']-end['C312'])),
        'C316_raw_norm_m': float(np.linalg.norm(end['C316']-end['C312'])),
        'C316_restored_damping_norm_m': float(np.linalg.norm(end['C316_damping312']-end['C312'])),
        'interpretation': 'C316 raw also changes Plane–Mesh; do not call its entire error damping or Warp. Reciprocal damping ablation isolates the intervention on each engine.'}
    first_rows = []
    step_rows = []
    phases = next(x['phases'] for x in json.loads((a.fixture/'fixture.json').read_text())['cases'] if x['name'] == 'grip')
    indices = set(range(20)) | {len(phases)*400-1}
    indices |= {(i+1)*400-1 for i in range(len(phases)) if i == len(phases)-1 or phases[i] != phases[i+1]}
    for key, values in arrays.items():
        if key == 'C312':
            continue
        difference = values[:, nc:nc+m.nq]-arrays['C312'][:, nc:nc+m.nq]
        for j in range(m.njnt):
            start = int(m.jnt_qposadr[j]); stop = int(m.jnt_qposadr[j+1]) if j+1 < m.njnt else m.nq
            ids = np.flatnonzero(np.any(difference[:, start:stop] != 0, axis=1))
            first = int(ids[0]) if len(ids) else None
            first_rows.append({'comparison': key+' vs C312', 'joint': m.joint(j).name,
                'first_exact_difference_step': first+1 if first is not None else None,
                'first_exact_difference_SIM_s': (first+1)*dt if first is not None else None,
                'first_max_abs_component': float(np.max(np.abs(difference[first, start:stop]))) if first is not None else 0.,
                'endpoint_max_abs_component': float(np.max(np.abs(difference[-1, start:stop])))})
            if first is not None:
                indices |= set(range(max(0, first-2), min(len(values), first+3)))
        for i in sorted(indices):
            step_rows.append({'comparison': key+' vs C312', 'step_1based': i+1, 'SIM_s': (i+1)*dt,
                'phase': phases[i//400], 'base_error_m': float(np.linalg.norm(values[i, base:base+3]-arrays['C312'][i, base:base+3])),
                **{m.joint(j).name: float(difference[i, m.jnt_qposadr[j]]) for j in range(m.njnt)}})
    for name, rows in [('first-joint-divergence.csv', first_rows), ('joint-step-excerpts.csv', step_rows)]:
        with (a.root/name).open('x') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = {'decomposition': decomposition, 'endpoints': {k: v.tolist() for k, v in end.items()},
        'raw': {k: {'path': str(paths[k]/'steps.npz'), 'sha256': hashlib.sha256((paths[k]/'steps.npz').read_bytes()).hexdigest()} for k in paths},
        'note': 'Exact first difference is descriptive, includes float32 rounding, and is not an acceptance threshold.',
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (a.root/'version-decomposition.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(decomposition, indent=2))


if __name__ == '__main__':
    main()
