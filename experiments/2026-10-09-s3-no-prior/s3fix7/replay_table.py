"""Review table from the sealed comparison; no selection/threshold changes."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
v=json.loads(a.comparison.read_text());labels={'off':'B','ess_v1':'R1','roughen_v1':'R2','roughen_floor_v1':'R3'}
lines=['## 저장 입력 비교 결과','', '기준 B 4개는 보존된 결과이며 소비 경로 동일성으로 연결했다. R1/R2/R3 각 4개를 새로 재생했다(총 8개 궤적 × 4설정). 물리 실행 0회. S3의 σ는 전체 XY covariance trace의 제곱근, 자기 지도는 XY 최대 고유값의 제곱근이다. 자기 지도는 최고 가중치 입자의 위치와 전체 혼합 covariance를 함께 보고한다. 아래 자기 지도 이차 오차 eᵀP⁻¹e는 그 보고값의 진단이며 정합된 단일 Gaussian의 NEES 인증이 아니다. S3는 full XY covariance가 없어 이를 산출하지 않는다.','', '| 후보 | 궤적 | 프레임 | XY RMSE m | 마지막 오차 m | 마지막 σ m | RMS σ m | >3σ | 평균 보고 eᵀP⁻¹e | 이차 오차 >11.829 | 허위 인증 프레임 |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for option,table in v['table'].items():
 for case,r in table.items():
  nees=f"{r['xy_nees_mean']:.3f}" if 'xy_nees_mean' in r else '미산출'
  tail=f"{100*r['xy_nees_gt_11_829_fraction']:.2f}%" if 'xy_nees_gt_11_829_fraction' in r else '미산출'
  false=str(r['false_certificates']) if 'false_certificates' in r else '해당 없음'
  lines.append(f"| {labels[option]} | {case} | {r['frames']} | {r['xy_rmse_m']:.6f} | {r['final_error_m']:.6f} | {r['final_sigma_m']:.6f} | {r['sigma_rms_m']:.6f} | {r['over_3sigma']}/{r['frames']} ({100*r['over_3sigma_fraction']:.2f}%) | {nees} | {tail} | {false} |")
lines += ['', '사전 선택 규칙 유지. 새 smoke의 PF 옵션: `'+v['smoke_option']+'`.','', '| 후보 | 채택 가능 | 실패 검사 수 | pooled >3σ |','|---|---:|---:|---:|']
for option,r in v['selection'].items():lines.append(f"| {labels[option]} | {r['eligible']} | {len(r['failures'])} | {100*r['pooled_over_3sigma']:.2f}% |")
if v['smoke_option']=='off':lines+=['', '모든 후보가 일관성 개선과 각 궤적 오차 비악화 조건의 결합을 통과하지 못했다. 이번 smoke는 PF 옵션 off로 진행하며, 과신 해결을 주장하지 않는다.']
lines += ['', '저장 입력과 명령을 고정했다. 재생 제어기의 제안 명령은 기록하지만 원래 발행 입력을 대체하지 않는다. 새 폐루프 집기/운반 성능으로 해석하지 않는다.']
with a.output.open('x') as f:f.write('\n'.join(lines)+'\n')
