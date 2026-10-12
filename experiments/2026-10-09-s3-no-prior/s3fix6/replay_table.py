"""Generate a review table from the unchanged sealed comparison."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
v=json.loads(a.comparison.read_text());labels={'off':'B','effective_sqrt_v1':'C1','effective_mean_v1':'C2','effective_sqrt_alpha_v1':'C3'}
lines=['## Saved-input comparison result','', 'Sources: B/C1/C2 `105ffc70` (retained with byte/AST equivalence); own-map C3 `bfce6a01`; corrected S3 C3 `'+v['replay_source_sha']+'` (per-arm receipts in comparison.json); four saved runs / eight trajectories, four settings, physics0. S3 sigma is sqrt(trace overall XY covariance); own-map sigma is sqrt(max XY eigenvalue). Full matching per-frame XY covariance is retained only for own-map; see the S3 covariance field audit below.','', '| Option | Trajectory | Frames | XY RMSE m | Final error m | RMS sigma m | >3sigma | Mean XY NEES | NEES >11.829 | False certificate frames |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for option,table in v['table'].items():
 for case,r in table.items():
  nees=f"{r['xy_nees_mean']:.3f}" if 'xy_nees_mean' in r else 'unavailable'
  nees_tail=f"{100*r['xy_nees_gt_11_829_fraction']:.2f}%" if 'xy_nees_gt_11_829_fraction' in r else 'unavailable'
  false=str(r['false_certificates']) if 'false_certificates' in r else 'unavailable'
  lines.append(f"| {labels[option]} | {case} | {r['frames']} | {r['xy_rmse_m']:.6f} | {r['final_error_m']:.6f} | {r['sigma_rms_m']:.6f} | {r['over_3sigma']}/{r['frames']} ({100*r['over_3sigma_fraction']:.2f}%) | {nees} | {nees_tail} | {false} |")
lines += ['', 'The preregistered selection rule is unchanged. Selected smoke option: `'+v['smoke_option']+'`.','', '| Candidate | Eligible | Failed checks | Pooled >3sigma |','|---|---:|---:|---:|']
for option,r in v['selection'].items():lines.append(f"| {labels[option]} | {r['eligible']} | {len(r['failures'])} | {100*r['pooled_over_3sigma']:.2f}% |")
if v['smoke_option']=='off':lines += ['', 'No candidate meets the consistency and no-error-deterioration gate. Observation tempering is not admitted for this smoke. This comparison does not establish correlated evidence as the sole cause or resolve overconfidence.']
lines += ['', 'All input streams are fixed saved observations/issued commands; counterfactual controller proposals are logged but not substituted into the archived input stream. These compare reported beliefs from the complete controller under saved inputs, not new closed-loop success trials.']
with a.output.open('x') as f:f.write('\n'.join(lines)+'\n')
