# 공용 자기 명령 구동 모델 — drive_model_deadband_v1

기본 **off**. M1의 명령=바퀴속도 가정과 M2의 임시 요 상수를,
v7 입력 릴레이·DC 감쇠에 저장된 접촉 구름 손실과 일차 ODE를 더한 모델로 선택적으로 바꾼다.
최신 수정 라운드는 [contact-ode 결과표](contact-ode/results.md)·[요약](contact-ode/summary.json)이며,
기존 results.md/summary.json/validation.json은 `01703ed2`의 직사각 모델 기록으로 보존한다.
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
- 접촉 구름 손실을 반영한 정상상태는 `|omega| = max(0, T0*(|u|-bk)-τc)/(B+b1)`.
  `τc=1.857e-3 N·m`, `b1=2.86e-5 N·m·s`(바퀴당)는
  `experiments/2026-10-06-drive-friction/v7-results.json`의 **v7-empty-forward-u035/050/100**
  (`rows[3:6]`)에 저장된 4바퀴 평균 속도와 모터 토크의 잔차를 직선 적합한 값이다.
  u=.35/.50/1.0의 저장 정상 비율 .2727/.4354/.9787을 ±1% 이내로 재현한다.
  세 점은 적합 자료이며 독립 검증이 아니다. `u-bk`만으로 속도를 계산하지 않는다.
- 펄스는 `I_eff * dω/dt = τmotor - (B+b1)*ω - τc*sign(ω)`를 각 구간에서 해석적으로 적분한다.
  속도 0을 지나는 시점에서 구간을 나누며, 정지 중 `|τmotor|<=τc`면 붙어 있는 상태를 유지한다.
  반전·바퀴별 명령 종료·명령 없는 감속을 처리한다. 릴레이 상태와 예측 속도는 별도다.
- `I_eff=3.85e-4 kg·m²`는 질량/XML 어림이다. 빔 gate episode-016 scene.xml에서
  질량 1.1 kg의 병진 환산 `m*r²/4=2.9046875e-4`, 허브 y축 관성 `4.49468085e-5`,
  armature `2e-5`, 9개 롤러의 `Σ[m*(x²+z²)+max(diaginertia)]=3.04469039e-5`를
  더하면 `3.85862462e-4`다. 롤러를 함께 회전하는 물체로 근사한 상한 쪽 어림을 반올림했다.
  실제 메카넘 결합·자유 롤러·하중별 유효 관성은 식별하지 않았다. 원본 분석의
  `2e-4..3.85e-4` 민감도에서 고립 펄스 총 이동은 약 13.20..12.62 mm다.
- 메카넘 차체 증분은 바퀴 각 증분을 `r/4` 행렬로 변환한다.
  `r=.0325 m`, `lx+ly=.0594+.06495=.12435 m`는 저장된 v3 장면의 고정 치수다.
  OFF는 기존 M1의 .1255를 그대로 쓴다. 별도의 몸체 GT 이득은 곱하지 않았다.
- u=.35의 **0.1초 고립 펄스 + 완전 감속**은 12.616 mm로, S3 실측 12.9 mm의
  요청 허용 범위 12.6–13.2 mm 안이다. 첫 .1초 이동만은 7.442 mm이고 그 뒤 5.175 mm를 더 간다.
  M2 ON `rates()`는 이 검증을 거친 펄스 이동/.1초인 **.126164 m/s**를 쓴다.
  기본 OFF의 경험값 .129는 유지한다. rates와 .1초 시점의 순간 적분값을 혼동하지 않는다.
- ON 요 계획 상수는 같은 펄스/기하에서 **1.0146 rad/s**(실측 약 1.03 대비 −1.5%)다.
  요에 병진과 같은 손실을 적용할 수 있는지는 **미확인**이다. 정상 속도 기반 요 예측은 약 1.119 rad/s다.
  저장 r14d 요 진단은 새 모델 요 경로비 .815로 과소 추정한다(2로봇).
  횡이동도 별도 손실 계수가 필요할 수 있다(기존 GT-fit 횡 .715, 전진 .749;
  접촉 미끄럼 횡 .015 m/s, 전진 .00014 m/s). 이번에 횡 전용 계수는 넣지 않았다.
- 외력·충돌·실제 하중 변화는 예측하지 않는다. 발행 명령을 실제 이동이나 파지 성공으로 취급하면 안 된다.

공용 모델은 wheel relay와 명령만으로 예측한 각속도 상태를 로봇마다 보관하며 episode 시작에 `reset()`한다.
`delta(wheels, durations_s, dt)`에는 구간 시작의 바퀴별 남은 펄스 시간을 넣는다.
펄스가 dt보다 짧으면 해당 relay를 해제하고 남은 구간의 감속 이동까지 적분한다. 정지 구간도 전달해야 한다.
같은 틱에서 좌표/요/거리 갱신에 쓸 delta는 한 번 계산해 재사용한다.
기억 항목마다 같은 상태 객체를 다시 적분하면 안 된다.

## 접촉 손실의 근거와 한계

접촉을 제거한 `v7-motion-no_contact-u035`(`rows[12]`)는 `omega/omega0=.290909`를 재현한다.
추가 DC 점성 감쇠가 있다는 이전 해석을 철회한다. 기존 [정적 감사](source-audit.json)의 XML 40개에
기록된 `B=.006867418019757396`, `frictionloss=0`, native motor·gear=1과도 일치한다.
새 τc와 작은 b1은 **롤러–바닥 접촉 잔차**다. 손실이 소산되는 세부 기구는 미식별이며,
과거 한 속도에서 환산한 .000624 N·m·s를 실제 감쇠로 더하지 않는다.

원본 분석의 .2666은 정상 속도가 아니라 펄스 구간 평균이다. 접촉 손실과 듀티 효과를
분리하며, 약 ×.973의 듀티 손실을 고정 이득으로 또 곱하지 않고 ODE로 계산한다.
분석 원문·수치 근거·XML·해시는 [이번 라운드 근거](contact-ode/calibration.json)에 기록했다.
빈 로봇 직진 3점의 적합은 하중·횡·요·실물 검증을 대신하지 않는다.

## 저장 원본 재계산

[최신 4모델 결과표](contact-ode/results.md) · [요약 JSON](contact-ode/summary.json).
원본 `odometry-scale/scripts/{lib,flows,an}.py`를 바이트 그대로
`analysis_helpers/`에 보존해 loader·시각 대응·드리프트 정의를 재사용했다.
GT-fit 비교에는 기존 `odometry-scale/scripts/m3.py`의 .749/.715/.719를 그대로 쓴다.
새 모델에는 몸체 GT 적합 계수를 넣지 않았으며 접촉 손실 2개 모수만 저장 바퀴 속도 3점에서 가져왔다.

- 명령 at `t_a` ↔ 평가 `[t_a,t_b]` 구간. M1의 바퀴별 duration과 M2의 기존 scalar duration
  규칙을 각각 유지하고 M1/M2/GT-fit/새 모델을 계산한다. M2 흐름의 새 모델 표는 `odometry(wheels, seconds, ...)`의 기존
  호출 형태를 쓰되 같은 평가 구간에 남은 감속 이동도 더한다. 새 optional `durations_s`를 사용하는 별도 비교와 섞지 않는다.
- 경로비는 로봇별 issued/GT, 전체와 nonzero-command 구간을 별도 산출한다(각 GT 경로 >.5 m).
  최종 위치/요 차는 전체 GT 경로 >.3 m, 첫 GT 자세에 네 모델을 동일하게 정렬한 열린고리 적분이다.
  GT를 매 틱 모델에 넣지 않는다. 요 drift는 최종 최단각 절댓값이고, 요 경로비는 공칭 M1 누적 절댓값 >20°인 로봇을 분모로 쓴다. solo 원장에는 yaw가 없어 미측정으로 표시한다.
- 실패·중단도 제외하지 않는다. 진단 집합에는 여러 과거 SHA가 있어 단일 새 코호트 성능이 아니다.
  `r12d`, `r14d`는 release 진단의 부분집합이고, 상자 grasp/release도 같은 실행의 단계다.
  이 행들의 n을 더해 독립 실행 수로 보고하지 않는다.
- 단독 운반은 원 보고서 Markdown과 JSON이 다르다. JSON과 원본에는
  `84a1b7b8`(거의 정지) 및 `870c0c59`(interrupted)가 모두 있다. 두 행으로 분리한다.
  움직인 interrupted 1회도 완주/성공으로 표시하지 않는다.
- native_yaw_v1 자료의 외부 부호 처리 의미는 미확인이다. 여기서는 네 모델의 양의 요를
  같은 메카넘 규약으로 적분한 크기 비교이며, 실행기 부호 경로를 검증한 결과가 아니다.

재현(로컬 저장 원본만 읽음):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/analyze_drive_model_deadband.py \
  --gcp-runs /Users/changmin/projects/ugrp/outputs/gcp1-runs \
  --beam-runs /Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/beam-gate-752b0cbb/raw/grasp-search-gate40-gcp-752b0cbb \
  --out /private/tmp/drive-model-new-output
```

이번 재생은 기존 원본 2,736파일을 모두 같은 해시로 유지하고 같은 로컬 경로의 추가 상자 진단 10실행(66파일)을 포함했다.
관문 코호트는 그대로이며 진단 행의 분모만 증가했다. 총 2,802파일을 다시 해시 검증했다.
상태 원장은 complete 213 / interrupted 10 / HOST_ERROR 6 / status 미기록 253개 디렉터리다.
status 미기록을 완료로 간주하지 않으며, 저장 구간의 계산 완료와 실제 실행 완료는 구분한다.

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
| 계획용 속도표 | `scripts/probe_carry_lookaround.py`의 모든 `rates(odometry)` | `rates(..., drive_model_deadband_v1=True)`; .35 고립 .1초 펄스+감속의 이동/.1초이며 다른 u·듀티에 선형 비례로 재사용 금지 |

함수는 기본 one-shot(정지에서 시작)으로도 호출할 수 있다. 연속 명령·가속·감속 이력을 유지하려면
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

`tests/test_drive_model_deadband.py`: **22 passed** (접촉 ODE 수정 라운드). 실제 v7 parameter class만 AST로 추출해
릴레이 모든 방향/경계값·기존 DC 감쇠를 비교했으며 시뮬레이터 객체를 만들지 않았다.
저장 정상값 3점 ±1%, 고립 펄스 12.6–13.2 mm, 반복 .07/.1 듀티, 구간 분할 불변성·반전·정지를 검사했다.
두 API 연결, pulse/gap/reset, mixed wheels·요 부호, 오류 입력, GT 입력 거부와 상호 배제를 검사했다.
고정 baseline 소스에서 만든 128개 입력의 OFF 및 기존 보정 결과 JSON,
M1 VisibleWorld 출력 JSON은 SHA-256이 일치했다. [이번 시험 기록](contact-ode/validation.json).
저장 원장의 OFF 바이트 비교는 475,991회(중복 포함), 불일치 0회다.
기본 OFF·기존 고정 보정 출력은 바뀌지 않았다. 소스·압축/해제 해시도 대조했다.
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
   source/hash를 [sources.json](sources.json)에 기록했다.
5. 이번 접촉 보정의 직접 근거: `v7-results.json`의 `v7-empty-forward-u035/050/100`,
   반증 행 `v7-motion-no_contact-u035`, 제공된 `odometry-scale/damping_analysis.md` 2·3·5·7절.
   [고정 원문 사본](contact-ode/damping_analysis.md)·[해시/수치](contact-ode/calibration.json).
