# MasterPi 구동 검토와 접촉 구동 후보 (2026-10-06)

**v7 DEV 후보 채택 — 실물 보정 전.** 현재 진단 workflow는 **7.1.0**이며,
`masterpi_drive_friction_v7`을 명시적으로 선택한다. 무하중·cyan의 20/30 정지와
35/50/100의 5초 지속 주행을 확인했다. 옆 이동 yaw −2.49°와 실물 측정·카메라 보정은 남은 과제다.
기본값·기존 번들·v102/v106·카메라·팔/물체 접촉은 변경하지 않는다.
v1/v2 NOT_READY와 workflow 2.0.0은 아래에 보존한 과거 판정이며 현재 채택 상태가 아니다.
새 RGB 번들 번호는 예약하지 않았다. 이번 PR 수정에서는 시뮬레이션과 PR 병합을 하지 않는다.

독립 리뷰의 제어기 경로 점검에서는 **50개 중 45개가 v7에서 멎는 호환성 문제**가 지적됐다.
이는 새 물리 실행 50회의 결과가 아니며 v7 채택이 기존 제어기의 통과를 보장하지 않는다.
특히 기존 `_fast_drive_kernel` 가속 경로가 설치된 상태로 v7의 물리 스텝에 들어가면
`HysteresisWorld._physics_step_for`가 **RuntimeError**를 내므로 동시 사용은 지원하지 않는다.

## 현재 모델과 결과 해석

`sim/masterpi_dynamics_v2.py:1268` 및 `sim/multi_masterpi_production.py:1454`:
정규화 바퀴 명령을 0.085 s 1차 필터에 넣고, 네 바퀴 명령의 조합을 앞·옆·회전 성분으로 만든다.
`Fx=2.2*u_forward-1.4*vx`, `Fy=1.65*u_left-1.4*vy`, `Tz=.12*u_yaw-.08*w`를
차체 방향에서 세계 방향으로 돌려 `xfrc_applied`에 직접 넣는다(기본 미보정 값).
정지 명령 때 감쇠는 18 N/(m/s), .8 Nm/(rad/s)이다. 별도 정지마찰 임계값은 없다.
실제 바퀴 actuator는 최대 .002 Nm, 목표 12 rad/s, 지지 실린더 마찰 .001로 보조 역할이다.
`exact_speedups.ExactDriveKernel`은 이를 같은 산술 순서로 빠르게 실행한다. 새 바퀴 물리가 아니다.

따라서 바퀴가 바닥에서 떨어져도 직접 추진력이 남고, 바퀴별 수직하중·마찰 한계와 추진력 사이의 연결이 없다.
하중은 MuJoCo의 질량·관성·팔과 집게 접촉으로 작용하지만 추진력 한계는 그 하중에 비례하지 않는다.
짝 운반에서 빔과 집게를 통한 힘 전달은 실제 접촉이다. 반대 로봇의 저항은 주로 차체 감쇠와 지지 마찰이다.
예를 들어 정지 로봇의 단순 정상상태 근사는 외력 1 N / 18 = .0556 m/s라서, 작은 힘에도 계속 밀릴 수 있다.
움직이는 동안에는 감쇠가 1.4로 낮아져, 그 외력을 정지마찰로 버티는 실제 바퀴/기어와 차이가 커진다.
이것은 가능한 원인 분석이며 과거 모든 위치 오차를 이 원인으로 확정한 것은 아니다.

[v102](../2026-10-05-loaded-gain-calibration-v102/README.md)는 기존 SIM의 명령→변위 곡선을 맞춘
DEV 보정이다. 약 7.2% 과주행의 기존 원인 판정(보정 범위 밖 게인 외삽)은 유지된다.
새 물리에서도 그 계수나 1.02 s 시간상수가 맞는다는 증거는 아니다.
[v106](../2026-10-05-solo-cyan-v106/README.md)은 그 하중 이동 계수와 s911 방향 결합 보정을 사용했다.
시야 가림으로 위치 재관측이 끊긴 별도 원인도 있으므로 구동을 바꾼 것만으로 위치 문제가 해결됐다고 할 수 없다.
과거 성공·실패는 기존 물리 내부 결과로 남으며 실물 미끄러짐/힘 성능의 증거로 승계하지 않는다.

## 방법 비교와 선정 (측정 전에 고정)

| 방식 | 장점 | 한계/선택 |
|---|---|---|
| 직접 차체 힘(기존) | 빠르고 기존 재현 가능 | 바퀴 접지와 추진력이 분리됨; 그대로 보존 |
| 일반 실린더 + 높은 마찰 | 단순, 일반 바퀴에 적합 | mecanum 옆 이동을 일반 타이어의 옆 미끄럼으로 오해; 채택하지 않음 |
| 방향성 마찰 + 바퀴 토크 | 롤러 자유도를 줄여 빠름(Okada 2023) | 접촉 좌표축을 바퀴에 맞춰야 함. `geom friction`의 3개 값은 x/y 마찰이 아님. MuJoCo는 pair에서 5개 계수 지원. 이번에는 접촉 프레임 재작성 복잡성을 피함 |
| 수동 롤러 hinge + 바퀴 actuator + 접촉 | 표준 강체/마찰 해법 그대로; 공중에서는 추진 불가 | 접촉 수/비용 증가, 롤러 단순 형상·베어링 측정 필요. **이번 후보** |

v3의 기존 9개 capsule 롤러를 각각 자유 hinge에 붙이고 동일한 중심/크기/재질로 접촉을 활성화한다. 기존 장식 롤러의 좌우 기울기는 공식 ABAB 도면과 반대여서 새 프로필에서만 바로잡는다.
45도 기울어진 롤러가 수동 회전하고 바닥 마찰이 추진력을 만든다. 지지 실린더의 충돌은 끈다.
차체 wrench·인위적인 제동 감쇠·실시간 위치 보정·weld를 사용하지 않는다. 정지 명령은 모터의 속도-토크 기울기로 저항한다.
`kv=torque_cap/omega_no_load`인 bounded velocity actuator는 선형 DC 모터의 토크-속도 근사이다.
원래 저수준 모터 값과 같은 명령→속도 곡선이라고 가정하지 않는다. 새 프로필은 `exact-v1` 등을 거부한다.

## 수치 출처와 미확인 사항

- **공식 확인:** MasterPi 본체 1.1 kg(포장 1.6 kg과 구분), 65 mm 바퀴, 45° 롤러, TT 모터.
  차체/팔/카메라는 v3 그대로, 바퀴 질량 .05 kg은 기존 미보정 값 그대로 합계를 보존한다.
- **구조 근사:** 롤러 9개·반지름 5.8 mm·capsule 길이는 기존 v3의 사진 추정 형상이다.
  단단한 hub와 capsule 부피를 사용해 같은 밀도로 .05 kg을 분배한다. 실측 관성·밀도라는 뜻이 아니다.
  베어링은 이상적인 무마찰 hinge, 기존 바퀴 armature .00002 kg m²는 보존(미보정).
- **탐색용 모터 후보:** Hiwonder 일반 TT 제품의 150 rpm, encoder TT 제품의 1.2 kgf cm = .1176798 Nm를
  속도 기준/토크 상한의 참고값으로 사용한다. **두 제품이 장착 모터와 같다는 근거는 없으며,
  1.2 kgf cm가 stall torque인지도 미확인이다.** 이 조합은 부품 유사 후보이지 MasterPi 사양 일치 판정이 아니다.
  완성 로봇의 최대 속도는 미확인. `150 rpm * pi * .065 / 60 = .51051 m/s`는 무부하 원주 속도의 계산값이다.
  공식 튜토리얼의 ±100 mm/s API 설명을 완성차 최대 속도로 사용하지 않는다.
- **마찰:** sliding_mu=1은 MuJoCo 공식 기본값. MasterPi의 고무/실험 바닥 계수는 미측정이다.
  2026 asRoBallet은 다른 로봇의 마찰 민감도/실측 필요성 참고이며 그 값이나 성능을 이 로봇으로 옮기지 않는다.
  torsional/rolling friction=0, condim=3으로 이상적인 수동 롤링을 명시한다.
- 시험 결과를 보고 위 값을 맞추지 않는다. 실물용 채택에는 모터 식별·부하별 RPM/토크·바닥 마찰·정지/역구동 측정이 필요하다.

## 유한 확인 계획과 실행

직진·옆·회전(.2 명령), 정지, 1 N 옆 밀기, 접촉 제거, 최대 명령을 각 1.5 s + 정지 1 s로 확인한다.
cyan은 표준 Scene 물체를 HIGH 집게에 초기 배치하는 진단이며 집기 성공이 아니다. 실제 접촉 유지/낙하를 기록한다.
무하중/하중을 분리하고 제어 명령에 평가 좌표를 되돌리지 않는다. 원본은 기본 체크아웃 `outputs/`에만 새로 쓴다.
`status == null` 확인 후 드라이버 자기 PID로 원자적 잠금을 잡고 `finally`에서 자기 PID/브랜치를 확인해 해제한다.

```sh
python3 scripts/ugrp_session.py run drive-friction-CASE -- \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.sim_cli workflow run masterpi-drive-friction-probe --record /Users/changmin/projects/ugrp/outputs/drive-friction-record-NEW-ID -- \
  --expected-source-sha SHA --drive-profile masterpi_drive_friction_v1 \
  --cases rest forward left turn push no_contact rated_speed \
  --output /Users/changmin/projects/ugrp/outputs/drive-friction-NEW-ID
```

실행/결과/실패·wall/SIM·TensorBoard 기록은 아래에 있다. 실물·짝 빔·v106 완주 검증은 없다.

## 다시 해야 하는 검증

1. 장착 모터/전압/기어비/정지 명령의 coast 또는 brake를 확인하고, 무하중/하중·전후/좌우/회전 응답과 바닥 마찰을 실측한다.
2. 새 물리에 대해 무하중 v101·하중 v102의 gain/deadband/시간상수/정지거리/방향 결합·PF 잡음을 새 파일로 다시 보정한다.
3. cyan 가림·내려놓기/재관측/재집기를 포함한 v106과 짝 빔의 반대 명령·정지·회전·집게 이탈을 새 번들에서 재검증한다.
4. 기존 빠른 drive_kernel과 렌더/스텝 배치를 새 물리로 별도 이관하고 wall/SIM·카메라 타이밍·명령 lease를 재검증한다.
5. DEV와 stop-ON E2E/연구 코호트는 분리하고, 실물 결과를 얻기 전에는 SIM-to-REAL 완료로 부르지 않는다.

## 참고 자료 (2026-10-06 조회)

- [Hiwonder MasterPi 제품/도면](https://www.hiwonder.com/products/masterpi): 1.1 kg, 65 mm 도면, 외관. 확인.
- [Hiwonder MasterPi 구동 튜토리얼](https://wiki.hiwonder.com/projects/MasterPi/en/latest/docs/6.motion_control_course.html): 45° roller 및 명령 API. 확인.
- [일반 TT 모터](https://www.hiwonder.com/products/high-quality-tt-motor): 3–6 V, 150 rpm, 1:42. 확인; 장착품 동일성 미확인.
- [encoder TT 모터](https://www.hiwonder.com/products/tt-motor-plastic): 150 rpm, 1.2 kgf cm. 확인; 장착품 동일성·stall 정의 미확인.
- [MuJoCo 모델링](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters), [XML actuator/geom](https://mujoco.readthedocs.io/en/stable/XMLreference.html): Coulomb 접촉, condim, 마찰 혼합, velocity actuator. 확인.
- [MuJoCo 공식 car.xml](https://github.com/google-deepmind/mujoco/blob/main/model/car/car.xml): 관절 구동+바퀴 접촉의 공식 공개 예. 확인.
- [Matsinos 2012](https://arxiv.org/abs/1211.2323): mecanum 힘 분해와 저항의 고전적 모델. 초록 확인, 본문 계수 미사용.
- [Okada et al., ICAR 2023](https://doi.org/10.1109/ICAR58858.2023.10406382): 고정 롤러+방향성 마찰. 2025 논문 참고 문헌으로 서지 확인, 원문/재현 코드 미확인.
- [Schönbach et al., 2025 논문](https://arxiv.org/html/2510.10273v1), [공개 구현](https://github.com/AIS-Bonn/tiago_isaac): passive revolute roller·collision approximation과 실측 가속 곡선 필요성. 본문/README 확인; 이 코드의 실행 재현은 하지 않음.
- [MuJoCo mecanum 공개 예](https://github.com/Roundly/Mujoco-omni-mecanum/blob/main/wheel_example.xml): 수동 roller joint+접촉 기하. 코드 확인; 형상/질량 값은 복사하지 않음.
- [asRoBallet 2026](https://arxiv.org/html/2604.24916v1): MuJoCo explicit roller·마찰 모델/실측의 최근 연구. 다른 구형 로봇이며 MasterPi 성능 근거는 아님.

## 실행 기록

- `995ff901` 구조 검사 5 passed. 첫 호출은 다른 Codex 카메라 진단 잠금으로 시작 전 거부.
- 두 번째 호출은 초기 정지까지 실행 후 기록 코드가 `robot_mass_kg` property를 함수로 불러 HOST_ERROR.
  표준 NamespacedMasterPi API를 확인해 읽기만 고쳤으며 물리 수치는 바꾸지 않음.
  원본: `/Users/changmin/projects/ugrp/outputs/drive-friction-995ff901-forward{,-record}`. 실패 원본 보존.

- `5f04f473` 무하중 7조건 완료: 직진 .08077 m/s, 옆 명령이 반대로 -.07026 m/s, 회전 .02219 rad/s.
  이는 기존 장식 롤러를 그대로 물리화했을 때의 잘못된 handedness 진단이며 채택 결과가 아니다.
  공식 Hiwonder top-view 도면과 WPILib 운동식으로 부호를 확인했다. FL/RR의 위쪽 roller 축은 forward-left이고
  접지점에서는 `vx-vy=r*w`; FR/RL은 `vx+vy=r*w`여야 한다. 크기/마찰/모터 값은 유지하고 축/해당 그림 기울기만 반전한다.
  이 변경은 새 프로필 내부에만 존재하며 과거 v3 source/번들/사진 자료를 수정하지 않는다.
  [공식 배치 도면](https://wiki.hiwonder.com/projects/MasterPi/en/latest/assets/image4.CoSpVv9z.webp),
  [WPILib 표준 mecanum 좌표계/운동학](https://docs.wpilib.org/en/stable/docs/software/kinematics-and-odometry/mecanum-drive-kinematics.html).
- 접촉 제거 시 차체 기준점은 내부 모터 반작용으로 움직일 수 있어 **로봇 전체 질량중심** 변위를 함께 기록한다.
  기준점 변위만을 공중 추진으로 오해하지 않는다. 접촉점 상대 속도와 힘도 기록한다.

## 최종 후보의 측정과 판정

실행 SHA **`f323a7b7cfda36ec15fc0b0e6faf2a2911e550d5`**, MuJoCo **3.12.0**,
기존 Mac 환경. 무하중 7조건·기존 구동 6조건·cyan 30 g 하중 5조건 = **18개 짧은 진단**이다.
조건별 한 번이며 통계적 코호트나 실물 성능 측정이 아니다. 속도는 명령 시작 뒤 1.0–1.5 s 평균,
변위/회전은 1.5 s 명령과 1.0 s 정지 전체다. `steady`라는 필드명은 정상상태 수렴을 보장하지 않는다.
같은 .2 정규화 명령이지만 actuator 환산이 다르므로 같은 속도에서의 성능 비교나 개선율로 해석하지 않는다.

| 확인 | 기존 차체 힘 구동 | 새 접촉 구동 | 판정 범위 |
|---|---:|---:|---|
| 무하중 직진 속도 | .23474 m/s | .08084 m/s | 다른 명령→속도 곡선, 재보정 필요 |
| 무하중 직진 접촉점 미끄럼 | .20247 m/s | .000581 m/s | 해당 명령의 접촉점 상대 접선 속도 |
| 접촉·중력 제거 시 질량중심 이동 | +x .254945 m | 전체 약 2.76e-8 m | 새 프로필은 내부 바퀴 토크만으로 추진하지 않음 |
| 정지 명령 + 옆 1 N 외력 | y .082269 m | y .00000229 m | 고정 외력 진단; 실제 빔 또는 실물 정지력 측정 아님 |
| 무하중 옆 명령 | .17449 m/s, 총 -2.05° | .03407 m/s, 총 **-20.50°** | 새 프로필의 원치 않는 회전, **실패** |
| 무하중 회전 명령 | .28775 rad/s | .29307 rad/s, y 속도 -.03476 m/s | 새 프로필의 원치 않는 병진, **미해결** |
| cyan 직진 | 미실행 | .06836 m/s | 물체가 미리 잡힌 진단 상태 |
| cyan 옆 명령 | 미실행 | .03055 m/s, 총 **-20.49°** | 같은 문제 재발, 추가 물리 중단 |
| 최대 명령 직진 | 미실행 | .45856 m/s | 유사 TT 150 rpm 기준 원주 속도 .51051 m/s; 장착품/최대속도 일치 미확인 |
| 직진 wall/SIM | .4764 | .7595 (cyan .8583) | 계측 포함, 렌더 제외; 반복 속도 벤치마크 아님 |

정상 구동 때 새 프로필의 차체 외력 기록은 0이며, 접촉 제거 때 바퀴 접촉 수는 0이다.
무하중 정지의 평균 x/y 속도는 각각 1.77e-6/-0.91e-6 m/s였다.
18개에서 MuJoCo 경고·낙하는 없었으나 이는 구동 적합성 통과가 아니다.
cyan 최저 높이는 약 .141 m로 초기 .143 m 부근을 유지했다. 집기/운반 성공으로 세지 않는다.

옆 이동 때 앞 두 바퀴가 약 .02 rad/s로 거의 멎고 뒤 두 바퀴가 약 ±2.2 rad/s로 움직인다.
이는 회전 편향과 함께 관찰됐지만 **근본 원인은 분리 검증하지 못했다**.
기존 장식 capsule은 실제 배럴형 롤러의 바깥 윤곽을 정확히 만들지 않으며, 모터/바닥도 미보정이다.
이 때문에 1 N을 잘 버틴 결과에도 접촉이 걸리는 효과가 섞였을 수 있다. 실물에 가까워졌다는 판정은 보류한다.
임의로 마찰·토크를 올리거나 테스트 기대값을 맞추지 않았다. 짝 빔·loaded legacy·v106·추가 렌더는 중단 후 실행하지 않았다.

## 원본, 재현, 검증 기록

- 최신 원본: `/Users/changmin/projects/ugrp/outputs/drive-friction-f323a7b7-{empty,legacy,cyan}/`.
  각 조건에 result/trace/실제 XML, 실행 루트에 SHA·명령·잠금 기록이 있다.
  해당 `-record/`에는 표준 관리 실행의 환경/소스 기록이 있다. 모든 잠금은 자기 PID로 해제했다.
- 과거 잘못된 형상 7개와 HOST_ERROR 1개도 보존했다. 총 26개 결과 행 중 25개는 유한 측정 완료,
  1개는 기록 코드 오류이며 **성공률의 분모로 합산하지 않는다**.
- 별도 시작 전 거부: 파일 직접 실행의 import 경로 오류(이후 `python -m scripts.sim_cli` 사용),
  타 작업 잠금 1회, 잘못 옮겨 적은 전체 SHA 1회. 이들은 물리 결과 수에 넣지 않는다.
  초기 잠금 거부의 관리 기록만 worktree `outputs/simulation-runs/`에 생겼고,
  기본 `outputs/drive-friction-audit-20261006/early-lock-rejection-record/`에 복사·해시 확인했다. 원본은 보존했다.
- [압축 요약](results.json), [원본 85파일 SHA-256](artifacts.sha256.json),
  [관리 기록 14파일 SHA-256](managed-records.sha256.json), [TensorBoard 검증](tensorboard-verification.json).
  raw/영상의 원격 백업은 하지 않았다. 모델 호출·학습·모델 산출물은 없다.
- 변경 모듈 시험: `.venv-sim-worker-mac/bin/python -m pytest -q tests/test_masterpi_drive_friction.py`
  **6 passed** (XML 계약·질량 합계·카메라 유지·축 부호·입력 거부). 실제 주행 적합성과 구분한다.
  전체 시험은 로컬에서 돌리지 않았으며 GitHub CI 결과는 PR에 별도로 표시된다.
- [summarize.py](summarize.py)는 완성된 JSON을 읽기만 해 기존 공식 exporter로 새 snapshot을 만든다.
  26개 run / 424개 scalar를 원본→event→실행 중인 TensorBoard API까지 대조했고 원본 85개 해시가 일치했다.
  snapshot은 `/Users/changmin/projects/ugrp/outputs/tensorboard/1006-drive-friction`이다.
  기본 `outputs/tensorboard-view.json`의 `masterpi_drive_friction_20261006` 키에 고정 링크와 열 설정을 추가했다.
- [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1006-drive-friction%2F#timeseries):
  기존 타 작업 뷰어 PID 52016의 공용 logdir를 읽었다. 서버 재시작/종료 없음.
  Chrome **강** 탭에서 고정 링크를 열었으나 이동 후와 한 번 새로고침 뒤 빈 화면이어서 UI 재시도를 중단했다.
  **실제 화면 카드·HParams 열 적용은 미확인**이다. 성공/모델 응답시간은 측정하지 않아 지표를 만들지 않았고
  렌더/영상도 없어 새 영상 등록 대상이 없다.

채택 전 다음 작업은 실제 롤러 윤곽·접촉 위치와 장착 모터를 확인한 뒤 접촉 걸림/앞뒤 하중을 분리 진단하는 것이다.
그 후에만 위 재보정 목록과 짝 빔/v106 검증을 새 버전으로 진행한다. 이번 PR은 **draft, 병합 금지**다.


## 재개: 공개 FUJI 모델 이식 v2 (측정 전 고정)

2026-10-06 사용자 재개 요청으로 공개 모델을 먼저 대조했다. **v1 파일/기존 번들은 그대로 두고**
`masterpi_drive_friction_v2`와 진단 workflow 2.0.0을 추가했다. remote 브랜치 전체의 workflow ID를
조회했고 `codex/drive-friction-model`의 1.0.0만 존재했다. PR #402 draft/병합 금지 유지.

| 공개 기준 | 실제 확인한 설정 | 사용 판단 |
|---|---|---|
| [Menagerie robot_soccer_kit](https://github.com/google-deepmind/mujoco_menagerie/tree/f054586a8e90465d49ee5be15335c4a0c7f57caf/robot_soccer_kit) | 20개 수동 롤러/바퀴, 원통 접촉, 기본 condim=3/friction, CAD 관성. README가 정밀 system identification 없음을 명시 | 옴니휠이며 메카넘의 45° 구성과 다름. 직접 대체하지 않음 |
| [JunHeonYoon MuJoCo](https://github.com/JunHeonYoon/mujoco_mecanum/tree/4d0fb46f363fc23fe4eb58653a6a4653e73a3c76) / Roundly fork | 12개 hinge, damping .1, sphere radius가 wheel radius와 같고 mass/inertia 인자가 generator에서 상수로 고정됨; force actuator 권고 | 동작 예제는 있으나 그대로 MasterPi 치수로 환산하는 데 불일치가 있어 기준으로 선택하지 않음 |
| [FUJI 공개 물리 모델](https://github.com/DaiGuard/fuji_mecanum/tree/646431a5e107448e0e2bdeeba4575db9aa3665ff) | 15개 배럴 mesh, 45° continuous joint, roller mass .3 kg / hub 2 kg, 관성·마찰 .8·damping .001·friction .0001 명시 | **이식 기준**. 아래 변경만 적용 |
| [TIAGo 논문 §III-A](https://arxiv.org/html/2510.10273v1) / [공개 USD](https://github.com/AIS-Bonn/tiago_isaac/tree/812ef55cdca2502dec6044ecddb08991ff41982d) | FUJI 생성 형상 사용, 15개/45°; 각 롤러의 6구 접촉 근사와 물리/실물 비교. USD 원문을 시스템 usdcat으로 읽어 .8 마찰·.001 damping 확인 | 출처 모델의 사용/검증 근거. 이번에는 FUJI 원본 convex barrel mesh를 그대로 써 별도 구 근사를 만들지 않음 |

**이식 내역:** `sim/assets/masterpi_drive_friction_v2/fuji_roller.stl`은 MIT 원본 바이트 그대로이며
SHA-256 `2bea3228aa5766e2ce42f4f4a46cdf4bc3e63802958fa7f0ffb9688d9393a424`와 LICENSE를 보존했다.
원문 [roller 설정](https://github.com/DaiGuard/fuji_mecanum/blob/646431a5e107448e0e2bdeeba4575db9aa3665ff/urdf/rollers.xacro),
[hub 설정](https://github.com/DaiGuard/fuji_mecanum/blob/646431a5e107448e0e2bdeeba4575db9aa3665ff/urdf/wheel.xacro).

- 길이 배율 `65/205`: 공식 MasterPi 바퀴 지름 65 mm에 맞춘 균일 축소. 바퀴 중심/폭/가시 형상/카메라는 기존 MasterPi 위치를 보존한다.
- 롤러 수 15→9: 기존 MasterPi 도면/사진 추정값. 실측 확정값이 아니다. 원본 continuous hinge와 45° 축 배치는 유지하고 원본 X 바퀴축을 MasterPi Y축으로 바꾼다.
- 원래 바퀴 합계 .05 kg 유지: `mass_scale=.05/(2+9*.3)`로 hub/roller 질량 비율을 보존한다.
  원문 관성에 `mass_scale*(65/205)^2`를 곱하고 바퀴축의 좌표 변환을 적용한다.
  roller damping/frictionloss에도 같은 관성 배율을 적용해 원문 단독 관절의 감쇠 시간/마찰 각감속 관계를 유지한다.
  **이것은 닮은꼴 이식 가정이며 실물 MasterPi의 질량 분포/베어링 식별이 아니다.**
- 원문 sliding friction .8 그대로, MuJoCo `condim=3`, torsional/rolling=0. MuJoCo 공식 표준 Coulomb 접촉으로 번역하며
  Gazebo의 kp/kd를 단위가 다른 MuJoCo solref에 복사하지 않는다. 기존 `local_contact_fine` solver를 보존한다.
- 원문 URDF의 자체 충돌 기본 OFF([SDF 공식 기본값](https://sdformat.org/spec?ver=1.12&elem=model#model_self_collide))를
  새 롤러와 **자기 로봇**의 exclude 쌍으로 옮긴다. 다른 로봇/바닥/짐과의 접촉은 유지한다.
  MuJoCo는 바로 인접한 부모-자식만 기본 접촉에서 제외하므로 롤러 몸체를 한 단계 더 만들면 차체와 접촉 후보가 될 수 있다
  ([공식 collision filtering](https://mujoco.readthedocs.io/en/stable/computation/index.html#collision-detection)).
  이전 v1의 실제 원인이 자체 충돌이었다고 아직 확정하지 않으며, 새 진단은 접촉한 자기 형상 이름/힘도 기록한다.
- MasterPi 모터의 실제 식별값이 없으므로 v1의 유사 TT 기반 bounded torque-speed 근사를 그대로 유지한다.
  TIAGo의 학습 S-curve·PID를 MasterPi에 옮기거나 모델을 호출하지 않는다.

정적 검사 **9 passed**: v1 6개와 v2 3개. 모델 compile/기구학·전체 질량 보존·108개 연속 수동 관절·45° 축·원본 mesh 해시·
자기 조립체만 제외·카메라와 가시 롤러 위치 보존을 검사했으며 physics step은 실행하지 않았다.

다음 측정은 이전과 같은 1.5 s 명령 + 1 s 정지, .2 명령/같은 HIGH 팔이다.
무하중·cyan 각각 `no_contact forward turn left`를 한 번씩 기록한다.
짝 빔으로 넘어가는 DEV 기준은 두 하중 모두 옆 이동이 왼쪽이고 총 회전 크기가 **1° 이하**, 실제 물리 실패가 없는 것이다.
1°는 이번 진단의 사전 보류 기준이며 실물 사양/연구 성공 기준이 아니다. 같은 옆 이동 문제가 두 하중에서 재발하면
더 튜닝하거나 짝 빔을 실행하지 않고 중단한다. 새로운 자료는 기존 raw와 다른 폴더에 저장한다.


## v2 재측정 결과: 채택 보류, 두 조건 재발로 중단

물리 실행 SHA **`13a8ed3289a17bdb97e94029c64a23dec53b373a`**, MuJoCo 3.12.0.
무하중·cyan 각각 접촉 제거/직진/회전/옆 이동 **4개씩 총 8개**를 한 번씩 측정했다.
명령 .2, 1.5 s 구동 + 1 s 정지, 기존 HIGH 팔/Scene/평가 구간을 유지했다.
원본 모델 이식 후 결과에 맞춰 마찰·관성·모터나 판정 기준을 바꾸지 않았다.

| 측정 | v2 무하중 | v2 cyan 30 g | 해석 |
|---|---:|---:|---|
| 접촉·중력 제거: 로봇 전체 질량중심 이동 크기 | 1.19e-7 m | 8.65e-8 m | 차체 외력 0, 바퀴 접촉 0. 접촉 없이 내부 토크만으로 추진하지 않음 |
| 직진 속도 | .09271 m/s | .09227 m/s | 장착 모터/최대속도 일치 미확인 |
| 직진 접촉점 미끄럼 | .000161 m/s | .000127 m/s | v1 .000581/.000457 m/s; 명령→속도가 달라 동일 속도 마찰 비교 아님 |
| 직진 총 회전 | -.0181° | +.0217° | 해당 단일 진단 |
| 옆 이동 속도 | .08627 m/s | .08593 m/s | 왼쪽 이동 방향 확인 |
| 옆 이동 총 회전 | **-2.04586°** | **-2.20142°** | 사전 기준 1° 초과, 두 번째 재발로 중단 |
| 옆 이동 접촉점 미끄럼 | .005836 m/s | .005972 m/s | v1 약 .0033보다 증가; 모든 미끄럼이 줄었다고 할 수 없음 |
| 회전 명령의 회전 속도 | .73458 rad/s | .61951 rad/s | 의도한 회전; 옆 속도 -.00170/-.00258 m/s도 기록 |
| 직진 wall/SIM | .96684 | .99901 | 계측 포함/렌더 제외, 단일 실행이며 속도 벤치마크 아님 |
| 옆 이동 wall/SIM | .87129 | 1.01332 | 각 실행의 load average 원본에 보존 |

접촉 제거의 cyan 조건은 로봇과 짐 사이 접촉도 제거하므로 **하중을 지탱한 공중 주행** 검증이 아니다.
차체 기준점은 내부 모터 반작용으로 움직일 수 있어 전체 로봇 질량중심으로 추진 여부를 확인했다.
전체 8개는 기록 완료(`MEASURED_DEV`)이며 임무 성공 8회라는 뜻이 아니다. MuJoCo 경고/짐 낙하 없고
새 롤러-자기 조립체 접촉 힘은 0이다. cyan 최저 높이는 접지 진단에서 약 .1434 m였다.
무하중 첫 배치 중 디스크 사용량 읽기가 겹쳤으므로 wall/SIM을 엄밀한 성능 비교로 사용하지 않는다.

v1의 옆 이동 회전 약 20.5°와 앞바퀴 약 .02 rad/s의 거의 멎음은 v2에서 약 2°와 2.6 rad/s로 바뀌었다.
그러나 **회전 편향은 사라지지 않았다**. 공개 배럴 형상·관성·자체 접촉 필터를 함께 이식했으므로
개선 또는 잔여 오차의 원인을 어느 하나로 확정할 수 없다. 기존 wrench 모델도 무하중 옆 회전 -2.05°였으나
이 수치가 비슷하다는 것이 실물 정확도 근거는 아니다. 실물 모터·9개 롤러 추정·질량·접촉/베어링은 여전히 미확인이다.

요청한 두 번 중단 규칙에 따라 **짝 빔 밀림 비교, 추가 최고속도 시험, v106 재생 및 렌더를 실행하지 않았다**.
짝 빔의 정지 저항 개선이나 v106 성공을 주장하지 않는다. 도입 전 재보정/검증 목록은 위와 같다.
이번 구현은 공개 FUJI/Gazebo 물리 모델의 MuJoCo 이식이며, 논문에서 검증된 TIAGo/PhysX 구현 그 자체나
MasterPi에서 검증된 MuJoCo 모델이 아니다. 확인한 공개 자료와 직접 실행한 범위를 구분한다.

### v2 원본과 검증

- `/Users/changmin/projects/ugrp/outputs/drive-friction-13a8ed32-{empty,cyan}/`: 결과/trace/XML/manifest.
  대응 `-record/`에는 표준 관리 실행 소스/환경 기록을 보존했다.
- 두 배치 모두 `ugrp_session.py run`에서 자기 PID로 `status=null` 확인 후 acquire/release했다.
  세션 두 개 모두 종료, 종료 직후 공용 잠금 null 확인. 다른 프로세스/서버는 변경하지 않았다.
- [요약](v2-results.json), [raw 28파일 해시](v2-artifacts.sha256.json),
  [관리 기록 4파일 해시](v2-managed-records.sha256.json), [TensorBoard 검증](v2-tensorboard-verification.json).
- 변경 구동 시험만 실행: `python -m pytest -q tests/test_masterpi_drive_friction.py tests/test_masterpi_drive_friction_v2.py`
  **9 passed** 후 물리 소스 커밋/push. 이후 물리 코드는 바꾸지 않았고, 후처리 변경은 실제 8개 결과 변환으로 확인했다.
- TensorBoard 새 snapshot `outputs/tensorboard/1006-drive-friction-v2`: 8 runs / 152 scalar를
  원본→event→실행 중인 API까지 대조했고, raw 28파일 해시도 일치했다. 기존 26 runs를 재변환하지 않았다.
- 모델 호출 0. raw는 로컬 보존이며 원격 백업으로 표현하지 않는다. 생성한 영상/모델 산출물은 없다.

- 공용 `outputs/tensorboard-view.json`에는 자기 키 `masterpi_drive_friction_v2_20261006`만 추가했다.
  저장된 고정 링크의 새 8개 + 기존 대응 11개 run을 Chrome **강**의 기존 구동 탭에서 선택했다.
  접근성 텍스트에서 7개 고정 카드와 옆 속도 .0863/.0859, 미끄럼 .0058/.0060 표시값을 확인했다.
  하지만 캡처 화면은 빈 페이지였고 HParams 선택 후에도 열 테이블이 열리지 않아 **화면/HParams 검증은 미완료**다.
  기존 타 작업 서버 PID 52016·설정·다른 작업 탭은 변경하지 않고 UI 재시도를 중단했다.
  [대시보드](http://127.0.0.1:6006/?runFilter=%5E1006-drive-friction#timeseries), 정확한 7개 고정 링크는 검증 JSON의 `url`에 있다.

## 재개 16:40: 실물 입력 dead zone 조사와 v3 사전 계획

사용자 관측: 실물 속도는 모르며 바퀴 입력 **30 이하에서는 움직이지 않음**.
전체 fetch 후 로컬/원격 486 refs, 도달 가능한 2664 commits를 `git log --all -G`로 검색했다.
초기 소스 `2df573259de679e651bc1085e34f7da6ea713716`부터 아래 기록이 있다.

- `docs/decision_log.md` 2026-08-29: <=30 실제 정지 관측, 35/.10 s 회전 후 영상 변화 기록.
  이는 이번 재측정이나 정량 속도/토크 자료가 아니다. 낮은 값의 과거 명령 완료는 실제 이동 증거가 아니라고 명시한다.
- `scripts/masterpi_control.py`: -100..100 바퀴 명령, 모터 1/3 부호 반전 후 I2C 0x7A의 31..34 register에 signed byte로 전달.
  현재 안전 CLI는 비영점 35 미만을 거부하고 전후/회전 40, 옆 70 상한이다. 이 경로를 바꾸거나 실물을 구동하지 않는다.
- `scripts/robot_actions.py`: 30 이하에서 움직이지 않아 기본 35라는 설명. `calibration/masterpi/chassis_trials.jsonl`의
  108행은 모두 dx/dy 측정 null이며 실제 속도 데이터가 아니다. 해당 두 핵심 제어/보정 파일의 모든 브랜치 이력은 초기 import뿐이다.
- [PR #385](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/385) `88c5803c` 확인:
  Pi4 legacy I2C 제어 파일과 팔 dry-run·카메라/전압 진단이며 바퀴 속도/토크 측정 없음. raw는 Windows 로컬 경로라 Mac에서 회수하지 않았다.
- `/Users/changmin/projects`의 다른 프로젝트/옛 worktree/이관 backup을 읽기 검색했다. 독립 실물 SDK/유효 속도 로그를 찾지 못했다.
  가상환경·node_modules·가중치·Git object 바이너리는 일반 파일 검색에서 제외했고, Git 이력은 별도로 검색했다.
  최초 import 이전 실물 SDK 원본 및 보드 firmware의 PWM→전압 변환은 **미확인**이다.

### 공식 SDK의 단위와 역산 한계

[공식 MasterPi SDK SHA 11b0cb04](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/masterpi_sdk/common_sdk/common/mecanum.py)의
`set_velocity` 주석은 mm/s지만, 운동학 합성 후 정수값을 `set_motor_duty`에 그대로 전달한다.
[해당 전송 코드](https://github.com/Hiwonder/MasterPi/blob/11b0cb04ada14be7c391e6c865ac705f903a95e7/masterpi_sdk/common_sdk/common/ros_robot_controller_sdk.py)는
motor duty를 float로 패킷에 싣고 속도 피드백이나 mm/s 보정을 하지 않는다. 이 최신 Pi5 UART SDK는 우리 Pi4 I2C와 버전이 다르다.
따라서 확인된 실물 ‘30’은 **±100 눈금의 바퀴 출력 명령**이고, 30 mm/s 실측값이 아니다.
이를 30% PWM/전압으로 선형 해석하는 것은 유력한 모델 가정이며 firmware duty/전압 실측으로 확정한 것은 아니다.

표준 모델은 [MuJoCo 공식 DC motor 문서 §1.1–1.2](https://mujoco.readthedocs.io/en/latest/_static/dcmotor.pdf)의
준정적 전압→토크 식과 dry-friction joint constraint를 따른다.
`tau = tau_full*(u - omega/omega0)`, `|tau_loss| <= tau_c` (정지), 회전 시 반대 방향 dry loss.
이상적인 접지 마찰은 바퀴가 미끄러지지 않도록 하는 힘이며, 구름 출발 저항을 `mu*m*g`로 단정할 수 없다.
바닥 sliding_mu를 올리는 대신 **모터/기어/롤러 저항의 등가값을 바퀴 joint frictionloss**로 둔다.
이는 원인이 모터축 마찰이라고 식별한 것이 아니고 하중 의존성·정지/동마찰 차이는 아직 구분할 수 없다.

30에서 정지, 역사 기록의 35에서 움직임을 같은 조건으로 근사하면 `0.30 <= tau_c/tau_full < 0.35`.
단일 관측으로 `tau_c`, `tau_full`, 바닥 mu를 각각 역산하는 것은 **식별 불가능**하다.
v3은 이 구간의 **하한 .30**을 명시적 후보로 고정한다(결과에 맞춰 고른 값 아님).
v2의 미확인 토크 scale .1176798 Nm를 유지할 때 등가 joint loss는 **.03530394 Nm/바퀴**,
4바퀴 직진의 등가 구동력 하한은 `4*tau_c/.0325 = 4.3451 N`이다. 실제 저항의 확정 측정값이 아니다.
FUJI mesh·관성·.8 접촉 마찰·롤러 수·베어링·카메라·팔·모터 기울기는 v2 그대로다. 소프트웨어 명령 30 clamp는 넣지 않는다.

[일반 TT 공식 자료](https://www.hiwonder.com/products/high-quality-tt-motor)는 150 rpm/1:42,
[encoder TT](https://www.hiwonder.com/products/tt-motor-plastic)는 무부하 150 rpm/토크 1.2 kgf cm를 표기한다.
장착품 동일성·정지 토크 표기는 **미확인**이므로 후자를 stall torque 확정값으로 사용하지 않는다.
65 mm에서 원주 속도 `pi*.065*150/60 = .51051 m/s`는 조건부 무부하 상한 계산이다.
v2 입력20의 .093 m/s는 선형 .2*.51051=.10210보다 낮아 모델 내부로는 설명되지만,
실물은 입력20에서 정지한다는 관측과 충돌하므로 ‘실물에 맞는 속도’가 아니다.
v3의 동일 Coulomb 저항이 주행에도 유지된다는 가정에서는 최대 `.7*.51051=.35736 m/s`; 실물 최대속도 예측으로 확정하지 않는다.

### 유한 검증 순서 (물리 실행 전 고정)

1. v2, v3 각각 무하중/cyan에서 20/30/35/50/100 직진 계단을 **매번 새 초기 상태**로 1.5 s + 정지 1 s 실행.
   known v2 dead-zone 불일치는 비교 기준이며 수정 후보 실패 횟수에 합치지 않는다.
2. v3의 입력20/30은 명령 중 전체 COM XY 이동 <=1 mm를 정지 진단 기준으로 사용한다(눈금 관측의 수치 근사, 실물 정밀도 아님).
   35/50/100은 실제 이동 크기를 그대로 기록. MuJoCo soft friction의 미세 creep와 수치 경고/낙하를 구분한다.
3. v3에서 관측 재현이 되면 입력50으로 옆/회전을 무하중/cyan에 각각 확인한다.
   입력20이 멈췄다고 옆 회전이 해결됐다고 하지 않는다. 옆 이동 회전 기준은 이전 1°를 유지한다.
4. 같은 후보 문제가 두 조건에서 반복되면 중단. 옆 이동이 기준을 만족하면 짝 빔을 통한 정지 로봇 밀림 비교로 진행.
   파지 weld/정답 제어/모델 호출 없이 초기 상태 배치 진단만 허용한다. 원인을 분리하지 못하면 증상 재발로 보고한다.
5. 새 profile `masterpi_drive_friction_v3`, 진단 workflow **3.0.0**. 기본값/과거 번들/실물 드라이버 변경 없음.

## v3 계단 측정 결과: 정지 문턱 재현, 낮은 출력의 지속 주행은 미해결

물리 실행 SHA **`a4964a0a0d34b4b54223c5f3676806b2ac82e6ec`**, MuJoCo 3.12.0.
공개 FUJI v2와 새 v3을 같은 1.5 s 직진 + 1 s 정지로 비교했다. 각 입력은 새 world/초기 상태에서 시작한다.
이전과 같은 HIGH 팔이며 cyan 30 g은 미리 잡힌 하중 진단이다. 아래는 명령 마지막 구간의 평균 직진 속도(m/s)이다.

| 입력 | v2 무하중 | v2 cyan | v3 무하중 | v3 cyan |
|---:|---:|---:|---:|---:|
| 20 | 0.092710 | 0.092274 | 0.000021 | 0.000020 |
| 30 | 0.143674 | 0.142822 | 0.000027 | 0.000027 |
| 35 | 0.169293 | 0.168462 | 0.000027 | 0.000027 |
| 50 | 0.245080 | 0.243558 | 0.092907 | 미실행 |
| 100 | 0.497936 | 0.495559 | 0.346018 | 미실행 |

- **v2 10개 + v3 8개 = 18개** 단일 DEV 진단을 완료했다. 임무/실물 성공률이 아니며 모델 호출은 0이다.
- v3 입력20/30의 명령 중 COM XY 최대 이동은 무하중 **.156/.544 mm**, cyan **.161/.537 mm**였다.
  사전 진단 기준 1 mm 이내여서 ‘30 이하 정지’ 관측을 수치 허용오차 안에서 재현했다. 정확히 0은 아니며 MuJoCo soft friction의 creep가 남는다.
- 입력35는 무하중 **17.923 mm**, cyan **17.913 mm** 출발한 후 명령 중 멎었다. 끝 구간 속도는 둘 다 약 .000027 m/s이다.
  첫 발생 후 빈 상태 50/100과 v2 기준 비교를 기록했고, cyan35에서 같은 증상이 두 번째로 발생한 즉시 추가 물리 실행을 중단했다.
  **같은 증상의 두 번 재발이며 동일한 근본 원인을 분리·확정한 것은 아니다.** 실물의 장시간35 주행 자료도 없으므로 정량 실물 불일치까지 확정하지 않는다.
- 따라서 v3 cyan50/100, 접촉 제거 재측정, 옆 이동/회전, 짝 빔 밀림, v106 재생은 **미실행**이다.
  과거 v2 접촉 제거 결과는 보존하지만 v3 검증으로 승계하지 않는다. v2 옆 회전 2.05°/2.20° 문제가 해결됐다는 근거는 없다.
- v3 무하중 입력50=.09291, 입력100=.34602 m/s. 조건부 이론값 .35736 m/s 근처여도 장착 모터의 실제 최고속도 검증이 아니다.
  기존 v2의 .093 m/s는 입력20 측정값이며 실제 입력20 정지 관측과 맞지 않는다. 실물 최대속도로 해석할 수 없다.
- 새 계단 진단 wall/SIM 범위: v2 무하중 **.856–.876**, cyan **.985–1.012**;
  v3 무하중 **.950–.996**, cyan **1.119–1.136**. 렌더 제외·trace 계측 포함이며 단일 실행으로 성능 차이를 일반화하지 않는다.
  각 raw에 시작/끝 load average와 wall 시간을 보존했다. MuJoCo 경고는 없고 cyan 최저 높이는 .1419 m다.

**채택 판단: NOT_READY.** 관측 하나로 출발 저항과 최대 구동력의 비율만 제한할 수 있다.
설치된 모터·기어·전압/출력 전달·실제 회전수·바퀴/롤러 저항을 독립 측정하기 전에는 토크/바닥 마찰을 고유하게 역산할 수 없다.
새 wheel frictionloss는 등가 저항 후보이며, 무부하 rpm에 이미 포함될 수 있는 모터/기어 내부 손실까지 식별했다는 뜻이 아니다.
결과에 맞춰 .30이나 .1176798 Nm, .8 접촉 마찰, 롤러 형상·관성을 변경하지 않았다. 기본값·기존 번들은 그대로다.

재개 시에는 먼저 35에서 시작 후 멎는 현상을 공개 표준 모델/측정과 대조해 원인을 분리해야 한다.
그 뒤 새 버전의 전체 계단(빈 상태·cyan), 접촉 제거·옆/회전, 짝 빔 밀림 순서로 확인한다.
v106/짝 실행기 도입에는 위의 v101/v102 gain·deadband·시간상수·정지거리·하중·PF 보정과 실제 운반 재검증이 여전히 필요하다.
이번 결과만으로 과거 위치 오차/짝 미끄러짐의 원인을 전부 설명하거나 운반 성공을 승계하지 않는다.

### v3 원본·검증 기록

- [전체 이력/PR385/로컬 코드 조사](v3-history-audit.json), [참고 파일 7개 해시](v3-reference-files.sha256.json).
  공식 SDK·모터·MuJoCo 자료 URL과 확인/미확인 구분은 바로 위 조사 절에 있다.
- [18개 결과](v3-results.json), [raw 66파일 해시](v3-artifacts.sha256.json),
  [관리 기록 12파일 해시](v3-managed-records.sha256.json), [TensorBoard 검증](v3-tensorboard-verification.json).
- raw는 `/Users/changmin/projects/ugrp/outputs/drive-friction-a4964a0a-{v2-empty,v2-cyan,low-empty,low-cyan,high-empty,35-cyan}/`,
  각 대응 `-record/`는 표준 관리 기록이다. 기존 원본/실패 기록/스냅샷은 보존했다. raw 원격 백업은 하지 않았다.
- 모든 배치는 `ugrp_session.py run`에서 공용 잠금 null 확인 후 자기 PID로 acquire/release했다.
  시작한 여섯 세션은 종료했고 마지막 잠금 null을 확인했다. 다른 작업의 프로세스는 변경하지 않았다.
- 변경 구동 시험 `python -m pytest -q tests/test_masterpi_drive_friction_v2.py tests/test_masterpi_drive_friction_v3.py`:
  **5 passed (1.26 s)** 후 물리 소스 커밋/push 및 실행. 기본 v2 접촉/actuator 보존, native dry loss, 명령 단위 검사를 포함한다.
  후처리는 실제 18개 변환·66+12+7파일 해시·378개 원본→event→live API 대조로 확인했다. 이후 물리 코드는 변경하지 않았다.
- TensorBoard snapshot `outputs/tensorboard/1006-drive-friction-v3`: v2 재측정 10 runs + v3 8 runs,
  **378 scalar 일치**. 과거 26/8개 snapshot을 재변환한 것이 아니다. 임무 성공·모델 응답시간·영상은 해당 자료가 없어 등록하지 않는다.
  공용 뷰 파일에는 자기 `masterpi_drive_friction_v3_20261006` 키만 추가했고 타 작업 서버 PID 52016은 유지했다.
- Chrome **강**의 기존 구동 탭에서 저장한 7개 고정 카드 링크를 열었으나 빈 페이지였고, 한 번 새로고침 후에도
  화면 캡처/내용 확인이 불가능했다. **카드 화면·run 선택·HParams 열 표시 검증은 미완료**이며 두 번 확인 뒤 UI 재시도를 중단했다.
  다른 작업 탭/서버를 변경하지 않았다. [대시보드](http://127.0.0.1:6006/?runFilter=%5E1006-drive-friction-v3%2F#timeseries),
  정확한 고정 링크와 데이터 대조 결과는 [검증 JSON](v3-tensorboard-verification.json)의 `url`/`readback`에 있다.

## 이슈 #404 재개: 정지/운동 마찰 분리 v4 (실행 전 조사·계획)

[추적 이슈 #404](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/404)의 사용자 관측은
**입력30 이하 정지, 35 이상 지속 주행**이다. v3의 일정한 dry loss는 출발/운동 저항을 같게 놓았다.
정지 후 재출발을 구분하는 표준 모델을 조사한 뒤 아래 v4 후보를 고정한다. 이전 실패가 오직 이 항목 때문이라고 미리 확정하지 않는다.

| 방법·출처 | 확인 내용과 선택 |
|---|---|
| Karnopp (1985), [DOI](https://doi.org/10.1115/1.3140698) | 작은 속도 구간에서 붙음/미끄러짐을 구분하는 고전법. 서지는 확인, 출판사 원문 접근 실패로 원문 세부식은 **미확인**. 이번 코드의 직접 출처로 삼지 않음 |
| Stribeck, [MuJoCo DC motor 기술 문서 식10](https://mujoco.readthedocs.io/en/latest/_static/dcmotor.pdf) | `g(w)=Tc+(Ts-Tc)*exp(-(w/ws)^2)`로 정지에서 큰 저항, 운동에서 낮은 저항. 이 식을 사용 |
| LuGre (1995), [저자 기관 서지](https://lup.lub.lu.se/search/publication/0c411ed4-a01c-41e2-852c-6586fa9295e7), MuJoCo 기술 문서 §1.4/2.4 | bristle 상태·강성·감쇠로 미끄러지기 전 변형을 포함. 설치된 MuJoCo3.12의 `dcmotor lugre` 구현/공개 시험 확인. 장착품 강성·감쇠가 없어 이번에는 추가 상태를 식별한 척하지 않음. 1995 원문 파일 직접 열람은 미확인 |
| [MuJoCo frictionloss](https://mujoco.readthedocs.io/en/3.12.0/computation/index.html#friction-loss) | 정지에서도 작용하는 native dry-friction constraint지만, 상수 하나로 두면 정지/운동의 다른 크기를 표현하지 못함 |
| [공개 MuJoCo #1366](https://github.com/google-deepmind/mujoco/issues/1366) | 관절 속도로 `frictionloss`를 갱신하는 공개 제안. 이 갱신 경로를 그대로 사용하되 **상류에서 검증된 로봇 구현은 아님**을 명시 |
| [공식 passive/actuator-bias callback](https://mujoco.readthedocs.io/en/3.12.0/APIreference/APIglobals.html#physics-callbacks) | 사용자 힘/바이어스 확장 가능. 전역 callback 수명과 별도 zero-speed regularization을 피하고, 기존 native constraint의 정지 처리 사용 |
| [공식 model 변경 지침](https://mujoco.readthedocs.io/en/3.12.0/programming/simulation.html#model-changes) | 모델별 실수 파라미터 갱신. v4는 자기 world의 wheel DOF만 갱신하며 RK4는 거부하고 기존 implicit integrator 사용 |

공개 MuJoCo 소스는 설치 버전3.12.0 SHA **`13827e9ee56f097f57acf69ae52b078f9839682d`**에 고정했다.
[DC motor 엔진](https://github.com/google-deepmind/mujoco/blob/13827e9ee56f097f57acf69ae52b078f9839682d/src/engine/engine_forward.c),
[공개 derivative 예제](https://github.com/google-deepmind/mujoco/blob/13827e9ee56f097f57acf69ae52b078f9839682d/test/engine/testdata/derivative/dcmotor.xml),
[LuGre/모터 단위 시험](https://github.com/google-deepmind/mujoco/blob/13827e9ee56f097f57acf69ae52b078f9839682d/test/engine/engine_forward_test.cc)을 읽었다.
참고 파일은 primary `outputs/drive-friction-v4-references-20261006/`에 URL·SHA256과 저장했다.

### v4 파라미터의 근거와 한계

[Hiwonder encoder TT 공식 사양](https://www.hiwonder.com/products/tt-motor-plastic)은 6 V, 무부하150 rpm,
무부하 전류 **0.1 A**, 정지 전류 **1.2 A**, torque1.2 kgf cm를 표기한다. 앞서 빠졌던 두 전류를 이번에 확인했다.
장착품 동일성과 torque가 stall rating인지 여부는 여전히 미확인이다.
[Adafruit TT3777 공개 자료](https://www.adafruit.com/product/3777)도 선형 전압 구동·모터 간 편차, 6 V에서250 rpm/0.16 A와
정지1.5 A/0.8 kgf cm를 제공한다. 기어비1:48로 Hiwonder1:42와 다른 제품이어서 이 수치를 MasterPi에 섞지 않는다.
TT의 전체 실측 토크-속도 곡선은 찾지 못했으며 **공식 DC 식으로 사양 끝점을 잇는 근사 곡선**을 사용한다.

- 모터 토크 scale `T0=.1176798 Nm`는 기존 미확인 후보 그대로. 결과를 통과시키기 위해 키우지 않는다.
- 정지 저항 `Ts=.30*T0=.03530394 Nm`: 사용자 출발 문턱의 하한 대표값을 v3에서 유지.
- 운동 저항 `Tc/T0=I0/Is=1/12`, 따라서 **Tc=.00980665 Nm**.
  같은 전압에서 토크가 전류에 비례하고 무부하 손실을 모두 dry loss로 볼 때의 조건부 추론이다.
  점성/브러시/기어 손실 분리·하중 의존성·실물 바닥 마찰계수는 식별하지 못했다.
- Stribeck 전이속도 `ws=.1 rad/s`는 위 공식 derivative 예제의 값 그대로이며 장착품 실측값이 아니다.
  이 값을 실행 전에 고정하고 결과를 보고 변경하지 않는다. 강성·micro damping은 사용하지 않는다.
- native `dcmotor`의 전압 입력은 `u*6 V`, 식은 `T0*(u-w/we)`.
  무부하150 rpm에는 손실이 이미 포함되므로 `we=(150*2*pi/60)/(1-1/12)=17.13596 rad/s`로 전기적 무토크 속도를 계산한다.
  joint 운동 저항을 뺀 뒤 무부하150 rpm으로 돌아오게 해 손실 중복 차감을 피한다.
  컴파일러가 만드는 K/R는 **등가 출력축 곡선**이며 실제 코일 저항/전류를 식별했다는 뜻이 아니다.
- v2 공개 롤러·접촉·마찰 .8·관성·베어링·solver·가시 형상·카메라를 그대로 유지한다.
  차체 힘/속도/위치를 보정하거나 입력30을 소프트웨어에서 잘라 버리지 않는다. 관절 속도는 물리 구성식 안에서만 사용한다.

새 프로필 `masterpi_drive_friction_v4`, 진단 workflow **4.0.0**. 원격 브랜치 전체의 같은 workflow 최댓값3.0.0 확인 후 등록.
기본값/기존 번들/실물 제어 코드는 유지한다. 후보 선택 이유는 모터·기어 강성 없이 관측 가능한 정지/운동 저항을 구분할 수 있어서다.
공개 제안+표준 구성식의 구현이며, 이 조합의 MasterPi 물리 정확도는 아래 진단에서 따로 판단한다.

### 이번 유한 확인 순서

1. 새 초기 상태에서 v4 직진 입력20/30/50/100을 각각1.5 s+정지1 s, 입력35는 **5 s+정지1 s**로 무하중/cyan 비교.
   20/30 명령 중 전체 COM XY 최대 이동 <=1 mm, 35 마지막 .5 s의 모든 기록에서 전진 속도 >.001 m/s이면
   이번 유한 지속 주행 진단 통과로 판정한다. 실물 정밀도/무한 지속 보증이 아니며 35의 과거1.5 s보다 긴 재확인이다.
2. 동일 문제의 두 조건 재발이면 즉시 중단. 통과하면 같은35와1.5 s로 접촉 제거·옆 이동·회전을 두 하중에서 확인한다.
   옆 이동 회전 보류 기준은 이전과 같은1°이고, 접촉 제거는 질량중심과 접촉 힘으로 판단한다.
3. 옆 이동 회전 문제가 사라질 때에만 짝 빔 밀림 비교로 넘어간다. weld/모델 호출 없이 정해진 명령의 DEV 물리 비교다.
4. 모든 실행은 primary 잠금 null 확인 후 자기 PID acquire/release, 관리 세션, 절대 raw 경로.
   새 실패도 보존하고 TensorBoard 수치 대조만 수행한다(사용자 요청으로 브라우저 확인 생략).

## v4 첫 실패와 v5 계획 수정 (추가 실행 전)

v4 물리 SHA `7dce794b527ccbda830ef798eaf6ad0de0c43101`, 무하중20/30만 측정했다.
20은 .156 mm로 정지 기준 안이지만 **30은156.353 mm, 끝 속도 .11098 m/s**로 관측을 위반했다(첫 발생).
trace에서 .02 s에 첫 바퀴 속도 .013 rad/s, 마찰 상한 .03492 Nm로 감소하고 .04 s에는1.23 rad/s와
운동 저항 .00980665 Nm가 나타났다. 이 증거는 경계의 미세 속도가 Stribeck 저항 감소로 확대되는 설명을 지지한다.
이를 마찰값/토크를 높여 보정하지 않는다. 원본·실패 후보는 유지하고 새 구조적 분기를 조사했다.

- [Kirk Roffi 2024 공개 Karnopp/Simulink 예제1.1.0](https://www.mathworks.com/matlabcentral/fileexchange/155462-karnopp-s-model-stick-slip-friction-dynamics-in-simulink?s_tid=FX_rc2_behav):
  저자가 설명한 zero-velocity band, static saturation, 바깥쪽 Stribeck 분기와 시연 설명 확인.
  SLX 다운로드는403/로그인 경로로 원본 블록 파일 직접 확인은 **미확인**이며 실행하지 않았다.
- [Song & Smedley 2010](https://doi.org/10.1115/1.4000321): 출판사 초록에서 고정/가변 step의 Karnopp 비교 확인.
  전체 PDF 접근 실패로 원문의 개선 clutch 식은 **미확인**이며 복사하지 않았다.
- [BME 로봇 마찰 교재 §8.4.2.3](https://www.mogi.bme.hu/TAMOP/robot_applications/math-ch07.html):
  작은 속도 구간을 별도로 취급하는 Karnopp 원리 확인. MuJoCo에 옮길 때는 단일 물체 힘 상쇄/가상 속도 적분을
  **결합된 native joint constraint의 soft 정지 근사**로 대체한다. 원저자 SLX 전체와 동일한 구현이라고 하지 않는다.

v5은 `abs(w)<=DV`에서 native 마찰 상한을 Ts로 유지하고 바깥에서는 기존 Stribeck 식을 사용한다.
**모터/토크·Ts·Tc·ws·접촉·관성 값은 v4와 동일**하다. DV는 이미 고정했던 .1 rad/s 속도 척도를 재사용하는
수치 근사이며 실물 베어링 실측값이 아니다. 통과하도록 값을 탐색/선택한 것이 아니며 band 민감도는 미검증이다.
바퀴 qvel/차체 위치를 강제로0으로 만들지 않고, 제어 명령값으로 분기를 선택하지 않는다.
공개 원리에 대한 MuJoCo 이식 후보이고 미세 creep는 남을 수 있다.

새 profile `masterpi_drive_friction_v5`, workflow5.0.0(원격의 자기4.0.0 뒤). v4 물리 파일은 동결한다.
이전에 적은 전체 비교를 v5 새 초기 상태로 다시 수행한다. **30 정지 실패가 v5에서도 재발하면 전체 두 번째로 세어
즉시 멈춘다**. 35/50/100 지속 주행을 확인한 뒤 접촉 제거·옆/회전, 그 뒤 짝 빔 순서는 유지한다.
v4의 나머지 조건은 미실행으로 남기며 v5 성공 자료로 합산하지 않는다. 두 프로필/실패/후처리의 출처 SHA를 구분한다.

## v4/v5 결과: 입력30 정지 실패 두 번으로 중단

v5 물리 SHA **`7e6e9cf8b6ac11d231942687c5955e1ddeb1da69`**.
v4/v5 각각 무하중20/30 두 개, 총 **4개 DEV 기록**이며 판정 기준과 물리 파라미터를 실행 중 바꾸지 않았다.
MuJoCo3.12.0, 명령1.5 s+정지1 s, 같은 HIGH 팔·Scene·초기 자세다.

| 후보/입력 | 명령 중 COM XY 최대 이동 | 마지막 .5 s 평균 전진 속도 | wall/SIM | 정지 진단 |
|---|---:|---:|---:|---|
| v4 / 20 | .15585 mm | .00002125 m/s | .98772 | 1 mm 이내 |
| v4 / 30 | **156.35295 mm** | **.11097550 m/s** | .97321 | 실패1 |
| v5 / 20 | .15585 mm | .00002125 m/s | .99806 | 1 mm 이내 |
| v5 / 30 | **146.63897 mm** | **.11019512 m/s** | .98112 | 실패2, 중단 |

v5은 .04 s까지 작은 속도에서 정지 상한을 유지했지만, .06 s 기록에 두 바퀴가 .85 rad/s를 넘고
그 마찰 상한이 운동 값으로 떨어졌다. **정지 구간 분기만으로 입력30을 붙들지 못했다.**
두 후보의 같은 출발 문턱 위반을 중단 횟수로 센 것이며, 접촉·하중 반작용·soft constraint·모터 기울기 중
어느 항목이 최초 이탈을 일으켰는지는 분리하지 못했다. 따라서 고전 마찰 구조를 추가했다는 사실과 실물 재현은 구분한다.
DV·Ts·모터 힘을 결과에 맞춰 다시 바꾸지 않았고 추가 물리 실행을 하지 않았다.

**입력35의5초 지속 주행·50/100·cyan·접촉 제거·옆 이동/회전·짝 빔 밀림·v106은 이번 두 후보에서 미실행**이다.
기존 v3의35 정지 문제와 v2의옆 회전2° 문제를 해결한 것으로 보고하지 않는다. v4/v5는 **NOT_READY**이고 기본 채택하지 않는다.
다음 진단에는 출발 문턱의 경계에서 각 바퀴의 전기 토크/접촉 부하/constraint 반력을 분리하는 검증이 필요하다.
장착 모터의 토크/전류 곡선, 실제 구름 저항, numerical band 민감도와 native LuGre의 미확인 강성·감쇠도 남아 있다.
새 구동을 도입하지 않았으므로 v102/v106 보정은 그대로이며, 도입 시 위의 재보정/짝 실제 운반 검증은 여전히 필요하다.

- 관련 **v4 3개 + v5 2개 단위 시험 통과**, v3 호환 시험2개도 앞서 통과. 시간 적분 없는 native DC 곡선·컴파일·접촉 보존·
  정지/운동 분기·초기화 경로 검사다. 물리 정지 진단은 위처럼 실패했으며 단위 시험 통과를 물리 성공으로 보고하지 않는다.
- 각 후보를 시험 후 커밋·push해 고정한 뒤 실행했다. 기본 구동·v1/v2/v3 파일·기존 번들은 변경하지 않았다.
- 시작한 두 세션은 종료, 매번 공용 잠금 null 확인→자기 PID acquire→finally release, 마지막 잠금 null.
  실행 전 여유37.75 GiB 확인. 차체 외력0, MuJoCo 경고0, 모델 호출0, 렌더0. 다른 작업은 변경하지 않았다.
- raw16파일: primary `outputs/drive-friction-{7dce794b,7e6e9cf8}-low-empty/`; 각 `-record/`에 관리 기록4파일.
  [4개 결과](v45-results.json), [raw 해시](v45-artifacts.sha256.json), [관리 해시](v45-managed-records.sha256.json),
  [참고7파일 해시](v45-reference-files.sha256.json), [공식 파라미터 출처](v4-references.json). 원본 삭제/덮어쓰기/원격 raw 백업 없음.
- 새 TensorBoard snapshot `1006-drive-friction-v45`: **4 runs / 96 scalar 원본→event→live API 일치**.
  [검증 기록](v45-tensorboard-verification.json)의 고정 링크는 새4개와 기존 v3 무하중20/30 기준2개를 함께 선택한다.
  과거 snapshot을 중복 변환하지 않았다. 공용 뷰의 자기 키만 추가했고 서버 PID52016은 유지했다.
  **브라우저 화면 확인은 사용자 요청으로 생략**했다. 임무 성공·영상·모델 응답시간 자료는 없다.
  [대시보드](http://127.0.0.1:6006/?runFilter=%5E1006-drive-friction-v45%2F#timeseries).


## #404 재개: 출발 토크 원인 분리 (2026-10-06, 실행 전)

사용자가 재개를 요청했다. v4/v5의 물리 상수는 동결하고 무하중 입력30 각각 한 번만
짧게 재생한다. 첫0.15 s 매 스텝의 모터 generalized torque, joint friction 행,
접촉/다른 제약의 `J^T efc_force`, bias/passive/관성항을 기록한다.
MuJoCo 공식 [힘 식](https://mujoco.readthedocs.io/en/3.12.0/computation/index.html),
[`mj_mulJacTVec`](https://mujoco.readthedocs.io/en/3.12.0/APIreference/APIfunctions.html#mj-muljactvec)를 따른다.
`mj_step` 뒤 힘은 적분 전 상태의 값이므로 속도/시각을 적분 전후로 구분한다.
gear=1 여부, actuator_force와 qfrc_actuator 일치, 실제 friction 행과 설정 상한을 확인한다.
접촉 프레임 힘과 geom 이름도 원본에 저장한다. 평가만 하며 추가 mj_forward/상태 변경 없음.

원인이 특정된 경우 그 원인만 새 후보에 고친다. 분리 불가/최소 수정 실패 시 사용자 승인한
v6 액추에이터 dead-zone으로 전환한다. 같은 원인으로 다시 막히면 추가 튜닝 없이 중단한다.
문턱 30 이하 정지(최대 COM 이동1 mm),35/50/100은5 s 명령 마지막0.5 s 전진속도
모든 표본>0.001 m/s를 진단 기준으로 유지한다. 옆 회전은 기존1° 기준, 짝 빔은 별도
물리 진단으로 비교하며 기존 운반 성공을 승계하지 않는다. 모델 호출/렌더 없음.

### 토크 분리 결과와 최소 수정 사전 기록

진단 SHA `a7e5ad76`에서 v4/v5의 입력30 이동을 각각 그대로 재현했다.
모터 기어는 전부1이고 `actuator_force == qfrc_actuator`; 토크 단위/추가 기어 환산 오류는
발견되지 않았다. Ts는 실제 joint friction 행에 존재한다. v5 접촉 제거/중력0/초기속도0의
첫 스텝 모터는 바퀴당0.03530394 Nm, 실제 마찰은 약-0.03308131 Nm여서0.00222263 Nm가
남았다. 제약항 분해와 관성 균형 잔차는 각각<7e-18 / <5e-17 Nm.
접촉이 없어도0.04575 s에0.1 rad/s 구간을 벗어나므로 접촉이 우회의 필요 원인이 아니다.
접촉 유지에서는0.05125 s에 벗어나고 마찰 상한이0.03530→0.01915 Nm로 내려간다.
즉 **soft friction 제약의 유한 regularization이 만든 속도 누출 → 낮은 운동 마찰로 전환**이
이번 실패의 원인이다. 접촉은 바퀴별 시점/토크를 바꾸지만 위 원인을 없어도 재현했다.
이 설명은 수치 모델 원인이지 실물 Ts의 측정/식별 결과가 아니다.

[MuJoCo 공식 solver/friction](https://mujoco.readthedocs.io/en/3.12.0/modeling.html#friction)은
마찰 행의 r=0, d=solimp[0], `(1-d)*a_unconstrained` 잔류 가속도를 명시한다.
공식 최대 impedance `mjMAXIMP=0.9999`를 **wheel joint의 solimpfriction[0]에만** 적용한
`masterpi_drive_friction_v5_hard_v1`(workflow5.2.0)을 비교한다. 기존0.9→0.9999,
Ts/Tc/DV/모터곡선/접촉/roller/나머지 solimp/solref는 불변임을 단위 시험으로 확인했다.
이는 이상적 정지 마찰의 수치 근사이며 새 물성 측정도, 결과를 보며 숫자를 탐색한 것도 아니다.
입력20/30/35/50/100 각5 s+정지1 s, 무하중부터 하나씩 실행한다.
이 최소 수정이 실패하면 사용자 지정 dead-zone v6로 전환하며 이 solver 수치를 다시 탐색하지 않는다.

### 최소 수정 결과 → v6 dead-zone 후보 (실행 전 고정)

SHA `19621cfc`:5 s 입력20 최대0.0725 mm,30 최대2.0296 mm(1 mm 정지 기준 실패),
35/50 마지막0.5 s 최소 전진속도0.1271/0.2132 m/s. 따라서 soft constraint 누출을 크게
줄여도 정지 관측은 충족하지 못한다. 같은 solver 값을 다시 조정하지 않고 사용자가 지시한
대체 후보로 전환한다. 입력100은 끝에서 x≈5.19 m에 도달해 동쪽 벽/차체 여유와 겹친다.
공간 부족을 시사하는 위치/지도 비교이며 끝 구간의 벽 접촉 힘을 별도로 기록하지 않아 충돌 원인은 추론이다.
이 사례는 5 s 지속 주행 판정에서 제외해 보존한다.
v6에서는 **명시적 --long-lane**으로 setup x만3.0→2.5 m로 옮긴다(벽/장면 물리는 불변).
최대 이론 이동2.55 m와 정지 여유를 확보한다. 기존 짧은 비교는 이전 x3도 유지 가능하다.

`masterpi_drive_friction_v6`, workflow6.0.0: 표준 대칭 piecewise-linear dead-zone
`D(u)=sign(u)*max(abs(u)-b,0)/(1-b)`, `b=0.325`를 결과 확인 전에 고정한다.
사용자의 <=30 정지/35 이상 출발 관측 구간의 중간값이고 측정된 정확한 문턱은 아니다.
기울기는 D(±1)=±1을 보존하는 정규화이다. native wheel motor에 `T0*D(u)`를 준다.
속도 저항 `B=T0/omega0`를 joint damping으로 두어 순 모터 곡선은
`T0*(D(u)-omega/omega0)`이다. 이는 공식 준정적 DC 방정식의 구동원/역기전력 항 분해이다.
|u|<=b이면 **능동 모터 토크0**이며, 이미 회전하거나 외력으로 밀릴 때 수동 속도 저항은 남는다.
모터를 껐을 때 실제 보드가 coast인지 brake인지는 미확인이다. 이 구분을 토크 원본에 명시한다.
150 rpm은 손실 포함 속도 끝점으로 쓰고 기존 Tc/Ts를 동시에 차감하지 않는다.
기존 .1176798 Nm 토크 크기의 정지 정격/장착품 동일성은 여전히 미확인이다.
65 mm 바퀴의 이상적 최고속도는0.5105 m/s이며 기존0.093 m/s와 동일한 사양값이 아니다.

v6는 **물리적 정지 마찰 역산 모델이 아니라 관측 입력-출력 근사**다. 하중 의존 문턱,
방향별 차이·온도·히스테리시스·기어 자체잠금은 재현하지 않는다. 바닥/롤러 마찰과 베어링,
모양/질량/관성/카메라는 v2 그대로다. 바퀴축 native torque만 쓰며 차체 wrench/상태고정 없음.
재보정 전 기존 운반/v106/학생 성공이나 실물 속도를 승계하지 않는다.

근거·확인 범위:

- [Tao & Kokotović1994](https://doi.org/10.1109/9.273339): 제목/서지 확인, IEEE 원문 본문은 접근 미확인.
- [Wang, Su & Hong2004, Automatica Eq1](https://users.encs.concordia.ca/~cysu/publication/Robust%20adaptive%20control%20of%20a%20class%20of%20nonlinear%20systems%20with%20unknown%20dead-zone.pdf): 저자 공개 전문 확인. Tao 계열 정적 모델·양쪽 선형 가지/중간0을 그대로 사용. 적응 역보상 제어기는 구현하지 않음.
- [Fezazi et al.2021 DC motor dead-zone](https://www.iieta.org/journals/jesa/paper/10.18280/jesa.540612): 공개 전문의 모터 손실 식별/보상 사례 확인. 해당400 W 모터 수치는 TT에 전용하지 않음.
- [MathWorks 공식 DC motor](https://www.mathworks.com/help/simscape-electrical/ref/dcmotor.html): `T=Kt/R*(V-Kv*w)`와 정지토크/무부하속도 기반 매핑 확인. v6는 이 affine 식을 능동 source와 수동 damping으로 분리함.
- [2026 dead-zone compensation preprint](https://arxiv.org/html/2607.28142v1): 공개 본문 확인, 모델 없이 보상하는 최근 접근은 검토만 함. 공개 실행 코드/저자 실험 재현은 미확인. 이번처럼 측정이 적은 후보에는 제어/학습을 추가하지 않음.

동일 입력20/30/35/50/100, 무하중·cyan5 s 진단 후 옆/회전/접촉 제거, 짝 빔을 비교한다.
입력 정지/지속 주행이 v6에서도 실패하면 숫자 재조정 없이 중단한다.


### v6 결과·최종 중단 기록

v6 실행 SHA `b438cddb` (정확 SHA는 원본 manifest/아래 JSON), 무하중 HIGH,
명시적 long-lane 초기 x2.5, 각5 s 명령+1 s 정지. 결과를 본 뒤 수치는 변경하지 않았다.

| 입력 | 명령 중 최대 COM 이동 | 마지막0.5 s 평균 전진속도 | 마지막0.5 s 최소 전진속도 | 판정 |
|---:|---:|---:|---:|---|
|20|0.0204 mm|0.00000236 m/s|-0.00007974 m/s|1 mm 이내 정지|
|30|0.0204 mm|0.00000236 m/s|-0.00007974 m/s|1 mm 이내 정지|
|35|17.7825 mm|0.00000988 m/s|0.00000229 m/s|출발 후 멎음, 지속 주행 실패|
|50|609.3673 mm|0.12288000 m/s|0.11066061 m/s|5 s 지속 주행|
|100|2459.4250 mm|0.49792302 m/s|0.49401283 m/s|5 s 지속 주행|

v6 input35에서 매 바퀴 능동 torque는 계속0.00435851 Nm, wheel joint frictionloss는0이다.
0.5 s에는0.01889 m/s였으나2 s부터약0.00002 m/s로 작아졌다. 따라서 이번 멎음은
v4/v5의 wheel joint 정지/운동 분기 전환과 같다고 볼 수 없다. 약한 유효 출력에서
남아 있는 롤러/접촉 저항과의 관계가 의심되지만 원인 항별 분리는 이번 범위에서 미완료이다.
**출발 후 멎음의 재발로 v6도 채택 보류**한다. 앞서 정한 중단 기준에 따라 b·기울기·
롤러마찰을 다시 조정하지 않고 중단했다. 사용자 관측에 맞게 threshold만 넣으면 모든
물리 저항 아래에서35 주행까지 보장된다는 주장은 하지 않는다.

이번 재개에서 cyan 하중, v6 접촉 제거, 옆 이동/회전, 짝 빔 밀림, v106은 **미실행**.
v5 접촉 제거는 원인 분리용 1건뿐이고 v6 검증으로 승계하지 않는다.
기존2° 옆 회전 문제 해결이나 빔 저항 개선을 주장하지 않는다.

- 원인 분리3건(v4 forward30,v5 forward30/no-contact30), hard-v5 계단5건, v6 계단5건: 총13개.
- v6 wall/SIM0.9296–1.0152. 토크 매 스텝 기록이 포함돼 이전 계측 없는 속도와 직접 동등하지 않다.
- 모든 run 경고0, 능동 차체 외력0, 모델 호출0, 렌더0. 무하중은 cyan을 멀리 놓은 조건.
- 이번 신규 단위 시험은4개(토크 투영1, solver 변화 범위1, dead-zone/모터곡선2) 통과.
  단위 시험은 시간 적분 없는 코드 검사이며 물리 목표 미달과 구분한다.
- 각 source는 관련 시험 통과 뒤 커밋/push하고 실행 중 고정했다. 기본/기존 번들/과거 프로필은 불변.
- 각 session은 primary 잠금 null→자기 PID acquire→release, 총4개 session 종료, 마지막 잠금 null.
- raw60파일/관리 기록8파일 해시 검증, 이전 raw/snapshot 보존. 로컬 보관이며 원격 백업 아님.
- TensorBoard `1006-drive-friction-v6`:13 runs/**312 scalars**를 원본→event→실행 중 API로 대조했다.
  브라우저 화면은 사용자 요청으로 생략. 다른 작업의 viewer PID52016/서비스는 변경하지 않았다.
  공용 view에는 자기 새 key만 추가, 기존 v5 input30을 비교 선택하고 중복 변환하지 않았다.
- CI/물리 목표는 별개다. PR #402 **DRAFT/NOT_READY/병합 금지**, 이슈 #404 미완료 유지.

[v6 및 진단 결과](v6-results.json), [출발 토크 분리](v6-torque-diagnosis.json),
[raw 해시](v6-artifacts.sha256.json), [관리 기록 해시](v6-managed-records.sha256.json),
[TensorBoard 수치 대조](v6-tensorboard-verification.json).
Raw:
`/Users/changmin/projects/ugrp/outputs/drive-friction-a7e5ad76-audit-{v4,v5}/`,
`/Users/changmin/projects/ugrp/outputs/drive-friction-19621cfc-hard-empty/`,
`/Users/changmin/projects/ugrp/outputs/drive-friction-b438cddb-v6-empty/`.

다음 근거가 필요한 사항은 장착 TT 토크/출력 곡선, 출력35의 충분한 구동력, 롤러 전환/접촉
저항의 바퀴축 환산이다. 실측 또는 공개 모델 대조 없이 b나 모터 기울기를 바꾸지 않는다.
그 후 cyan/옆·회전/짝 빔을 새 후보에서 검증하고 v102 시간·하중 gain 및 v106 하중 이동,
정지거리/odometry/PF/경로 시간을 다시 보정해야 한다. 현재 어떤 후보도 기본 채택하지 않는다.


## v7 재개 사전 기록: 입력35 멎음 1회 진단

사용자 지시에 따라 v6 입력35, 무하중 HIGH, x2.5 long-lane,5 s 구동+1 s 정지 한 번만
실행한다. 물리상수와 v6는 불변. `--stall-audit`는0.01 s마다 generalized torque 균형,
모터 속도 저항, elliptic 접촉의 normal/tangential 행을 `J^T efc_force`로 분해한다.
바퀴 지지 실린더와 roller의 접촉을 구분한다. Roller bearing은 서로 다른 관절좌표이므로
축 토크에 단순히 더하지 않고 각 hinge 토크/각속도와 소산 전력을 별도로 기록한다.
공식 [MuJoCo 접촉 좌표](https://mujoco.readthedocs.io/en/3.12.0/computation/index.html#contact),
[제약 투영 API](https://mujoco.readthedocs.io/en/3.12.0/APIreference/APIfunctions.html#mj-muljactvec)를 따른다.

이 결과와 [Hiwonder TT](https://www.hiwonder.com/products/tt-motor-plastic)의 I0/Is를
근거로 v7 입력 측 stick/slip 상태 후보를 고정한다. 정지시 출발 문턱32.5는 유지하고,
운동 문턱을35 통과 결과로 조정하지 않는다.20/30 정지,35/50/100 각각5 s 지속을 먼저
측정하고 이어서 옆/회전·짝 빔을 비교한다. **첫 실패에서 중단**하며 추가 조정하지 않는다.
정지 판정은 최대 COM이동1 mm, 지속은 마지막0.5 s 모든 전진속도>0.001 m/s,
옆 이동의 기존 yaw 허용1°를 유지한다. 기본값·기존 번들/프로필·원본은 불변이다.


### v6 멎음 토크 분리 결과와 v7 고정 파라미터

진단 SHA `7d1025f3`, 무하중 입력35 1회는 기존17.7825 mm 이동 후 멎음을 동일 재현했다.
4.5–5.0 s 0.01 s 표본 평균, 단위mN m, 바퀴 순서FL/FR/RL/RR:

| 항 | FL | FR | RL | RR |
|---|---:|---:|---:|---:|
|능동 모터|4.35851|4.35851|4.35851|4.35851|
|모터 속도 저항|0.00185|-0.00373|-0.00045|-0.00142|
|롤러 normal 접촉|-4.76142|-3.86471|-3.81842|-4.99404|
|롤러 tangential 접촉|0.37047|-0.46122|-0.52141|0.61702|
|남은 관성항(순토크)|-0.03059|0.02885|0.01823|-0.01994|

바퀴 joint dry loss0, 지지 실린더 접촉0, 다른 접촉0. 순간 힘 균형 잔차<5.3e-18 Nm,
분해 재합산 잔차<4.3e-20 Nm. Roller bearing의 소산은 작고(별도 원본에 hinge별 저장),
서로 다른 좌표의 토크를 wheel축에 중복 합산하지 않았다. 미세 solver 진동에서 부호가
바뀌는 bearing 순간 전력은 물성으로 식별하지 않는다.
0.5 s에는 속도 저항 약4.2–4.6mNm이었지만 멎은 뒤에는 거의0이다. 멎음을 유지하는 것은
주로 **접촉점 오프셋에 따른 수직 반력 모멘트**다. 이는 바닥의 Coulomb 마찰 계수나 모터
내부 손실과 동일하지 않은 형상/하중 저항이다. v6가 출발 문턱을 운동 중에도 계속 빼서
출력이 작다는 가설과 부합하지만, 실제 MasterPi의 손실 식별 결과는 아니다.

`masterpi_drive_friction_v7` / workflow7.0.0은 요청된 입력 측 상태 모델이다.
Karnopp의 정지/운동 두 분기 개념에 공식 Schmitt relay 전이 규칙을 적용한다:

- 각 바퀴 초기/리셋 상태는정지. abs(u)>0.325일 때 구동 분기로 진입한다.
- 같은 명령 방향에서 abs(u)>bk이면 구동 분기를 유지한다. abs(u)<=bk 또는 낮은 역방향
  명령이면 해제한다. 역방향 abs(u)>0.325는 새 방향으로 다시 진입한다.
- bk=I0/Is=0.1/1.2=1/12=0.0833333. Tc=T0*bk=0.00980665 Nm.
  구동 분기 출력은 T0*(u-sign(u)*bk), 정지 분기 능동 출력은0이다.
- 정격 전압의 속도 끝점150 rpm에 손실을 이중 차감하지 않도록
  B=(T0-Tc)/omega0=0.00686742 Nm s/rad (정확값은 profile JSON)를 수동 속도 저항으로 쓴다.
  입력35의 구동 토크는0.03138128 Nm로 **측정 결과를 보기 전 식에서 정해진다**.
- 멎은 v6의 접촉 반력 약4.4mNm을 bk에 더하거나 빼지 않는다. 이미 물리 접촉에서
  계산되는 외부 저항이며, I0/Is는 모터 내부 무부하 손실의 비율이므로 역할이 다르다.

이는 원문 Karnopp의 실제 속도/총 외력을 사용하는 모델과 동일한 전체 구현이 아니다.
사용자가 지정한 **입력 이력만의 상태로 이식**하였으므로 외부 장애물에 실제로 멎어도
명령이 유지되면 구동 상태를 유지한다. 이 상태를 실제 이동 성공/정지 증거로 쓰지 않는다.
학생 제어기에 qvel/접촉을 전달하지 않는다. 제약 강성 변경/바퀴 상태 강제 고정은 없다.
Hiwonder 전류비를 전부 Coulomb로 간주한 가정, 장착 TT 동일성·정지 토크 정격·PWM
전압 매핑·하중 의존 출발 문턱은 미확인이다. geometry/contact/inertia/FUJI bearing은 불변.

출처 확인:
[Hiwonder TT 공식 사양](https://www.hiwonder.com/products/tt-motor-plastic) 100mA/1.2A/150rpm/6V 직접 확인.
[MuJoCo DC motor](https://mujoco.readthedocs.io/en/latest/_static/dcmotor.pdf) 무부하 손실과 토크-속도 식 확인
(3.12.0 경로는 접근 실패, 이전에 고정한3.12 source와 latest 문서 구분).
[공식 Relay](https://www.mathworks.com/help/simulink/slref/relay.html)의 서로 다른 on/off 문턱과
초기off 규칙 직접 확인. [Roffi 공개 Karnopp1.1.0](https://www.mathworks.com/matlabcentral/fileexchange/155462-karnopp-s-model-stick-slip-friction-dynamics-in-simulink)은
공개 목록/이전 설명 확인, SLX 다운로드/실행 미확인. Karnopp1985 원문은 여전히 미확인.
최근 마찰/보상 연구의 출처와 검토 범위는 위 v4–v6 절에 보존했다. 추가 학습/보상기 없음.

관련 시험: 진단 분해2개 통과, v7 상태·곡선·초기화·중단 기준4개 통과.
중단 기준의 NumPy bool 반환을 발견한 첫 단위 시험1개 실패는 Python bool 반환으로
수정 후4/4 통과했다. 물리상수 변경이나 결과 튜닝은 아니다.
이후 시험 순서는 무하중 계단20/30/35/50/100 → cyan 동일 계단 → 접촉 제거/제자리/
옆 이동/회전(각35,짧은1.5 s) → 짝 빔 비교. **첫 물리/수치 판정 실패 시 더 실행하지 않는다.**


### v7 결과·옆 회전 실패에서 중단

물리 소스 `f837428b52454eae28430a8926d290a4aca27a33`, workflow7.0.0,
기존 FUJI roller/축/접촉/관성은 그대로다. 아래 각 입력은 새 reset에서5 s 명령+1 s 정지,
동일 HIGH·long-lane 초기조건이다. 상태를 이어서 낮춘30은 히스테리시스상 계속 구동할 수
있으며, **아래20/30 정지는 정지 상태에서 해당 입력으로 시작한 시험**이다.

| 하중 | 입력 | 명령 중 최대 COM 이동(mm) | 마지막0.5 s 평균/최소 전진속도(m/s) | 판정 |
|---|---:|---:|---:|---|
|없음|20|0.01909|−0.00000334 / −0.00004567|정지|
|없음|30|0.01909|−0.00000334 / −0.00004567|정지|
|없음|35|684.51056|0.138039 / 0.126996|5 s 지속|
|없음|50|1093.14659|0.220861 / 0.213915|5 s 지속|
|없음|100|2450.36022|0.496537 / 0.492752|5 s 지속|
|cyan|20|0.00996|−0.00000686 / −0.00007482|정지|
|cyan|30|0.00996|−0.00000686 / −0.00007482|정지|
|cyan|35|679.91719|0.137329 / 0.126282|5 s 지속|
|cyan|50|1085.06944|0.218936 / 0.210538|5 s 지속|
|cyan|100|2436.56153|0.492432 / 0.490028|5 s 지속|

이10개는 사전 기준을 통과했고 cyan 낙하가 없었다.35의 멎음은 이번5 s 범위에서 사라졌다.
이는 실물 속도 확인/장시간 주행/방향 정확도 성공이 아니다. 예를 들어 cyan50의 총 yaw는
−1.13102°이며, 직진 계단 기준은 정지/지속 여부만 평가했다.100의 속도0.492–0.497 m/s는
150 rpm·65 mm로 계산한0.5105 m/s 끝점과 같은 크기이나, 장착 모터·실물 속도는 미확인이다.

그다음 무하중 짧은 시험(각1.5 s 명령+1 s 정지, 초기 x3):

| 조건 | 측정 | 판정 |
|---|---|---|
|접촉 제거·중력0,35|명령 중 전체 로봇 COM 최대0.112 μm, 바퀴 접촉0, 차체 능동 외력0|10 μm 기준 통과|
|제자리·명령0|COM 최대0.00812 mm|1 mm 기준 통과|
|옆 이동35|평균 옆 속도0.124627 m/s, 최소0.119829 m/s; 총 yaw **−2.487829°**|기존1° 기준 **실패**|

접촉 제거 시 base 원점은 내부 바퀴/차체 반작용으로13.03 mm 움직였으나 전체 COM은
보존됐다. base 원점 변화를 바닥 없는 병진 추진으로 해석하지 않는다. 접촉 주행에서도
차체 `xfrc_applied`는0이고 wheel native actuator만 구동한다.
옆 이동은 실제로 진행되지만 원치 않는 회전이 남는다. 평균 접촉 미끄러짐0.015164 m/s,
최종 base 이동(x,y)=(0.005295,0.187342)m. 옆 회전 원인은 이번 결과만으로 식별하지 않는다.
**첫 판정 실패에서 batch가 중단됐으며 이후 turn·cyan 옆/회전·짝 빔 비교는 미실행**이다.
마찰/토크/기울기/roller 수치를 더 바꾸거나 재실행하지 않았다. 이슈 #404 미완료,
PR #402 **DRAFT / NOT_READY / 병합 금지**를 유지한다.

검증·보존:

- 이번 재개에서 v6 원인 진단1개+v7 계단10개+짧은3개=14개. v7 기준은12개 통과/1개 실패.
  `MEASURED_DEV`는 측정 완료이며 옆 이동의 acceptance 실패를 성공으로 바꾸지 않는다.
- 변경 모듈 단위 시험은 토크 분해2개와 v7 상태/곡선/초기화/중단 기준4개, 총6개 통과.
  실행 전 통과·커밋·push한 소스를 고정했다. 물리 실패 뒤 코드/상수는 변경하지 않았다.
- v7 접촉 유지 wall/SIM1.0723–1.2789, 접촉 제거0.7055; v6 상세 계측1.0190.
  비교는 고정 DEV 조건이며 하중/계측량/호스트 loadavg를 원본에 보존했다.
- 경고0·모델 호출0·렌더0. 네 managed session 정상 종료, 각각 잠금 null 확인 후
  자기 PID acquire/release, 마지막 잠금 null. 다른 작업의 프로세스/서버/PR/worktree 변경 없음.
- raw64파일과 관리8파일 해시 확인. 원본/이전 snapshot 보존, raw는 로컬 보관이며 원격 백업 아님.
  후처리 첫 실행에서 활성 제약 종류가 표본마다 달라 누락 키 오류가 났다. 없는 제약 행을0으로
  집계하는 방식으로 수정해 완료했으며, 물리 실행/원본/판정 값은 바꾸지 않았다.
- TensorBoard `1006-drive-friction-v7`:14 runs/**336 scalars** 원본→event→실행 중 API 일치.
  [대시보드](http://127.0.0.1:6006/#timeseries), 공용 view 새 key
  `masterpi_drive_friction_v7_20261006`에 이전 v6의35도 비교 선택. 기존 키/순서는 보존했다.
  브라우저 화면은 사용자 요청으로 생략. 기존 PID52016 서버를 재시작/수정하지 않았다.
- 새 RGB bundle ID 없음. v1–v6/기본 dynamics/exact_speedups/기존 실행 번들은 재개 전 SHA와
  동일하다. 최종 기록 커밋은 물리 실행 SHA와 구분한다.

[14개 결과·판정](v7-results.json), [v6 멎음 토크 분해](v7-stall-diagnosis.json),
[raw 해시](v7-artifacts.sha256.json), [관리 기록 해시](v7-managed-records.sha256.json),
[TensorBoard 수치 대조](v7-tensorboard-verification.json).
Raw는 `/Users/changmin/projects/ugrp/outputs/drive-friction-7d1025f3-v6-stall/` 및
`/Users/changmin/projects/ugrp/outputs/drive-friction-f837428b-v7-{empty,cyan,motion}/`.
후처리 소스는 `/Users/changmin/projects/ugrp/outputs/drive-friction-v7-audit-20261006/postprocess-source.py`,
SHA256 `0b05a718c8177d00a254483f88a2c793d171a79b40ee0d866d40e348c4151dc0`로 로컬 보존했다.

v102의 시간/하중 gain, v106의 하중 이동·자세별 속도, 짝 빔을 통한 수동 밀림/파지 유지,
정지거리·odometry/PF·경로 시간은 새 구동에서 다시 측정해야 한다. 이번 입력 관측 재현만으로
기존 성공/오차 결과를 승계하거나 기본 프로필을 바꾸지 않는다. 다음 변경에는 옆 yaw 원인의
별도 근거가 필요하며, 이번 작업에서는 실패 뒤 추가 원인 실험/수정 없이 중단한다.


## 메인 결정 이후: v7 DEV 후보 채택·짝 빔 비교 1건

2026-10-06 메인 세션/사용자 결정([#404 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/404#issuecomment-6013834255)):
옆 이동1°는 실물 근거가 없는 임시 보류 기준이었다. v7의−2.487829°를 알려진 특성으로
남기고 **DEV 후보로 채택**한다. 기존 wrench의−2.05°는 메인 세션이 제시한 비교 기록이며,
이번 짝 빔 실행에서 다시 측정한 단독 옆 이동 값은 아니다. 이전1° 판정/원본은 당시 기록으로
보존하고 소급해서 통과로 바꾸지 않는다. 기본값·기존 번들 승격·실물 검증 완료와 구분한다.

실제 로봇 운용은 자기 카메라로 방향을 관측하고 보정하는 경로를 전제로 한다. 이번 고정 명령
진단에는 카메라 방향 보정을 넣지 않으며, 그러한 보정이 이 편향을 충분히 줄인다는 실물 증거는
아직 없다. **실물 옆 이동 거리·yaw(무하중/하중, 양 방향, 입력/시간 기록)와 자기 카메라 보정 전후
오차를 측정**하는 TODO를 #404에 유지한다. GT yaw로 보정하거나 새1° 기준을 만들지 않는다.

짝 빔 비교 사전 설계(workflow7.1.0, `--pair-beam` 명시적 옵션):

- 기존 표준 `FinalV3Scene`, `zone_wide_two_doors_final_v3`, seed1601, 같은300g/600mm
  `long_beam`, `cargo_noslip_v1`, weld OFF. 등록 지도/카메라/팔/빔/접촉은 불변.
- 기존 [v92 고정 HIGH 준비](../../harness/zone_final_pair_loaded_schedule.py)의
  `high_held`32 s 순서와 [staging 어댑터](../../harness/zone_pair_highpose_staging.py)를 재사용한다.
  빔 위치 `[3.55,-.85,0]`와 정적 station_offset도 기존 측정 설계 그대로. CameraRobotPort의
 2000 pulse/s 보간으로 실제 팔 액추에이터가 파지·상승하며, 준비 후 자세 강제 배치/보정은 없다.
- 준비 후 **r1만 옆 방향 바퀴 입력35를0.5 s**, r2는명령0; 이어서 둘 다1 s 정지.
  짝 사이 비동기 명령의 고정 perturbation으로 수동 밀림을 드러내는 DEV 조건이다.
  같은 명령·시간 비교이며 같은 속도/힘 비교는 아니다. 진단값에 맞춘 보정/재시도 없음.
- 순서wrench→v7 각1회, 매회 새 reset. 동일 설계 해시·시작 상태·준비 과정 차이도 보존한다.
  조건 사이 잠금을 바로 놓고 다음 시작 직전에 status null 확인 후 자기 PID로 다시 잡는다.
- 비교: 빔 중심(x,y,z) 이동·yaw, 두 로봇의 world-y 진행량과 그 차이, 빔 좌표계에서 각
  finger midpoint 변화(집게 안 미끄러짐), 손가락 반력·빔 최저 높이·기울기. 준비 종료를 기준으로
  계산한다. 전체 준비 trace도 보존하고 준비 중 실패를 구동 비교로 대신하지 않는다.
- abort만 GT를 사용한다. 기존 teacher의 finger>=0.5N/양쪽·이탈0.3 s, lift clear12mm,
  낙하 최저 높이5mm 또는 상승 뒤 바닥 접촉을 따른다. 기존 cargo probe의 로봇10° 제한을
  사용하고 빔에도 같은10° DEV 안전 제한을 적용한다(실물 한계가 아님). 실제 실패면 그 시점에
  멈추고 남은 조건/재실행은 하지 않는다. yaw 편향·진행 차이는 수치 그대로 기록한다.

방법 출처: [MuJoCo 공식 접촉 힘 API](https://mujoco.readthedocs.io/en/3.12.0/APIreference/APIfunctions.html#mj-contactforce),
[접촉 좌표](https://mujoco.readthedocs.io/en/3.12.0/computation/index.html#contact) 직접 확인.
힘은 공식 `mj_contactForce`의 normal을 합산한다. 상대 slip/기울기/바닥 기준은
기존 [cargo probe](../../scripts/probe_zone_cargo.py),
[team teacher](../../scripts/zone_team_teacher.py)의 정의를 따른다. 새로운 마찰 법칙이나 물성을
만들지 않으며 공개 모델·모터 자료의 확인/미확인 범위는 위 v2–v7 조사에 유지한다.

실행 전 관련 단위 시험: `test_probe_drive_pair_beam.py`3개와 `test_masterpi_drive_friction_v7.py`4개, 총7개 통과(0.93s). 시간 적분 실험이 아닌 중단/측정/관리 경로 및 기존 v7 회귀 검사다.

### 짝 빔 비교 결과: 각1회 완료, 실제 물리 실패 없음

물리 실행 SHA `c05130d9bef2f42fe93e755cbd0c83e375570b2e`, 두 조건의 설계 해시
`fb91f1d3549d87d53a364f26970f3a608a70b4d5e8cb89fdc98341351f690243` 동일.
실제 staging 명령 파일·drive 명령 파일도 각각 바이트 동일하다. 로봇 각1.1kg, 빔0.3kg,
dt0.00025s 동일. 아래는 HIGH 준비 종료 대비0.5s 비대칭 구동+1s 정지 후 변화다.

| 항목 | 기존 wrench | v7 |
|---|---:|---:|
|빔 옆 이동(world-y)|23.7061mm|30.5293mm|
|빔 앞뒤 이동(world-x)|0.3456mm|3.1826mm|
|빔 yaw 변화|−2.60215°|−3.35178°|
|명령을 받은 r1 진행량(world-y)|45.1761mm|58.2693mm|
|명령0인 r2 진행량(world-y)|2.6118mm|3.7194mm|
|두 로봇 진행량 차이(r1−r2)|42.5642mm|54.5498mm|
|집게 안 최대 상대 미끄러짐(r1/r2)|0.05334/0.04780mm|0.06375/0.05940mm|
|구동·정지 중 빔 최저 높이|114.8112mm|114.5192mm|
|구동·정지 중 손가락 최소 반력|5.2501N|5.2374N|
|준비 포함 로봇 최대 기울기|2.26786°|2.90945°|
|준비 포함 빔 최대 기울기|0.11106°|0.10538°|
|준비 포함 wall/SIM|1.03636|1.74467|

위 wall/SIM은 **조건별 n=1이며 호스트 loadavg가 다른 측정**이다.
부하를 통제한 속도 비교나 일반적인 성능 차이의 근거로 해석하지 않는다.

낙하·10° 기울기 초과·집게 이탈·수치 경고는 두 조건 모두0, 활성weld0.
각33.5 SIM초(준비32초+구동/정지1.5초), 실측 wall34.7181/58.4466초.
wall에는 world 생성/준비/계측도 포함되므로 앞선 단독 주행의 적분 구간 wall/SIM과 직접
동등하지 않다. 고정된 평가 명령48개/조건, 모델 호출0·렌더0. 두 managed session을
차례로 끝내고 각 잠금을 바로 release, 마지막 null 확인. 추가 물리/반복/튜닝 없음.

v7에서도 빔을 통해 명령0인 상대 로봇이 밀린다. 이번 **같은 명령**에서는 빔 이동·회전·
진행 차이가 오히려 더 컸으므로 저항 증가나 밀림 개선으로 해석하지 않는다. 모터 입력의
토크/속도 매핑이 달라 r1 자체의 진행도 커졌다. 동일 속도/힘에서의 저항 비교나 통계·
실물 검증이 아니며, 자기 카메라로 방향/동기화를 보정하는 실제 운반 제어기도 실행하지 않았다.

동일 reset·동일 준비 명령이어도 물리가 달라 HIGH 도달 상태는 완전히 같지 않다.
wrench 준비 뒤 빔 중심x=3.550029m, v7=3.543333m로 약6.70mm 차이, yaw는각0.10064°/
0.10344°였다. 강제로 맞추지 않았고 전체 준비 trace를 보존했다. 비교 변화량은 각자의
준비 완료 시점 기준이며, 이 초기 차이도 한계로 포함한다. 집게 slip은 빔 좌표에서의
finger midpoint 변화로, 빔 전체 이동이나 바퀴-바닥 접촉 미끄러짐과 다른 지표다.

참고로 단독 옆 회전의 기존−2.047428° 원본도 해시를 다시 확인했다
([첫 비교 결과](results.json)의 `baseline-left`, 원본SHA256
`524e2ba7e8d3fcd0ee57c9fc2769a58918b67a8901ef106565325dfbe528db1d`).
당시 소스f323a7b7은 입력20/1.5초, v7의−2.487829°는 입력35/1.5초이므로 **같은 입력의
개선율 비교는 아니다**. 이번 빔 A/B만 입력35와 명령 시간이 같고, 단독 옆 이동 재실행은 없다.

[짝 빔 결과·원본 위치](pair-v7-results.json), [raw14파일/관리4파일 해시](pair-v7-artifacts.sha256.json),
[TensorBoard 대조](pair-v7-tensorboard-verification.json). raw는
`/Users/changmin/projects/ugrp/outputs/drive-friction-c05130d9-pair-{legacy,v7}/`.
TensorBoard 새 snapshot `1006-drive-friction-pair`:2 runs/**48 scalars** 원본→event→실행 중
API 일치. 공용 view에는 자기 `masterpi_drive_pair_v7_20261006` key만 추가했다.
처음 API 확인은 서버의 새 snapshot 재읽기 전404였고, 재읽기 후 일치했다(중복 변환 없음).
브라우저 확인은 사용자 승인대로 생략, 기존 PID52016 서버/다른 key/이전 snapshot은 보존.
기본값·기존 번들·v7 물성은 불변, PR #402 DRAFT·미병합. v7은 DEV 후보이고 실물 측정 TODO,
S2·v102/v106 및 카메라 보정이 포함된 새 운반 검증은 다음 범위다.

후처리 소스 로컬 보존: `/Users/changmin/projects/ugrp/outputs/drive-friction-pair-audit-20261006/postprocess-source.py`, SHA256 `62a804e167af88c7eb14d05d656e4a897f075f6d6afc834a8dcb56fcaecff331`.

## PR #402 독립 리뷰 반영 (2026-10-09)

- main `5c56807c69a5ec2ba64ace42b489e5a382433e1a`을 merge하고 workflow 계획 시험의 누락된 v7 인자를 #407과 동일하게 추가했다.
- 로컬 `tests/test_simulation_workflow_manager.py`: **18 passed**. 시뮬레이션·모델 호출 0, 물리 소스·카메라 변경 없음. 원본 실행 결과 재검증은 하지 않았다.
- 참고: [Git merge 공식 절차](https://git-scm.com/docs/git-merge)의 `--no-commit`으로 시험 전 커밋을 막고, [pytest 파일 지정 실행](https://docs.pytest.org/en/stable/how-to/usage.html)을 사용했다. 새 알고리즘/논문 이식 없이 기존 #407 시험 입력과 저장된 loadavg를 근거로 수정했다.
