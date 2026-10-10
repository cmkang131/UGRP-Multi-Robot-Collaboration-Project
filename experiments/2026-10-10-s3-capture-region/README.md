# S3 s3fix14: grasp capture region and actuator resolution

2026-10-10, DEV tuning diagnostic. PR #416 remains DRAFT; no CI wait/merge.
Remote refs scanned before reservation: maximum v159; reserve **v160 /7.53.0**
for the evaluation-only diagnostic. Existing registered files/defaults remain unchanged.
Host **oracle-x86**, OSMesa, MuJoCo3.12, LP_NUM_THREADS=4, OMP_NUM_THREADS=1,
at most10 S3 subprocesses. No physics/render/replay on Mac. ENOSPC/execution errors
are HOST_ERROR. Memory admission refusal waits then resubmits the same immutable list.

## Measurement plan fixed before results

[diagnostic-plan.json](diagnostic-plan.json) lists every name, seed, command flag.
All15 jobs are submitted before reading outcomes; fixed queue of10 (no SIGSTOP/nice).
Nine capture jobs: r1/r2/r3 × yaw(-.14,0,.14)rad; each contains the full
5×5 dx/dy grid (-24,-12,0,12,24)mm = **75 attempts/robot,225 total**.
dx/dy are object grip-centre errors in the rotated robot base frame, the same
coordinates as RGB alignment; dyaw rotates about the nominal grip point.
The setup solves base_xy = grip_xy - R(yaw)*(grasp_radius+dx,dy). This avoids
mistaking the203mm yaw lever arm for independent translational capture tolerance.
Pair partner is nominal and executes the
same synchronized tape, so these are **conditional individual capture regions**,
not proof that two arbitrary errors can be combined. Cyan is single-robot.
Existing stage fixture supplies scene only. The evaluation-side setup places the
robot at the static grasp convention plus the defined grip-frame offset; no pose/contact is supplied
to a student. There is no student controller in this diagnostic.

Fixed existing `ArmSequence` eased hover1s, seven0.12s descent steps, existing
hover settle, close0.5s+0.4s settle, low-hover lift1.2s+2.8s settle; finish at12SIMs.
No weld, base motion, live IK retarget, feedback correction, or success-driven retry.
**Grasp:** tested robot both fingers touching in >=4 samples (0.20s) between
close-ramp end and lift start. **Lift:** every sample in final1s has cargo COM>.06m
and both fingers of all carriers touching. Both criteria required for capture.
Actual tilt/drop/nonfinite stop is a physical failure; other exceptions HOST_ERROR.
Nominal0-offset captures own RGB at5Hz as representative raw; all attempts preserve
command tape, contacts, trajectory, cargo truth, outcome, hashes. Grasp/lift diagnostic
is not alignment, transport, E2E, or real-hardware success.

Six pulse jobs: conditions0–5, seeds14201–14206, each same fixed list of48 actions:
2 repeats × levels15/20/25/**35 reference** × forward/left/turn × signs±,
100ms drive then900ms native-expiry rest (48SIMs). All3 robots measured together
in the existing empty-room setup, inspect posture. Body displacement at10ms grid,
no outcome-dependent pulse or origin reset. Report signed response, cross-axis drift,
median/range and rest drift. Low-speed capability is diagnostic-only and rejects
`student_control != false`; the normal port contract is unchanged.

Command template (each row substitutes its name/kind/condition/flags):
```
.venv-sim/bin/python -m scripts.run_s3_capture_diagnostic --expected-source-sha SHA --output outputs/NAME/raw --kind KIND --condition C FLAGS --execute
```
Whole batch:
```
ORACLE_HOST=oracle-x86 oracle_run.sh WORKTREE s3fix14-diagnostics-r1 -- .venv-sim/bin/python -m scripts.run_s3_capture_cohort --expected-source-sha SHA --output outputs/s3fix14-diagnostics-r1/cohort --execute
```
Optional **one8SIM pathcheck**, nominalr3 open-loop tape. If infrastructure/contract
failure, fix and retest once; it does not tune the grid or count as a research unit.

## Selection rule fixed before diagnostic outcomes

1. **Hardware floor:** repository physical reference explicitly records wheel commands
   <=30 do not move the chassis; use35. Thus15/20/25 are measured but **ineligible** for
   control even if SIM residual motion is nonzero. Official SDK accepts a range but
   does not provide measured deadband; no conversion of SDK argument range into
   physical minimum. See sources below.
2. For each robot, consider origin-centred boxes bounded by measured XY levels and
   yaw±.14. Require every tested grid point inside the box to grasp AND sustain lift,
   including nominal. Select maximum-volume such box; ties choose smaller x, then y.
   Missing/error points fail qualification. Shrink each halfwidth to**80%** as margin.
   This is a finite-grid DEV estimate, not a proof of all unmeasured interior poses.
3. Effective robot/object alignment halfwidth must contain the worst measured absolute
   relevant-axis35/100ms step (all6 conditions and both signs) plus residual spread.
   Conservatively use maxstep + (maxstep-minstep). Full width>=2×this bound.
   This is an explicit sufficient engineering rule for a scalar quantized loop,
   **not a universal theorem** claiming every smaller interval must oscillate.
   Existing 3mm/0.035rad thresholds are retained in default-off code.
4. If no hardware-valid pulse fits the conservative capture box, mark candidate
   **NOT_ADMISSIBLE**; do not fake movement at15/20/25, widen beyond capture evidence,
   or silently shorten100ms. Report the precise incompatible bounds. A ten-case
   candidate is only launched after a concrete admissible profile and its hashes
   are preregistered; otherwise all10 are recorded blocked with this cause.
5. If admissible, freeze new default-off profile and all downstream alignment/hover/
   fixed-posture gate tolerances consistently before the10-case DEV batch. Keep fresh
   RGB/settling/hysteresis/one-axis behavior, heading on except joint beam carry.
   Pairc0–c5 + cyanc0/c3/c4/c5, each<=60SIMs, one batch. Cyan c0 regression mandatory.
   Use **n/N** for reached alignment, grasp, lift, carry. Never call tuning data confirmatory.

## References (checked2026-10-10)

- [Hiwonder MasterPi official motion tutorial](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/6.motion_control_course.html):
  SDK command range and50 example; **no numeric measured minimum**. Do not infer
  wheel PWM deadband from its mm/s API description.
- [Physical reference in this repository](../../scripts/red_block/physical_state_machine_reference.py#L266):
  recorded physical observation <=30 stationary,35 normal; minimum fine turn100ms.
  [v7 provenance](../2026-10-06-drive-friction/README.md) and
  [v7 input relay](../../sim/masterpi_drive_friction_v7.py) use this observation's
  bracket32.5. Installed motor/voltage/load-dependent deadband remains uncalibrated.
- [Hutchinson/Hager/Corke1996 visual servo tutorial](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf):
  image-feedback control, calibration and convergence/stability limitations;
  use actual grasp task region instead of assuming arbitrary precise pose alignment.
- [Liberzon2009, Nonlinear control with limited information](https://liberzon.csl.illinois.edu/research/legacy.pdf):
  quantization/time-delay errors and practical stability. Our full-width>=2×step
  condition above is a stated conservative design bound, not a quotation from it.
- [Johns/Leutenegger/Davison2016, Grasp Function under Gripper Pose Uncertainty](https://arxiv.org/abs/1608.02239):
  choose a region of good grasp outcomes under pose uncertainty instead of a brittle
  isolated optimum. We measure a fixed-motion grid only; no learned grasp network
  or GT online grasp selection is added.

## Results

Completed; see the result section below.

Local pre-execution checks: `test_s3_capture_diagnostic.py` and catalog plan subset,
6 passed; no local physics/render/replay. Central catalog matches origin/main bytes.

## Execution receipt (before cohort results)

Physics source **4384d61cfeafef96e62fd90355fe05c8cfa38699**, pushed.
`s3fix14-pathcheck-r1`:8SIMs, no HOST_ERROR; nominal cyan fixed tape reached
bilateral grasp and low lift. Trial wall16.65s; whole process including imports38.59s.
This is a path check, excluded from the225-point grid and candidate denominators.
`s3fix14-diagnostics-r1` submitted all15 jobs unchanged, workers10, LP_NUM_THREADS4.
The finite-grid evaluator implements the preregistered rule and verifies all raw hashes.
[Candidate names/seeds](candidate-plan.json) are frozen; parameters await entire-batch
selection. No ongoing raw outcome was used to alter the submitted grid.

Hardware qualification boundary: `scripts/red_block/primitive.py` accepts a35 floor
but its high-level lateral primitive expands requests to65/0.65s. The lower-level
35/0.10s lateral response measured here is a **DEV SIM calibration**, not independently
verified real sideways motion. No real device is commanded. `hardware_admissible`
in the diagnostic table means it is not below the recorded no-motion floor; it
must not be read as measured real distance/angle or deployed lateral qualification.
Saved-RGB-only delivery uses `build_s3_capture_delivery.py`; it creates no new scene
rendering or physics and checks actual video decoding/frame count/rate on x86.


## s3fix14 결과 — 새 제어 후보 미채택

전체 사전 등록225점과 펄스6조건을 같은 **oracle-x86 / LP_NUM_THREADS=4**에서 완료했다.
실행 SHA4384d61c, 평가 코드e56c45b2. 총15작업 EXIT0, HOST_ERROR0, 물리 중단0.
8SIM 경로 확인은 별도1회로 분모에서 제외했다. 후보10조건은 **실행하지 않았다**.

| 로봇 | 집기 접촉 | 지속 상승 | 집기 후 상승 실패 | 집기 접촉 실패 | 명목0점 |
|---|---:|---:|---:|---:|---|
| r1 | 53/75 | 29/75 | 24 | 22 | 통과 |
| r2 | 51/75 | 29/75 | 22 | 24 | 통과 |
| r3 | 34/75 | 19/75 | 15 | 41 | 통과 |

**허용 폭을 넓힐 근거와 한계:** yaw0·dy0 축에서는 r1/r2가dx[-24,-12,0,12,24]mm의5/5,
r3는dx[-12,0,12]mm의3/3을 통과해 전진±3mm는 해당 축 점검에서 좁았다. dx=dy=0에서는
세 로봇 모두yaw[-.14,0,.14]rad3/3을 통과했다. 그러나 세 로봇 모두dx=0,yaw=0의
dy=-12/0mm는 상승하고 **dy=+12mm는 접촉 후 상승 실패**했다. 포착 영역은 비대칭이며
독립 축 결과로±12mm 직육면체 전체를 통과시킬 수 없다. [전체225점](capture-grid.md).
이것은 고정 궤적의 유한 격자 결과이며, 로봇별 성공률 추정/학생 정렬 성공/실물 파지가 아니다.

|100ms 명령|실제 끝점 응답 범위|사전 보수 경계(max+spread)|제어 선택|
|---|---:|---:|---|
| forward -35 (n=36) | -12.4208…-11.7882 mm | 13.0535 mm | 허용 폭 조건 미충족 |
| forward +35 (n=36) | 11.0177…16.6858 mm | 22.3538 mm | 허용 폭 조건 미충족 |
| left -35 (n=36) | -11.0470…-10.8348 mm | 11.2593 mm | 허용 폭 조건 미충족 |
| left +35 (n=36) | 10.2162…11.8070 mm | 13.3978 mm | 허용 폭 조건 미충족 |
| turn -35 (n=36) | -0.0984…-0.0953 rad | 0.1014 rad | 허용 폭 조건 미충족 |
| turn +35 (n=36) | 0.0856…0.0888 rad | 0.0920 rad | 허용 폭 조건 미충족 |

15/20/25는 v7 불감대 안의 미세 정착 드리프트만 남았고, 부호와 이동 방향도 일치하지 않았다.
기존 실물의30이하 정지 관측에 따라 모두 채택 제외했다. 시뮬레이터가 그 관측을 입력 모델로
반영한 것이므로 새 실물 불감대 측정으로 보고하지 않는다. 명령당36개 로봇 응답, 전체864개 곡선이다.

**사전 판정:** 필요한 반폭은 전진22.354mm·옆13.398mm·회전0.101447rad.
측정 격자의 최대24mm에80% 여유를 적용하면19.2mm로 전진 요구보다 작고,
더 직접적으로는 세 로봇 모두 모든 점이 성공하는 원점 중심 포착 직육면체가 없다.
따라서 결과를 본 뒤 문턱/여유/선택 규칙을 바꾸지 않고 `NOT_ADMISSIBLE_CURRENT_GRID`로 판정했다.
이는 모든 가능한 제어 방법의 불가능 증명이 아니라 **이번 격자와 사전 기준으로 채택 근거가 없다는 뜻**이다.

|후속10조건|정렬 도달 n/N|집기 n/N|상승 n/N|운반 n/N|cyan c0 회귀|
|---|---|---|---|---|---|
|pair c0–c5, cyan c0/c3/c4/c5|미측정(N=0)|미측정(N=0)|미측정(N=0)|미측정(N=0)|미실행|

조건별 `NOT_RUN`은[candidate-plan.json](candidate-plan.json)에 보존했다. 미실행을0/10 실패로 세지 않는다.
허용 폭 변경·새 학생 정책은 미채택, 기존 기본값과 명령 경로는 그대로다.15/20/25옵션은
평가 전용 포트에서만 작동하며 학생 제어가 켜져 있으면 거절한다.

**시간:** 묶음 wall616.76s, CPU user5006.21+system81.54s; capture2700SIMs + pulse288SIMs.
병렬 묶음 wall/총SIM을 단일 S3 속도와 비교하지 않는다. 로봇별75회 진단 합산은 다음과 같다.

|대상|누적 wall s|누적 SIM s|합산 wall/SIM|
|---|---:|---:|---:|
|r1|1524.89|900.00|1.694|
|r2|1530.84|900.00|1.701|
|r3|1327.73|900.00|1.475|

진단은 대부분 렌더·PF가 없는 고정 팔 궤적이라 이전3대 학생60SIM스모크와 속도 비교하지 않는다.

**기록 범위:** raw의 상속된 `physical_supervisor` 문자열은 S2 r3 경로 이름이지만,
이번 평가용 bundle의case=pair에는 공통 S3 기울기·낙하·비유한 상태 중단이 적용됐다.
손가락 접촉 소실은 지속상승 실패로 평가했으며, 별도 S2 r3 감시가 실행됐다고 주장하지 않는다.
현재 코드의 진단 bundle 표기는 실제 공통 감시 이름으로 바로잡았고 회귀 시험으로 고정했다.
완료된4384d61c 원본은 고치거나 재봉인하지 않았다.

**다음 제안:** 비대칭 포착 중심을 확인하고, 차체 정지 후 팔로 잔여 오차를 줄이는 표준 접근을
별도 사전 등록해 짧게 검증한다. 이번 자료로 선택한 설정을 확증 자료로 재사용하지 않는다.

**원본:** `/Users/changmin/projects/ugrp/outputs/oracle-runs/s3fix14-diagnostics-r1` (원격 `~/ugrp-sim/runs/s3fix14-diagnostics-r1/`도 보존).
전체 파일·sha256 대조는[retrieval.json](retrieval.json), 상세 수치는[diagnostic-summary.json](diagnostic-summary.json).
새 렌더 없이 저장 자기 RGB로 만든 명목r1/r2/r3 4배속 영상은 각`delivery/r*/execution.mp4`에 있다.
최종 관련 로컬 시험8개 통과(진단7개 + 카탈로그 계획1개). Mac 물리·렌더·재생0, 모델 호출0, CI 대기·병합0.
새 카탈로그 조각만 추가했으며 중앙JSON은origin/main SHA256
`fc5bdf913a9f672bb3adb9597e1925b88a163a7ce1a1b30fb4fed9cf7ad0c813`와 바이트 동일하다.

## TensorBoard 전달

[고정 지표 대시보드](http://127.0.0.1:6006/?runFilter=%5E1010-s3fix14-capture-v1%2F&pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcapture_n%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fgrasp_n%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flift_n%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fn%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fexecuted_cases%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fplanned_cases%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fhost_errors%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0#timeseries) — 새 스냅샷 `1010-s3fix14-capture-v1`,
9개 뷰·175개 scalar·대표4배속 영상3개. 원본→event→실행 중인 서버 API를 모두 대조했고,
모든 영상Range206/전체 해시/실제 디코딩을 확인했다. Chrome 강에서9개 실행·고정10개 카드,
상승29/29/19와집기53/51/34를 확인했으며 HParams의case/policy/seed/source_sha 열을 적용했다.
[대표r3 영상](http://127.0.0.1:6007/video/c89125eba2897b1f41d6)은3.05초 끝까지 재생했다.
[기존 학생10조건 기록](../2026-10-10-s3-settled-servo/README.md)은 별도 기준선으로 남기며
이번 평가용225점과 성공률·속도 개선율을 합산하지 않는다. 기존 공용 서버PID52016과 이전 스냅샷은 보존했다.
[tensorboard-verification.json](tensorboard-verification.json), [보기 설정](dashboard.json).
