# MasterPi 구동 검토와 접촉 구동 후보 (2026-10-06)

**DEV 구조 후보, 실물 보정 전.** 기본값·기존 번들·v102/v106·카메라·팔/물체 접촉은 변경하지 않는다.
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

v3의 기존 9개 capsule 롤러를 각각 자유 hinge에 붙이고 동일한 위치/크기/외관으로 접촉을 활성화한다.
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

실행/결과/실패·wall/SIM·TensorBoard 기록은 아래에 추가한다. 아직 실물·짝 빔·v106 완주 검증은 없다.

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
