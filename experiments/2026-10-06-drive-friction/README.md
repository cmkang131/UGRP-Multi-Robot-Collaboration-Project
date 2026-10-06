# MasterPi 구동 검토와 접촉 구동 후보 (2026-10-06)

**v1 NOT_READY — DEV 구조 후보, 실물 보정 전.** 접촉 추진은 확인했지만 옆 이동 때 회전 편향이
무하중·cyan 하중에서 반복돼 두 번 막히면 중단하라는 요청에 따라 추가 물리 실행을 중단했다.
기본값·기존 번들·v102/v106·카메라·팔/물체 접촉은 변경하지 않는다.
별도 `masterpi_drive_friction_v1`과 `masterpi-drive-friction-probe` 1.0.0을 명시적으로 선택한다.
새 RGB 번들 번호는 예약하지 않았다. draft PR만 만들며 병합하지 않는다.

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
