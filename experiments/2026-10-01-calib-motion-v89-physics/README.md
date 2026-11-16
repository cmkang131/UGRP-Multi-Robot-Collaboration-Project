# 보정 수집: v89 무하중 운동 식별 (#347)

Refs #342 #346 #347. 진단 수집이며 보정값 채택, P03, loaded/fine, 학생 실행 승인이 아니다.

## 실행 정보

- 실행 번들 zone-final-environment-v89, workflow `zone-final-environment-floor-light-v2-check` 2.21.0,
  check `calibration-motion-v2`, seed 911, 지도 `zone_wide_two_doors_final_v3`, 로봇 r1 무하중.
- 고정 소스: PR #347 branch `codex/calib-measure-v2`, SHA `eaeaaff05553ea02c649b4db9ff82470fe6372b5`.
  worktree `/Users/changmin/projects/ugrp-wt/phys-v89-motion`, branch `claude/phys-v89-motion`(잠금 branch와 동일),
  HEAD=SHA, 깨끗한 트리, `source_unchanged=true`.
- 명령: [run_v89.sh](run_v89.sh) (핸드오프와 같은 subshell·`set -euo pipefail`·trap release,
  `ugrp_session.py run measurement-v89`). 정적 계획 확인(`--check` / `workflow plan`)은 먼저 통과.
  로그 [run_v89_log.txt](run_v89_log.txt). 잠금 owner claude, 종료 후 `agent_lock.py status` = null(해제 확인),
  세션 `measurement-v89` stopped, 남은 자식 프로세스 없음.
- 동기 SIM 모드. wall/속도 결론 없음. 실행 전 `uptime`: load averages 14.35 15.40 15.79(잠금 기록 13.52 15.21 15.72),
  실행 후 16.40 16.12 16.00(`result.json`). 다른 Codex 작업이 동시에 돌고 있었다.
- 디스크: 시작 전 여유 37 GiB(>=10 GiB). 프로젝트 예산은 outputs/worktrees OVER 상태(기존).

## 결과 (사실)

- `result.json`: `COLLECTED_UNQUALIFIED`, protocol_complete=true, denominator 1, model_calls 0,
  student_control=false. reset 1.30 SIM s + 수집 230.0 SIM s = 231.3 s (<=235). HOST_ERROR 없음(인터록 중단 없음).
- 렌더: `eval_only/applied.json`에 `floor_light_v1`(sha e3ea8aeb...) 적용, 바닥 텍스처 평균 RGB 124.5/122.0/118.0,
  그림자 0, physics 변경 없음.
- r1 명령 `robots/r1/commands.jsonl`: initial_servo 1 + mecanum **4600**(plan과 일치), 모두 lease 0.05 s, turn=0,
  명령 시각 간격 0.05 s(오차 1e-12). 구성 `configs/final_environment_measurement_v2.json`의 88개 구간으로 펼친
  (전진/측면 값) 4600개와 **불일치 0**.
- `eval_only/r1/pose.jsonl`: **4601**개, sample_index 0..4600 연속, t 간격 min 0.04999999999882 / max 0.05000000000024 s,
  첫 t=1.3(reset 끝), 끝 t=231.3. 렌더와 독립이며 v1(0.2 s)과 다르다.
- 벽 여유(원판 반경 뺀 하한): 최소 **0.6750 m**(시작), 최대 1.2248 m. 중단 기준 0.35 m 훨씬 위.
  r1 xy 범위 x 3.250–3.810, y -0.850 – -0.456.
- r2/r3: 47개 camera label 전부 위치 변화 약 1e-11 m 이내(정지 유지). 기존 상자 배치 유지.
- 자기 RGB 3대 x 47장(초기/5초마다/끝). r1 #23, r2 #0, r3 #46을 직접 확인: 640x480, 바닥은 밝은 회색 체커로
  floor_light 적용, 상자·벽·문 보임. r2/r3 화면의 푸른 바닥은 지도 구역 색으로 보이며 r1 화면 가장자리에도 푸른 구역이 보인다.
- `artifacts.sha256.json` 159개 파일 해시 재계산 일치(불일치 0).
- 원본: `/Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001` (25 MB, 보존, 수정 안 함).
  실행 기록: `/Users/changmin/projects/ugrp-wt/phys-v89-motion/outputs/simulation-runs/20261001-060016-zone-final-environment-floor-light-v2-check-f9dca762/manifest.json`
  (sha256 `b8b2bb7fa77239dae30b0abbe989a3ed03e7f7ddbfb13f8f548b312dfb450f08`, 이 worktree는 retire하지 않고 보존).
  raw 해시 목록 [raw_sha256_manifest.tsv.gz](raw_sha256_manifest.tsv.gz)(162개 파일). 1 MiB 넘는 파일
  (`pose.jsonl`, `contacts.jsonl`)과 PNG는 커밋하지 않았다. 원격 백업이 아니다.

## 식별 가능성 점검 (보정값 아님, 점검만)

코드: [fit_check_v89.py](fit_check_v89.py) (#347의 `response()` 1차 lag 적분 재사용, 출력 [fit_check_output.txt](fit_check_output.txt)).
pose를 첫 body 축(yaw 변화 <=0.93도)에 투영해 축별로 15초 계단 6개 + PRBS의 변위를 적합한다. 잔차 바닥 가정은 0.1 mm였다.

1. **선형 1차 모델(gain, drive τ, stop τ)은 맞지 않는다.** 계단 마지막 3초 정상상태 gain이 크기에 따라 다르다.

   | 입력 | 0.01 | 0.02 | 0.03 |
   |---|---|---|---|
   | 전진 속도/입력 | 0.801 | 1.186 | 1.314 |
   | 측면 속도/입력 | 0.437 | 0.799 | 0.925 |

   (+/− 부호는 서로 같다.) 이 때문에 선형 모델 최소 RMS는 전진 22.4 mm, 측면 21.4 mm이고 τ 0.1–1.5(전진)·0.1–1.8(측면) 초가
   모두 최소 RMS +5% 이내여서 **평평하다**. 이 모델로는 gain/τ를 채택할 수 없다.
2. **데드밴드 모델** `u_eff = sign(u)*max(|u|-d, 0)`을 넣으면 정상상태 속도가 입력에 선형으로 맞는다(탐색 격자 d 간격 0.0005).

   | 축 | d | gain | drive τ (s) | stop τ (s) | RMS (mm) | +5% 범위 (gain / τ / stop τ) |
   |---|---|---|---|---|---|---|
   | 전진 | 0.0050 | 1.576 | 0.836 | 0.08 | 1.79 | 1.565–1.581 / 0.76–0.863 / 0.05–0.12 |
   | 측면 | 0.0065 | 1.180 | 0.836 | 0.08 | 1.76 | 1.143–1.187 / 0.736–0.890 / 0.03–0.12 |

   최소는 격자 경계가 아니고 d·gain·τ 모두 좁게 정해진다(gain ±1% 안팎, τ ±8%, 측면은 gain ±2%). 그러나 RMS 1.8 mm는
   가정한 0.1 mm 바닥보다 18배 크므로 모델이 완전하지 않다. stop τ(0.03–0.12)는 여전히 불확실하다(0.05 s 표본에 비해 짧음).
   #346의 후보 τ(전진 1.44, 측면 3.0 s)와 gain(1.78, 2.41)은 이 자료로는 지지되지 않는다(이 기록의 τ는 약 0.84 s).
3. 검증용 PRBS는 계단만으로 적합(전진 d 0.005/gain 1.582/τ 0.863, 측면 d 0.0065/gain 1.185/τ 0.863)한 모델로 예측했다.
   PRBS 구간 변위 예측 잔차 RMS는 전진 4.24 mm(PRBS 변위 RMS 35.4 mm의 12%), 측면 3.40 mm(23.4 mm의 15%)다.
   계단 구간 RMS(0.84/1.29 mm)보다 크다: 짧은 교번 입력에서는 데드밴드·가속 형태가 더 필요하다는 뜻이다.

판정(점검용): 새 자료는 v1과 달리 τ를 경계 없이 좁게 묶을 수 있지만, 그것은 **데드밴드를 넣은 경우에 한한다**. 이 값을
보정값으로 커밋하지 않았고, 모델 형태(데드밴드, 작은 속도 영역)와 PRBS 잔차를 검토한 뒤 별도 적합 PR에서 다뤄야 한다.
회전/정지 τ, loaded/fine, 카메라 외부 보정, P03은 이 자료로 승격하지 않는다.

## 남은 일

- TensorBoard 변환·영상 등록·화면 확인은 수행하지 않았다(코디네이터 몫, `docs/tensorboard.md`).
- 이 PR은 draft이며 병합하지 않는다.
