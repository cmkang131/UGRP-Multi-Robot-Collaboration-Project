# 공용 자기 명령 구동 모델 — drive_model_deadband_v1

기본 **off**. M1의 명령=바퀴속도 가정과 M2의 임시 요 상수를,
v7의 입력 릴레이·무부하 전류 손실·확인된 감쇠에서 유도한 같은 모델로 선택적으로 바꾼다.
자기 발행 바퀴 명령과 시간, 고정 모터/치수만 받는다. GT·접촉·실측 관절은 입력하지 않는다.
실물에는 실제 모터 사양과 별도의 고정 보정이 필요하다. 현재 숫자는 실물 검증값이 아니다.

## 소스 범위와 유도

기준 main `328b4e1d2a4abe245620a58b35ea96ddc1450ef1`에는 M1/M2와 실행기들이 없다.
이 PR은 독립 공용 함수 및 M1/M2 모듈을 main에 추가한다.
M1은 #484 `4fdf7f84`의 `grasp_act_visible_world.py`, M2는 #500 `fd724191`의
`visible_belief.py`를 바탕으로 했다. M1의 순수 Python 의존성인 `grasp_act_contract.py`는
#484와 #500에서 바이트가 같은 파일을 그대로 가져왔다.
원본 ref·전체 SHA·파일 SHA-256은 [sources.json](sources.json)에 있다.
각 소비 브랜치의 실행기 연결은 아래 표대로 적용해야 한다. 이 PR 자체가 그 실행기들을 켜지는 않는다.

`harness/drive_model.py`는 시뮬레이터를 import하지 않는 고정 모델이다.

- `bk = I0 / Is = 0.1 / 1.2 = 1/12`.
- v7과 같은 signed relay: 정지/방향 반전에서는 `|u| > 0.325`로 시작,
  같은 방향에서는 `|u| > bk`까지 유지. 그 외 source torque는 0.
- 켜진 바퀴의 `tau = T0 × (u − sign(u) × bk)`;
  확인된 `B = (T0 − T0×bk) / omega0 = 0.006867418019757396 N·m·s`.
- 무부하 정상상태 `omega = tau / B`, `omega0 = 150×2π/60 rad/s`.
  따라서 u=.35에서 `omega/omega0=.290909`, 공칭/예측=1.203125;
  u=.40에서는 .345455와 1.157895다. .40은 수식 예측만 검증했다.
- 메카넘 차체 증분은 바퀴 각 증분을 `r/4` 행렬로 변환한다.
  `r=.0325 m`, `lx+ly=.0594+.06495=.12435 m`는 저장된 v3 장면의 고정 치수다.
  OFF는 기존 M1의 .1255를 그대로 쓴다. ON의 M2 요 속도는 u=.35에서 약 1.1943 rad/s다.
- 정상상태 근사라 관성·가감속·coast·밀림·접촉/정지를 예측하지 않는다.
  발행 명령을 실제 이동이나 파지 성공으로 취급하면 안 된다.

공용 모델은 wheel relay 상태를 로봇마다 보관하며 episode 시작에 `reset()`한다.
`delta(wheels, durations_s, dt)`에는 구간 시작의 바퀴별 남은 펄스 시간을 넣는다.
펄스가 dt보다 짧으면 남은 정지 구간에서 해당 relay를 해제한다. 정지 구간도 전달해야 한다.
같은 틱에서 좌표/요/거리 갱신에 쓸 delta는 한 번 계산해 재사용한다.
기억 항목마다 같은 상태 객체를 다시 적분하면 안 된다.

## 추가 감쇠 조사와 남는 차이

[정적 감사](source-audit.json)는 빔 원본 scene.xml 40개, 장면당 바퀴 12개를 확인했다.
모두 `damping=.006867418019757396`, `frictionloss=0`, native motor·gear=1이고
actuator default 블록은 없다. wheel 위치도 위 고정 치수와 일치한다.
`masterpi_drive_friction_v7` → v6 XML → v2/v1, `v7_exact_speedups`,
`CameraRobotPort`/`set_motor_commands` 및 multi-world 초기화를 읽었다.
relay cache는 원래 parameter 속성을 전달하고 명령 설정은 ±1 clipping만 한다.
검토한 경로에서 추가 `dof_damping` 또는 `actuator_biasprm` 덮어쓰기를 찾지 못했다.
시뮬레이터 코드는 변경하지 않았다. 실제 런타임 배열을 새로 관찰한 결과는 아니다.

제공된 분석의 정상 바퀴속도 `.2666×omega0`는 `B≈T0/omega0=.00749172874882625`와 맞는다.
그 차이 **.0006243107290688542 N·m·s의 원인은 미확인**이므로 ON 계산에 넣지 않았다.
`omega≈(u−bk)×omega0`를 확정한 법칙으로 채택하지 않았다.
이 선택 때문에 M1 과대가 줄어도 약 10–15%가 남고,
이미 전진이 보정된 M2 내려놓기의 위치 차는 커진다. 기본 전환 근거가 아니다.

## 저장 원본 재계산

[결과표](results.md) · [요약 JSON](summary.json).
원본 `odometry-scale/scripts/{lib,flows,an}.py`를 바이트 그대로
`analysis_helpers/`에 보존해 loader·시각 대응·드리프트 정의를 재사용했다.
모델별 별도 계수 fitting은 하지 않았다.

- 명령 at `t_a` ↔ 평가 `[t_a,t_b]` 구간. M1의 바퀴별 duration과 M2의 기존 scalar duration
  규칙을 각각 유지하고 ON/OFF를 계산한다. M2 ON 표는 `odometry(wheels, seconds, ...)`의 기존
  호출 형태를 쓴다. 새 optional `durations_s`를 사용하는 별도 비교와 섞지 않는다.
- 경로비는 로봇별 issued/GT, 전체와 nonzero-command 구간을 별도 산출한다(각 GT 경로 >.5 m).
  최종 위치 차는 전체 GT 경로 >.3 m, 첫 GT 자세에 두 모델을 동일하게 정렬한 열린고리 적분이다.
  GT를 매 틱 모델에 넣지 않는다. 요는 공칭 M1 누적 절댓값 >20°인 로봇을 분모로 쓴다.
- 실패·중단도 제외하지 않는다. 진단 집합에는 여러 과거 SHA가 있어 단일 새 코호트 성능이 아니다.
  `r12d`, `r14d`는 release 진단의 부분집합이고, 상자 grasp/release도 같은 실행의 단계다.
  이 행들의 n을 더해 독립 실행 수로 보고하지 않는다.
- 단독 운반은 원 보고서 Markdown과 JSON이 다르다. JSON과 원본에는
  `84a1b7b8`(거의 정지) 및 `870c0c59`(interrupted)가 모두 있다. 두 행으로 분리한다.
  움직인 interrupted 1회도 완주/성공으로 표시하지 않는다.
- native_yaw_v1 자료의 외부 부호 처리 의미는 미확인이다. 여기서는 두 모델의 양의 요를
  같은 메카넘 규약으로 적분한 크기 비교이며, 실행기 부호 경로를 검증한 결과가 아니다.

재현(로컬 저장 원본만 읽음):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/analyze_drive_model_deadband.py \
  --gcp-runs /Users/changmin/projects/ugrp/outputs/gcp1-runs \
  --beam-runs /Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/beam-gate-752b0cbb/raw/grasp-search-gate40-gcp-752b0cbb \
  --out /private/tmp/drive-model-new-output
```

raw 파일은 기존 로컬 위치에 보존한다. 요약의 원본 hash 목록·개별 로봇 결과·실행 상태 파일은
zstd 압축 뒤 해제 바이트/해시를 확인했다. 새 물리·렌더·원격 실행과 모델 호출은 0이다.
실행기/폐루프·새 조건·실물 성공은 미검증이다.

## 각 흐름의 활성화 위치

아래는 소비 브랜치가 이 공용 변경을 가져간 뒤 명시적으로 켤 위치다.
다른 브랜치의 기존 profile/static_walls 등 인자는 보존하고 구동 관련 변경만 이식한다.
실행 CLI/plan/report/기록 admission에도 같은 이름·값을 남겨 이전 관문과 구분해야 한다.
기본 CLI에는 아직 이 토글이 연결되지 않았고, 이 PR 검증은 아래 API를 호출한 저장 명령 재계산이다.

| 흐름 | 켜야 하는 코드 위치 | 적용 방법 |
|---|---|---|
| 빔 #484 | `scripts/run_grasp_act_teacher.py:237`의 `VisibleWorld` 생성, `scripts/replay_grasp_act_search17.py` | `drive_model_deadband_v1=True`, `odometry='off'`; `search17_odometry='off'`. batch/admission/원장에 동일 옵션 전달 |
| 상자 잡기 #500 | `scripts/run_crate_teacher.py`의 로봇별 `VisibleWorld` 생성 | 새 bool 전달. 상자의 `profile=CRATE`, static-wall 옵션은 그대로 유지 |
| 단독 잡기 #502 | `sim/grasp_act_solo_teacher.py::primitives`, `_target`, backoff/lookback 누적 | `command_delta(..., drive_model_deadband_v1=True)`. `sim/grasp_act_teacher_v3.py::propagate_owned`의 복제된 M1 식도 같은 delta로 바꾸어 xyz/yaw를 함께 갱신. 하나만 켜면 불일치 |
| 단독 운반 #505 | `sim/solo_carry_pose.py::CommandPose.issue`, `sim/solo_carry_to_zone.py::integrate` | 두 command_delta 호출에 같은 토글. 한 자기 자세를 이중 적분하지 않고 각 소유 상태에서 한 번 계산 |
| 빔 내려놓기 #491 | `sim/grasp_act_release_teacher.py::ReleaseTeacher.dead_reckon`, `scripts/run_grasp_act_release.py`의 own-command 경로 | `odometry(wheels, seconds, drive_model_deadband_v1=True)`. 기존 외부 native_yaw 부호 처리는 별도 검증 필요 |
| 상자 내려놓기/둘러보기 #500 | 위 release teacher, `scripts/run_crate_teacher.py:817–819`의 own_la/전파용 `odometry` | 모든 소비자가 같은 토글. `gcp_probe_v1`와 동시 사용 거부 |
| 계획용 속도표 | `scripts/probe_carry_lookaround.py`의 모든 `rates(odometry)` | `rates(..., drive_model_deadband_v1=True)`; .35의 정상상태 값이며 다른 u에 선형 비례로 재사용 금지 |

함수는 기본 one-shot(정지에서 시작)으로도 호출할 수 있다. 연속 저명령 유지까지 쓸 때는
`CommandDriveModel` 하나를 로봇/episode별로 만들고 `model=`에 전달하며 정지 구간도 적분한다.
`rates`는 별도의 one-shot 계산이라 로봇의 relay 상태를 바꾸지 않는다.

## search17과 상호 배제

[#484 search17 원문](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/4fdf7f8407074572e59566ac719f398f913e9286/experiments/2026-10-14-e2e18-grasp-rootcause/search17.md#L47-L80)의
`search17_fixed_v1`는 같은 명령 과대 문제를 몸체 GT로 적합한 고정 xyz/yaw 이득이다.
새 토글은 그 문제의 **물리 기반 대체 후보**이고, 동일한 보정 품질을 달성했다는 뜻은 아니다.
제공된 독립 분석의 .749/.715/.719와 search17의 .75141578/.68525882/.71802760은 서로 다른 fit이다.
이번 공용 모델에는 어느 것도 곱하지 않았다.

`command_delta(mode='search17_fixed_v1', drive_model_deadband_v1=True)`와
`VisibleWorld(odometry='search17_fixed_v1', drive_model_deadband_v1=True)`는 즉시 ValueError다.
M2의 `gcp_probe_v1`도 동시에 켜면 거부한다. 기존 OFF/search17/gcp_probe 산술은 유지한다.
실행기 초기 옵션 검사에서도 `validate_options`를 호출해 호스트 작업 전에 거부해야 한다.

## 검증

`tests/test_drive_model_deadband.py`: **17 passed**. 실제 v7 parameter class만 AST로 추출해
릴레이 모든 방향/경계값·감쇠를 비교했으며 MuJoCo 객체를 만들지 않았다.
두 API 연결, pulse/gap/reset, mixed wheels·요 부호, 오류 입력, GT 입력 거부와 상호 배제를 검사했다.
고정 baseline 소스에서 만든 128개 입력의 OFF 및 기존 보정 결과 JSON,
M1 VisibleWorld 출력 JSON은 SHA-256이 일치했다. [시험 기록](validation.json).
저장 원장의 OFF 바이트 비교 횟수와 mismatch는 결과표/요약에 별도로 있다.
Git diff에서 기존 시뮬레이터 파일 변경은 0이다. CI에 이 시험 파일을 등록했다.

## 참고 자료 — 2026-10-15 원문 확인

1. [Maxon, DC Motor Selection for Dynamic Motion Control Applications](https://www.maxongroup.us/medias/sys_master/root/8835095625758/DC-Motor-Selection-for-Dynamic-Motion-Control-Applications.pdf?attachment=true),
   p.1–2: 전류–토크 비례, 고정 전압의 선형 토크–속도와 전압 변화 시 평행 이동.
   이 일반 법칙은 v7의 특정 bk/감쇠 수치나 실제 MasterPi 모터를 검증하지 않는다.
2. [Northwestern, Brushed DC Motor Theory](https://hades.mech.northwestern.edu/index.php/Brushed_DC_Motor_Theory),
   Equations: 전압·저항·역기전력, `tau=kM*i`, 정상상태 식.
   DC 정상상태 유도의 근거로만 썼다.
3. [Taheri, Qiao, Ghaeminezhad (2015), Kinematic Model of a Four Mecanum Wheeled Mobile Robot](https://research.ijcaonline.org/volume113/number3/pxc3901586.pdf),
   §2, eq.6–12, p.7–8: 바퀴 위치와 각속도에서 차체 속도로의 기구학.
   실제 구현의 바퀴 순서/부호는 저장소의 `(FL,FR,RL,RR)` 규약에 맞췄다.
4. 저장소 `sim/masterpi_drive_friction_v7.py`의 `DriveParameters`·`command_step`,
   v6 `transform_xml` 및 저장 XML 40개: 이 프로젝트 수치의 직접 근거.
   제공된 `odometry-scale/report.md`, `summary.json`, scripts는 측정 근거이며
   source/hash를 [sources.json](sources.json)에 기록했다. 추가 감쇠의 출처로 대신 인용하지 않았다.
