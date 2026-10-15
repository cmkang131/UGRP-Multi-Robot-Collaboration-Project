# selfmap2 — 자기 RGB frontier 실주행 준비 (2026-10-15)

PR #506 · `claude/map-selfmap` · 시작 SHA `b136297833b8c2241505e31c4e025f0e6310f12a`.
실행 소스는 push 후 생성한 `20261015-selfmap-<SHA8>.json`의 전체 SHA에 고정한다.
**PREPARED_NOT_EXECUTED**: Mac 물리·렌더 0, 원격 접속·실행 0, 모델 호출 0.
지도 완성이나 실제 frontier 도착을 검증한 결과가 아니다.

## 변경과 재사용

- `self_map_executor=frontier_drive_v1`은 기본 off다. `--execute`도 있어야 실행하며
  Mac은 실행 전 거부한다. 공통 `sim_cli workflow run self-map-diagnostic`에 등록했다.
- 자기 RGB와 자기 발행 명령, 기존 고정 카메라 보정만 제어기에 전달한다.
  top RGB는 캡처하지 않는다. backend의 장면/시작 좌표/정답 지도/측정 상태는
  실행기·지도·위치 추정기에 전달하지 않는다. 단일 활성 로봇 r3, 다른 로봇은 기존 장면에서 정지한다.
- 시작에는 기존 SEARCH 팔 자세에서 겹치는 팬 관측(1500→1750→2000→1750→1500→
  1250→1000→1250→1500, 각 1초)을 하고 기존 `CycleNavigator`의 제자리 sweep을 수행한다.
  카메라 장착·FOV·외관·바닥 무늬를 바꾸지 않는다. 장면의 선택 벽 테이프는 off다.
- `own_map_navigation.frontier_candidates`와 A*를 재사용한다. 선택 목표를 유지하며
  새 관측 지도에서 경로를 다시 계산하고, 기존 `public_navigation.follower.follow_twist`와
  `active_wall_mapping.pulse_command`로 보정된 전진/회전 명령을 발행한다.
  도착하면 다시 팬/회전 관측한다. 동일 목표 3회 제한과 10초 무진척/30초 목표 시한은
  재관측으로 돌아가며, 후보 0을 완료로 취급하지 않는다.
- E2E18 #461의 `e2e_exploration.py`와 `active_frontier_cycle.py`의 목표 유지·도착·
  재관측 흐름을 확인했다. 회전 진척은 자기 발행 명령 yaw로 세고, 충돌 검사는 지도 추정
  yaw로 변환한다. `sim/grasp_act_solo_teacher.py` 및 `grasp_act_solo_lookaround.py`도
  `origin/claude/act-solo-teacher` SHA `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`에서
  확인했다. 그쪽의 고정 pan·settle 흐름은 참고했으며, 교사/정적 지도 localizer는 가져오지 않았다.
- 현재 차체 footprint는 **계획용 사본**에만 추가하며 관측 점유·커버리지에는 포함하지 않는다.
  관측 장애물은 지우지 않는다. 전진은 unknown을 막는 실제 footprint 검사,
  제자리 관측은 기존 `UnknownCostmap` 정책을 사용한다. 후자는 미관측 공간의 무충돌을
  증명하지 않으며 기존 backend 안전 감독자가 벽 접촉/기울기 등을 실패로 종료한다.
- 종료는 내부 `self_map_complete` 또는 유한 SIM 상한이다. 완료는 시각 pose, 경계 frontier 0,
  지도 안정화, 8방향 관측, 벽 관측, B 구역 재확인을 모두 요구한다.
  이는 운용 선언이며 정답 IoU·커버리지·위치 오차와 구분한다. 실제 완주/성공은 미측정이다.

## 큰 pose 보정과 점유 재삽입

`pose_rebuild=refit_history_v1`은 별도 기본 off이며 새 실행기에서만 켠다.
1차의 영구 보류 대신, 삽입한 자기 관측의 특징점·descriptor·body 좌표 ray를 보존한다.
큰 보정 뒤 현재 자기 landmark bank에 과거 각 관측을 다시 SE(2) 정합하고,
새 빈 격자에 ray를 재삽입한 뒤 **모든 과거 관측이 유효할 때만** 교체한다.
첫 bootstrap의 자체 원점은 고정한다. 실패한 과거 정합은 `unresolved`에 남고,
기존 격자/경로는 보류하며 완료를 막는다. 시각 관측이 있으면 최소 5초 간격으로 재시도한다.
재구성 뒤 이전 구역 확인과 sweep/stability를 초기화해 다시 관측한다.

래스터 전체를 통째로 이동하지 않으며, 이 구현은 PR #496 landmark bank에 대한 재정합이다.
전역 pose graph/landmark 동시 최적화나 반복 무늬의 오정합 해결을 구현한 것은 아니다.
아직 연속 RGB에서 재구성 처리 시간·정확도·완료 가능성을 측정하지 않았다.

## 저장 RGB 직접 확인과 pose 불가 사유

원본/해시·픽셀 마스크·특징/대응점 수는 [rgb-inspection.json](rgb-inspection.json).
s61001-r2의 자기 RGB 6장을 직접 열었다: frame 1/54/158/287/1090/1297,
SIM 1.3/11.9/32.7/58.5/219.1/260.5초. 전체 영상을 본 것은 아니며,
이 사이에는 RGB가 없는 구간이 있다. 다른 로봇과의 물리 실패 관계를 진단한 작업도 아니다.

넓은 단색 바닥/벽, 반복 체크 바닥, 전경의 밝은 빔을 보았다. 마스크는 색 화물과 자기 몸을
제외하며, 확인 표본에서는 유효 픽셀 약 17만–19만개에 ORB 특징 38–85개 수준이다.
특징이 존재해도 자기 landmark bank와 일치하지 않으면 pose는 갱신되지 않는다.
동결 PR #496 추정기와 1차 옵션으로 같은 126장을 재생해 분기 원인을 세었다:

| 126장 분기 | n |
|---|---:|
| 대응점 부족 `insufficient_matches` | 99 |
| 강체 정합 실패 `no_rigid_consensus` | 10 |
| 시각 pose 갱신 | 14 |
| bootstrap | 3 (초기 안정화 대기로 빈 관측 2 포함) |

따라서 `visual_pose_unavailable` 111회는 99+10+2다. 초기 연속 **5 Hz** 구간에서도
1.9초는 특징 48개 중 bank 대응 6개, 2.5초는 56개 중 7개여서 최소 8개 기준에 못 미친다.
4.3초는 대응 9개가 있어도 강체 정합을 통과하지 않는다. 후반의 선택 표본 간 대응은
58.5→219.1초 1개, 219.1→260.5초 0개였다(이 값은 표본끼리의 비교이며 bank 대응과 다름).
누락 RGB만으로 모든 실패를 설명할 수 없고, 단색·반복 무늬와 시야 변화가 대응을 어렵게 한다는
관찰과 일치한다. **연속 10 Hz 원본은 아직 없으므로 10 Hz에서도 같은 비율이라고 주장하지 않는다.**
추정기 임계값을 완화하지 않았다.

이 사유 진단은 코드 커밋 전의 계측이며 v1의 저장 행동을 고정한 재생이다.
새 주행 결과로 합산하지 않는다. 생성 자료는
`/Users/changmin/projects/ugrp/outputs/selfmap2-offline-rgb-inspection/`에 보관했고,
큰 JSON/JSONL은 zstd 해제 바이트 SHA-256 확인 후 압축했다. 원래 RGB·명령은 변경하지 않았다.

## 기록·평가·GCP 대기열

- 캡처/저장은 **640×480, 10 Hz 전량**이다. 제어도 저장 JPEG를 OpenCV로 읽어
  오프라인 재생과 같은 픽셀을 사용한다. 매 frame의 SHA와 원장 0.1초 간격/개수를 확인한다.
  명령은 기존 보정의 0.2초 pulse/tail 간격을 유지한다. RGB를 5 Hz로 줄이지 않는다.
- 프레임·명령·trace·지도·재구성 receipt·sweep/목표 이벤트·첫 30초 진척/속도·부분 실패를
  기록한다. 큰 JSON/JSONL과 해시 목록은 무손실 압축 확인 후 보관한다. 환경에는 기존
  SciPy/OpenCV/Pillow/MuJoCo와 pursuit의 matplotlib, `c++`, `zstd`가 필요하다.
  GCP 설치 여부는 미확인이고 실행 전 점검 대상이다. 새 환경은 만들지 않았다.
- 정답은 루프 종료 뒤 별도 평가 함수에서만 읽는다. 기존 고정 전체 지도 분모의 IoU/커버리지와
  시작 pose 고정 정렬의 자기 위치/yaw RMSE·실제 대응 n/N을 저장한다.
  내부 완료와 외부 지도 품질을 별개로 보고한다.
- 프로젝트 `ugrp-act-train-1014`, 호스트 `gcp1`, 예정 머신 `n4-highcpu-64`, 동시 **1**.
  시드 **93510/93511/93512**, 각각 **30/180/180 SIM초**, 실행당 wall 상한 1,800초.
  로컬 소스/관련 원격 브랜치 ref/기존 대기열에서 미사용을 확인하며,
  원격 실행 이력에 대한 최종 중복 검사는 coordinator의 제출 전 조건이다.
- 저장 상한은 301/1801/1801장. 기존 JPEG 126장의 중앙값 16,355.5 bytes,
  최댓값 17,237 bytes를 확인했다. 새 장면 크기는 미측정이므로 **128 KiB/장 + 텍스트/압축
  임시 공간 128 MiB**로 추정한다: 실행당 **165.625/353.125/353.125 MiB**,
  예약 **192/384/384 MiB**, 합계 **960 MiB**. GCP 영속 디스크에 RGB 전체를 보존하고
  Mac은 fetch-lite·필요한 개별 RGB만 받는다. GCP 전체 여유·타 작업 예약 쓰기는 미조회다.
- `coordinator_approval.approved=false`, `ready=false`, `runs_enabled=false`, 각 run `enabled=false`,
  자동 gate/학습 승격 false. 첫 30초의 속도·시각 pose·frontier/정지 구간을 확인한 뒤에도
  나머지 실행은 별도 coordinator 승인 전까지 꺼져 있다. 어떤 원격 명령도 실행하지 않았다.
- GCP 예산 정지, 8시간 STOP, 유휴 20분, 다른 호스트로 자동 이전 금지를 유지한다.
  원인 확인 시 자기 결함 실행 정지·원본 보존, 실행 후 결과 해시 회수·VM 정지 확인은
  coordinator의 실제 실행 단계에 남는다. 준비 기록을 완료 실험으로 승격하지 않는다.

오프라인 재평가는 새 raw의 `robots/r3/frames.jsonl[.zst]`와 commands를 사용한다:

```sh
python -m scripts.offline_self_map replay --raw RAW --images RAW --robot r3 \
  --output NEW_REPLAY --motion-model s2_pulse_v122_rotL_v1 \
  --self-map-integration natural_floor_frontier_v1 \
  --pose-rebuild refit_history_v1 --navigation-support current_footprint_v1
```

## 검증

관련 파일만 실행: `test_self_map_integration.py`, `test_self_map_executor.py`,
`test_offline_self_map.py`. 최종 **29 passed (18.44 s)**.
[selfmap2-summary.json](selfmap2-summary.json)에 최종 결과와 파일 해시를
기록한다. 기본 off, peer/top 차단, 과거 관측별 재정합/원자적 실패, footprint 증거 분리,
팬→기존 sweep→A*·실제 명령 생성→도착 재관측, cap/완료/오류 시 hold·close,
10 Hz 전량 원장, 압축 복원, 관리 workflow를 검증한다. 모두 오프라인 fixture이며 물리 결과가 아니다.
개발 중 도착 fixture를 실제 frontier와 같은 격자 중심으로 고쳤다(임의 셀 경계 목표 때문에
정상 회전/pose 보정 보류가 발생했던 1실패). native 물리/렌더 검사는 실행하지 않았다.

## 참고 자료

- [1차 참고 자료](../../docs/self_map_integration.md#참고-자료)의 occupancy/frontier 출처와
  열람 범위를 유지한다.
- [slam_toolbox `updateMap`·`setTransformFromPoses`](https://github.com/SteveMacenski/slam_toolbox/blob/ros2/src/slam_toolbox_common.cpp):
  2026-10-15 소스 열람. 수정 pose/지도와 odom 좌표계를 분리하고 점유 지도를 다시 생성하는
  구조를 확인했다. 이번 코드는 저장 RGB ray의 개별 pose 재정합에 적용했으며 ROS/LiDAR
  SLAM이나 해당 최적화기를 포팅했다고 주장하지 않는다.
- [Nav2 regulated pure pursuit](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp):
  2026-10-15 `shouldRotateToPath`, `rotateToHeading`, projected collision 검사 소스 열람.
  저장소의 기존 PythonRobotics pursuit/보정 pulse/footprint 검사 구현을 재사용한다.
- 내부 재사용: `harness/active_frontier_cycle.py`, `harness/e2e_exploration.py`,
  `harness/own_map_navigation.py`, `harness/public_navigation/follower.py`,
  `harness/active_wall_mapping.py`, `sim/own_map_closed_loop.py`, `sim/lazy_camera.py`.
