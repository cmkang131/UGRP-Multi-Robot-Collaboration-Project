# 2026-09-28 MasterPi 외관 모델 v3 (공식 자료 기반 재모델링)

- 작업: Claude, 브랜치 `claude/masterpi-visual-v3`, 기준 `origin/main` `b8583f17`
- 성격: 모델 버전 추가. 실험 결과가 아니고 성공률도 없다. 물리 step 0회, 시뮬레이션 실행 0회, 모델 호출 0회다. 정지 자세는 `mj_forward`로만 계산했고 오프스크린 정지 렌더만 만들었다.
- 새 파일:
  - `sim/masterpi_geometry_v3.py`: 치수, 출처 등급, 실측 목록
  - `sim/masterpi_visual_v3.py`: `build_v3_xml(profile=...)`
  - `scripts/render_masterpi_visual_v3.py`: 비교 렌더 스크립트
  - `tests/test_masterpi_visual_v3.py`
- v2는 바이트 그대로다. `sim/masterpi_dynamics_v2.py`, `sim/masterpi_geometry.py`, `sim/masterpi_scene*.xml`을 고치지 않았다. 새 모듈은 등록 실행 번들의 source closure 밖에 있다(테스트로 확인).
- 전환하지 않았다. 최종 연구 장면, 기본값, 번들은 계속 v2를 쓴다. 전환은 사용자 검토 뒤 별도 PR로 한다.

## 왜 이상해 보였나 (공식 치수도와 v2의 차이)

| 항목 | v2 | 공식 자료 | 등급 |
|---|---|---|---|
| 하부 차체 | 축 사이 120 mm 판 | 앞판이 185 mm 전장선에 닿는 짙은 회색 역U 차체, 높이 16.8–50.0 mm | public_measured |
| 팔 받침 | 팔 yaw 축이 차축 중앙(x=0), 전자부 덮개 앞끝과 겹침 | 짙은 회색 **팔 받침 상자**(x 9.8–76.9 mm, 폭 54.9, 높이 50–80.2)가 ID6 서보를 품고, yaw 축은 **x=48.2 mm** | public_measured |
| 초음파 | 차체 앞 낮은 위치. 중심 x 78, 높이 54 mm, 간격 34, 지름 20 | 팔 받침 상자 **앞면**에 달린 모듈. 송수신면 x **88.0**, 중심 높이 **61.7**, 간격 26.7, 지름 16, 수평 | public_measured / official |
| 팔 서보 | ID4·ID3에도 LD-1501MG 외형을 쓰고, 축 방향 폭 20 mm로 회전돼 있음 | ID6·ID5는 LD-1501MG(40×20×40.5), ID4·ID3·ID1은 LFD-01M(32.5×12×29.85). ID5는 축 방향 폭이 40.5 | official + public_measured |
| 팔 링크 | 평평한 막대 | 주황 개방형 측판(폭 19.8, 좌우 외폭 41.4, 삼각 구멍, 둥근 관절 끝) | public_measured / photo_estimate |
| 전자부 | Pi를 옆으로 눕힘, 은색 상자 | Pi 긴 변이 전후 방향이고 포트가 뒤쪽. 짙은 회색 덮개(윗판 101 mm, 옆판이 아래로 벌어짐, 삼각 창), 구리 M4×50 기둥 | official / public_measured |
| 바퀴 | 노란 캡슐 8개 | 회색 허브(살 10개)와 주황 롤러 9개, 폭 30 mm | official / photo_estimate |

## 두 프로필

| 프로필 | 물리 | 용도 |
|---|---|---|
| `appearance_only` | **v2와 같다.** body, joint, inertial, actuator, camera, site와 모든 충돌 geom의 값이 같다. `mj_forward` xpos와 카메라 자세가 비트 단위로 같다(테스트). v2 시각 전용 geom만 v3 시각 geom으로 바꾼다. | 물리를 건드리지 않는 외관 교체. 팔은 v2 위치(x=0)라서 덮개 앞끝과 겹쳐 보인다. 이것이 v2 기구학 위치의 문제를 그대로 드러낸다. |
| `drawing_layout_proposal` | **제안(opt-in).** `arm_base` x를 0 → 0.0482 m로 옮기고, 충돌 proxy 4개를 치수도에 맞추고, `arm_box_collision`을 추가한다. 질량, 관성, 링크 길이, 바퀴, 보정값은 그대로다. | 실물처럼 보이는 모델. 물리 변경이므로 사용자가 검토하고 실측한 뒤에만 채택한다. |

`build_v3_xml()`은 profile을 반드시 이름으로 받는다(기본값 없음).

## 초음파 장착 (PR #248에 전달)

`SONAR_MOUNT_V3`(robot body 기준, 원점은 차축 중앙이고 z는 차축 높이):
- 송수신면 중심: x = **0.0880 m**, y = 0, z = 0.0617 − 0.0325 = **0.0292 m**. 바닥 기준 높이는 **61.7 mm**다.
- 축은 +x(수평, pitch 0°). 두 송수신기 간격은 26.7 mm, 지름은 16 mm다.
- 사이트 이름은 `v3_ultrasonic_site`(zaxis = 전방).
- v2 대비: 높이 +7.7 mm, 앞 +4.0 mm(면 기준; v2 cylinder 중심은 78 mm, 면은 84 mm), 간격 −7.3 mm.
- 등급: public_measured(공식 치수도를 인쇄된 치수로 축척). 실측이 아니다. 축척 오차는 ±1 %(±1–2 mm)다.

## 출처 표

| ID | 자료 | URL | 라이선스 | 쓴 것 |
|---|---|---|---|---|
| S1 | Hiwonder MasterPi 제품 페이지, 사양표와 "Dimensional Diagram" | https://www.hiwonder.com/products/masterpi · 치수도 https://cdn.shopify.com/s/files/1/0084/2799/5187/files/masterpi_01173667-020d-4baa-8ec8-6ff4a45b6220.jpg?v=1716200111 | 저작권 Hiwonder, 재배포 허가 없음. 수치만 인용했고 이미지는 커밋하지 않았다 | 185×162×343 mm, 1.1 kg, 4DOF+집게, LD-1501MG·LFD-01M. 치수도 라벨 65/30/101/215 mm와 모든 public_measured 값(축척 2.357 px/mm) |
| S2 | 같은 페이지의 서보·카메라 사양 이미지 | 위 페이지(LD-1501MG `1501.jpg`, LFD-01M `LFD-01M.jpg`, HD 카메라 `7e29db14...jpg`) | 위와 같음 | LD-1501MG 40×20×40.5(귀 포함 54.4), LFD-01M 32.5×12×29.85, HBVCAM-V2101 30×25×25 mm |
| S3 | MasterPi 공식 문서 1장(구성품·조립 1–6단계) | https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html | 문서에 "Copyright … Shenzhen Hiwonder … no reproduction" 명시. 링크와 관찰 결과만 기록했다 | 팔 받침 상자에 초음파가 달린 조립 상태, 역U 차체, 배터리 케이스 위치(차체 안), Pi 방향(포트 뒤쪽), 덮개와 기둥 |
| S4 | Hiwonder 발광 초음파 모듈 제품 페이지와 치수도 | https://www.hiwonder.com/products/glowing-ultrasonic-sensor · 치수도 `02_8838c641-...jpg` | 저작권 Hiwonder | 모듈 45.6×28.5 mm, 측정각 15°(반각인지 전체각인지는 적혀 있지 않음), 2–400 cm, 40 kHz, I2C 0x77. 송수신기 간격 26.7 mm는 치수도 축척값 |
| S5 | Hiwonder MasterPi SDK `ArmIK/InverseKinematics.py`(공개 재배포본) | https://github.com/SquirrelRobotics/MasterPi/blob/98b85647eab1614f3fcce28aba959c679cfc72eb/ArmIK/InverseKinematics.py | 저장소에 라이선스 없음. 코드는 재사용하지 않고 상수만 대조했다 | l2 = 6.50, l3 = 6.20, l4 = 10.00 cm(= `harness/real_geometry.py`) |
| S6 | 저장소 기존 값 | `sim/masterpi_camera_profile.py`, `harness/real_geometry.py` | 저장소 | robot_cam 자세(REAL 적합)와 링크 길이는 그대로 뒀다 |

조사했지만 쓸 수 없었던 것:
- MasterPi 공식·공개 URDF, STEP, STL은 찾지 못했다. GitHub `gh search`(masterpi/urdf/stl/xacro, hiwonder urdf)에서 결과가 없었다. GrabCAD도 확인하지 못했다.
- 그래서 메시 자산 재사용은 0이다. 모든 형상은 MuJoCo 기본 도형과, 코드가 만드는 볼록 프리즘 메시로 만들었다.

## 값별 출처 등급

전체 목록은 `sim/masterpi_geometry_v3.py`의 `SOURCES`에 있다(이름 → 값, 등급, 근거). 등급은 다음 다섯 가지다.
- official: 인쇄된 수치
- public_measured: 공식 치수도를 그 도면의 인쇄 치수로 축척한 값
- photo_estimate: 공식 사진이나 렌더에서 눈으로 읽은 값
- controller: SDK나 제어기 값
- real_fit: ugrp1 REAL 적합값

주요 값:

| 값 | v3 | 등급 |
|---|---|---|
| 초음파 면 x / 중심 높이 / 간격 | 88.0 / 61.7 / 26.7 mm | public_measured |
| 초음파 모듈 크기, 측정각 | 45.6×28.5 mm, 15° | official |
| yaw 축 x | 48.2 mm | public_measured |
| 어깨 축 높이 | 127.7 mm(v2 물리 125.5는 유지) | public_measured |
| 상완 / 전완 / 손목→집게 끝 | 57.7 / 62.4 / 94.0 mm(물리는 SDK 65 / 62 / 100 유지) | public_measured vs controller |
| 덮개 윗면 | 101 mm | official |
| 차체 높이 범위 / 전장 | 16.8–50.0 / 185 mm | public_measured |
| 바퀴 지름 / 폭 | 65 / 30 mm(v2 물리 폭 31 유지) | official |
| 윤거 / 축거 | 129.9 / 118.8 mm(v2 131 / 120 유지) | public_measured |
| 롤러 수, 모따기, 색 | 9, 10 mm, RGBA | photo_estimate |
| robot_cam 자세 | 바꾸지 않음(67 mm 앞, 13.6 mm 위, −7.95°) | real_fit |

## 물리 쪽 제안 (이 PR에서는 적용하지 않음, `drawing_layout_proposal`로만 확인 가능)

1. **팔 yaw 축을 +48.2 mm 앞으로 옮긴다.**
   - 근거: 치수도 옆면에서 yaw 혼 767.75 px와 어깨 허브 765 px가 차축 중앙 880 px에서 떨어진 거리.
   - v2에서는 팔 받침이 전자부 덮개와 같은 자리에 있다. 그래서 `appearance_only` 렌더에서 팔이 덮개 앞끝과 겹친다.
   - 이 이동은 다음에 영향을 준다: 몸체 기준 도달 거리, 짝 정렬, 초음파와 집게의 상대 위치, 카메라의 세계 자세.
2. **차체와 덮개 충돌 proxy를 치수도에 맞춘다.**
   - 하부: 116 → 181 mm 길이, 높이 17–47 → 16.8–50 mm.
   - 앞판: x 60 → 91 mm.
   - 덮개: x −60…+4 → −85.6…+3.5 mm, 폭 ±47.2 mm.
   - 팔 받침 상자 proxy를 추가한다.
3. **링크 길이 차이.**
   - 치수도 상완은 57.7 mm이고, SDK와 v2는 65 mm다. 치수도는 인쇄 치수 5개와 1 % 안에서 맞는다(343 mm 전고 = 127.7 + 57.7 + 62.4 + 94.0 = 341.8).
   - v2로 팔을 곧게 세우면 360 mm가 된다.
   - 실측 전에는 바꾸지 않는다. REAL 제어기와 FK가 65를 쓰기 때문이다.
4. **집게 끝 위치.**
   - 치수도 94 mm, SDK 100 mm, v2 접촉 box 중심 100(86–114) mm로 서로 다르다.
   - v3 시각 패드는 물리 접촉 box 중심(100 mm)에 둔다. 영상과 접촉이 어긋나지 않게 하려는 것이다.
5. **카메라.**
   - 기본 제공 카메라(HBVCAM)의 치수도 위치는 렌즈가 손목축에서 53 mm 앞, 공구축에서 28 mm 위다.
   - ugrp1 적합값은 67 / 13.6 mm, −7.95°다. 적합값대로면 기본 브래킷에서는 카메라 기판이 집게 윗판과 겹친다.
   - v3는 AGENTS.md에 따라 적합 자세를 유지한다. 렌즈 시각 geom은 robot_cam 위치에 정확히 둔다(테스트). ugrp1 실측이 필요하다.

## 영향 목록 (전환 PR에서 처리)

- **렌더로 학습한 시각 모델**
  - 손목 카메라 영상: `appearance_only`에서는 자기 로봇이 화면에 거의 안 들어온다. `look_down` 자세 비교는 바닥과 그림자 모양만 다르다(`compare_robot_cam.png`).
  - 하지만 동료 로봇, TOP 카메라, 관찰자 영상에서는 외형이 크게 바뀐다. 동료 판별과 짝 인식 모델, 태그 없는 위치 추정(VIS 계열), 화물 인식 v1–v3 가운데 로봇 외형이 들어간 학습 데이터는 다시 확인해야 한다.
  - `drawing_layout_proposal`은 팔 위치가 바뀌므로 손목 영상 자체도 달라진다.
- **pair align과 짝 운반(#240, #246)**
  - 동료 외형(주황 대신 짙은 회색 차체, 받침 상자, 덮개), 몸체와 팔의 상대 위치, 충돌 proxy(제안 프로필)가 달라진다.
  - `peer_visibility_band` 같은 시각 단서는 v2 몸체 높이를 가정하므로 다시 확인해야 한다.
- **초음파(#248)**: 장착값 x 78 → 88 mm, 높이 54 → 61.7 mm, 간격 34 → 26.7 mm. 막대와 상대 로봇 가시성 표도 다시 계산해야 한다.
- **실행 번들**
  - 이 PR은 번들을 새로 쓰지 않는다. v2 파일이 바뀌지 않았으므로 `rgb-standard-dispatch-v63`을 비롯한 기존 번들의 해시도 그대로다.
  - 전환 PR은 `sim/multi_masterpi_production.py`의 `build_v2_xml` 호출을 바꾼다. 이 파일은 `REQUIRED_SOURCE_PATHS`에 들어 있으므로 새 RUNNABLE_ID를 등록해야 하고, 그때 main과 열린 PR의 최댓값을 확인해야 한다.
  - `harness/rgb_communication_scenarios.py`의 고정 파일 목록(770–772행)과 source-pinning 테스트도 다시 검토해야 한다.
- **해시를 고정한 테스트**
  - `tests/test_zone_study_source_pinning.py`, `tests/test_rgb_execution_bundle.py`는 이 PR에서 통과했다.
  - `tests/test_masterpi_physical_geometry.py`, `tests/test_masterpi_visual_geometry.py`는 v2 이름과 크기를 단정한다. 전환할 때 v3 버전을 따로 만들어야 한다. v2 테스트는 v2 모델에 그대로 둔다.

## 사용자 실측 목록 (ugrp1)

`sim/masterpi_geometry_v3.py`의 `MEASURE_ON_ROBOT`과 같다.

1. 초음파 송수신기 중심 높이(바닥에서): 치수도 61.7 / v2 54 mm
2. 차축 중앙에서 초음파 송수신면까지 앞 거리: 88.0 / 84 mm
3. 초음파 기울기(수평 = 0°)
4. 차축 중앙에서 팔 yaw(ID6) 축까지 앞 거리: 48.2 / 0 mm
5. 어깨(ID5) 축 높이: 127.7 / 125.5 mm
6. ID5–ID4 축 거리: 57.7 / 65 mm
7. ID4–ID3 축 거리: 62.4 / 62 mm
8. ID3 축에서 닫힌 집게 끝까지: 94 / 100 mm
9. 렌즈 중심 위치(ID3 축에서 공구축 방향, 공구축 위): 53/28(기본 카메라) vs 67/13.6(적합) mm
10. ugrp1 카메라 모델(HBVCAM 기본인지, icspring인지)
11. 윤거 129.9 / 131, 축거 118.8 / 120, 바퀴 폭 30 / 31 mm
12. 차체 앞판–뒤판 길이: 185 / 120 mm
13. ID5 서보 라벨(LD-1501MG 또는 LDX-218)

## 출력 (로컬 원본, 커밋하지 않음)

위치: `/Users/changmin/projects/ugrp/outputs/masterpi-visual-v3/`. `manifest.json`의 sha256은 `85c0826c…9c03`이다.

주요 비교 이미지:

| 파일 | 내용 | sha256 |
|---|---|---|
| `compare_product_view.png` | v2 / v3 제안 / v3 appearance_only / 공식 렌더(3/4 시점) | `f85b0b7c…0899` |
| `compare_side_ortho.png` | 옆 정사영, 팔 세움, 1 cm 눈금자, 초음파 표시, 공식 치수도 | `8bc67352…1852` |
| `compare_front_ortho.png` | 앞 정사영과 공식 치수도 | `301d70da…f349` |
| `compare_robot_cam.png` | 손목 카메라가 보는 장면(`look_down` 자세) | `ea6c555e…2682` |
| `v3_drawing_layout_side.png` | 옆 정사영 단독(눈금자, 초음파 점과 축) | `c08ef7ec…2597` |

- 참조 이미지(Hiwonder 원본 사본)는 `reference/`에 두었고, 해시는 `reference/SHA256SUMS`에 있다. 저작권 때문에 커밋하지 않는다.
- 로컬 보관일 뿐이며 원격 백업이 아니다.

## 검증

- 신규 `tests/test_masterpi_visual_v3.py` 12개: v2 물리 동일성(카운트, body, joint, actuator, camera, 충돌 geom, FK 비트 동일), 추가 geom이 모두 질량 0이고 비충돌인지, 초음파 사이트 값, 제안 프로필 변경 범위, 다중 로봇 prefix 복제 컴파일, 출처 등급, 치수도 축척, 번들 closure 밖 위치.
- 함께 돌린 기존 테스트: `tests/test_rgb_execution_bundle.py`, `tests/test_zone_study_source_pinning.py`.
- 위 테스트는 `mj_step`을 막는 가드 아래에서 돌렸다. 결과는 PR 본문에 있다.
- `test_masterpi_physical_geometry.py`, `test_masterpi_visual_geometry.py`는 `MasterPiDynamicsV2()` 생성 때 물리 step을 쓴다. 배터리 사용 중이라는 지시에 따라 실행하지 않았다(가드에 막힌 것 외의 실패는 없었다). v2 파일을 바꾸지 않았으므로 결과는 바뀌지 않아야 한다. 전원이 연결되면 확인해야 한다.
- TensorBoard: 지표가 있는 실험·학습·평가 결과가 아니어서 새 스냅샷을 만들지 않았다.
