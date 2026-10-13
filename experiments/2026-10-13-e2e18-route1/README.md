# 자기 지도 경로 단계 후보 v381 (기본 off, DRAFT)

작업: `claude/e2e18-route1`, 부모 `codex/e2e18`의 `f4d79b7772d9e7f115424241f741b44a4ab60094`.
목표는 매핑 저장 상태에서 경로 생성만 비교하는 것이다. 새 전체 E2E, Mac 물리/렌더, Azure 직접 조작, 병합은 하지 않는다.

## 원본 진단

`r79-diagnostics.json`과 `r79-failures.json`은 이미 회수된 16개 실행의 r1 ownmap 원장만 읽은 결과다. 원본 경로와 압축 파일 SHA-256을 각각 보존했다. r79는 공급자 402의 HOST_ERROR 배치이므로 제어 성능 분모로 쓰지 않는다. v375와 v377은 같은 관측을 반복한 사례가 있어 독립 증거로 합산하지 않는다.

- v375 seed61009: 경로 계산 86회 중 실패 85회, 실패 85/85에서 allow_unknown 이후에도 목표의 **전체 운반 외곽**이 막혔다. 마지막 실패 277.2 SIM초에는 목표 외곽에 occupied 34셀, 시작 외곽에 occupied 2셀이 있었다. 여유 폭은 이미 2cm까지 완화됐다. unknown을 더 허용하거나 σ만 낮추어 해결할 실패가 아니다.
- v375 seed61006: 실패 16회 중 시작 외곽 막힘 10/16, 양 끝점은 열렸지만 연결 경로 없음 6/16.
- v375 seed61007: 실패 7/7에서 두 끝점 막힘. 마지막 성공 기록의 B 외곽은 기존 관측 범위 밖 267셀로, allow_unknown 경로 생성은 지도 관측 완료가 아니었다.
- 원장 16/16 열람, 실제 route diagnostics가 있는 실행 14/16. 자료 미포함 2개를 성공이나 경로 실패로 바꾸지 않는다.
- B 경계 오인, 실제 좌표 등록 오차, 충돌·통과 가능성은 자기 지도 원장만으로 확정할 수 없다. r80 대표 4개 회수 뒤 진단을 추가했다(아래). 전체16개 코호트로 확대하지 않는다.

## 후보

`--route-recovery frontier_v1`만 v375 위에 합성해 **v381 / 7.274.0**으로 등록한다. off는 기존 경로 그대로다. 기존 v375 등의 등록 파일은 수정하지 않는다.

1. 기존 `footprint_clearance`의 고정 yaw 직사각형 C-space와 A*를 재사용한다. 1.25×0.40m 운반 외곽과 셀 크기 보정은 줄이지 않는다. 운반 중 yaw 회전은 계획하지 않는다.
2. 엄격한 `.02+3σ` → σ 기여 절반 → `.02m` 순서로 계산한다. 뒤 두 단계는 DEV 전용이며 정식 모드에는 적용하지 않는다. 수치와 `would_stop_sigma`를 기록한다. Nav2의 일반 권고가 물리 외곽 축소라는 뜻이 아니다.
3. 시작점은 이동/삭제하지 않는다. 목표가 막히면 12.5cm 안의 연결된 유효 셀 중 가장 가까운 셀을 고른다. 원래 막힌 목표를 경로 끝에 다시 붙이지 않는다. B의 최종 RGB 재관측·내려놓기 판정은 계속 필요하고, 재관측 endpoint에는 이 허용오차를 적용하지 않는다.
4. 관측 free만으로 경로를 내보낸다. 같은 외곽의 `allow_unknown`은 부족한 관측 위치를 찾는 가설에만 쓴다. 미지 구간을 자유 공간으로 기록하거나 그 경로를 실행 경로로 승인하지 않는다. 기존 DEV native 경로보다 생성률이 낮아질 수 있으므로 단순 생성률과 관측 완료율을 모두 보고한다.
5. 가설 경로의 운반 외곽에 겹친 미지 셀을 최대 256개 추려 기존 explore_lite frontier를 정보이득/이동거리로 재정렬한다. 관측 벽의 시야 가림을 검사한다. 기존 도달 가능성 검사·목표 유지·무진전 blacklist를 재사용한다. 초점은 own odom에 보관하고 현재 map TF로 변환하며 15 SIM초 뒤 만료한다. 실제 카메라 FOV 기반 정보량의 정확한 예측이나 탐색 완주 증거는 아니다.

## 단계 재생 및 남은 입력

기존 `harness/pair_stage_probe.py`를 먼저 확인했다. 그 도구는 align/grasp/carry/setdown용 교사 물리 배치와 별도 상태 형식을 쓰므로 현재 GoalRoute 매핑 상태를 복원할 수 없다. 이 변경은 그 도구의 `LABELS`와 canonical digest를 재사용하는 **순수 경로 계산 단계 어댑터**다. 전체 물리 checkpoint 복원을 구현했다고 주장하지 않는다.

실행 호스트에서 `harness.e2e_route_stage_probe.capture(goal, beam, now=..., profiles=...)`로 자기 grid odds/관측 출처/support, TF, 자기 pose/covariance, B·beam RGB 출처, 기존 옵션을 캡처한다. `beam`은 `rgb, pose_own_m` 두 필드만 전달한다. JSON을 저장하고 64KiB 초과면 zstd 압축/해제 SHA 검증한다. 평가 입력은 별도 파일로 둔다.

manifest `cases`에는 `case_id, seed, subset, snapshot, sha256`을 넣는다. `snapshot`은 JSON 또는 JSON.zst 파일이다. 선택적 `evaluation, evaluation_sha256`은 별도 평가 파일 경로/해시다. 동일 snapshot을 off/on에 재생하고 실제 `route_to_B`와 route compiler까지 호출한다.

```sh
PYTHONPATH=. python -m scripts.run_e2e_route_stage_probe \
  --manifest <paired-snapshot-manifest.json> --output <new-output-directory>
```

표준 관리에는 `e2e18-route-stage-v1 / 0.1.0`으로 등록했다. 산출물은 모든 실패/HOST_ERROR를 포함한 results와 summary JSON이다. 분모는 **저장 상태 수**이며 seed 수와 혼동하지 않는다. 같은 시점 파일의 SHA를 양쪽에 기록한다. 저장 시점 기준 경로 준비 SIM 시각의 중앙/최대는 온라인 후보 생성 지연이 아니다. 순수 재생은 SIM을 진행시키지 않으므로 온라인 생성 SIM 시간은 null이다.

평가 파일 schema `ugrp.route_eval_rectangles.v1`: `input_sha256`(snapshot canonical digest), `own_to_world`(평가 전용 변환), `bounds_xyxy`, `obstacles_xyxy`. 두 제어기 계산 뒤에만 읽고, 각 경로 선분의 1.25×0.40m swept polygon 전체와 직사각형 장애물을 SAT로 교차 검사한다. 접촉/마찰/실제 통과는 별도의 물리 단계 결과가 필요하며 항상 미확인으로 남긴다.

r80 실제 저장 지도·평가 파일 0/8 상태 회수, 온라인 단계 시험 0/16 실행(4 seeds × 2 checkpoint × 2 arms 예정). 기존 경량 ownmap-final에는 odds/floor_frames/wall_frames가 없어 저장 지도로 대체할 수 없다. 감독자에게 PR #461로 필요한 파일과 물리 checkpoint/전체 제어 상태 복원 어댑터 존재 여부를 요청했다. 원본 로그를 복원 가능한 상태라고 부르지 않는다.

## 검증

관련 기존 2파일 41/41, 신규 파일 최종 17/17 통과. 변경 중 총 56개 검사의 1개 실패는 synthetic 좁은 통로 바깥의 미지 우회로가 존재함을 무시한 기대값 오류였고, 외곽을 축소하지 않은 채 진단을 복수 원인으로 보완했다. 전체 회귀 대신 관련 파일만 실행했다. 실제 seed 짝비교·물리 통과·온라인 시간 개선은 미확인이다.

## 참고 자료

2026-10-13 원문 확인:
- [NavFn 설정](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/configuring_navfn/): `allow_unknown`, 목표 허용오차. 이미 존재하는 native unknown 경로와 새 관측 완료 경로를 구분하는 근거.
- [Smac 2D 설정](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/smac/smac_2d/configuring_smac_2d/) 및 [공식 구현](https://api.nav2.org/nav2-rolling/html/smac__planner__2d__impl_8hpp_source.html): 0.125m tolerance와 allow_unknown, 제한된 계획 시간. 이번 구현은 Nav2 패키지 이식이 아니라 기존 grid/A*에 같은 목표 허용오차 개념을 적용한다.
- [Nav2 튜닝 가이드](https://docs.nav2.org/jazzy/configuration_and_development/tuning_guide/): 실제 비원형 footprint와 SE2 검사. 물리 외곽을 줄이는 완화는 채택하지 않았다. 전 방향 회전이 필요하면 별도 SE2 플래너가 필요하다.
- [explore_lite ROS2 공개 구현](https://github.com/robo-friends/m-explore-ros2/blob/main/explore/src/frontier_search.cpp): free–unknown 경계, 거리/정보이득 비용. 기존 탐색기 위에 경로와 관련된 미지 셀 이득을 추가했다.
- [Kim 등, 2024-12, Enhancing Exploration Efficiency using Uncertainty-Aware Information Prediction](https://arxiv.org/abs/2412.12825): 초록 확인. 예측 지도 불확실성을 탐색 정보량에 반영하는 접근이며, 이 작업에서는 학습된 미관측 지도 예측을 제어에 넣지 않는다. 논문 전체 재현·수치 검증은 미확인.
- [2025, A Hierarchical Approach for Autonomous Robotic Exploration with Frontier Search and DRL-based Path Planner](https://www.sciencedirect.com/science/article/pii/S2405896325016337): 검색 초록만 확인, 본문 403으로 **미확인**. 구현 근거로 쓰지 않았다.

## 커밋 뒤 저장 파일 단계 재생

실행 소스 `926b84c3c2661610c97b3eb1569d313a01bdbee7`. synthetic 8개 상태를 JSON.zst로 저장하고 압축 해제 바이트를 확인한 뒤 실제 CLI로 off/on 16회 재생했다. `synthetic-summary.json`에 raw 위치·SHA를 연결했다.

| 지표 | 기준 off | 후보 frontier_v1 |
|---|---:|---:|
| 경로 생성 / 전체 상태 | 5/8 | 3/8 |
| 관측 완료 경로 / 전체 상태 | 2/8 | 3/8 |
| 평가 지도의 충돌 없음 / 생성된 경로 | 3/5 | 3/3 |
| 핵심: 막힌 목표 상태의 경로 생성 | 0/2 | 1/2 |
| 핵심: 막힌 목표 생성 경로의 충돌 없음 | 0/0 | 1/1 |

총 충돌 없는 경로는 양쪽 3/8로 같으며, 후보가 실제 seed에서 더 빨라졌다는 증거는 없다. 후보는 미지 가설 경로를 실행 경로로 세지 않는다. 모든 synthetic 저장 시각은 1.3 SIM초(중앙/최대 모두 1.3)로 고정한 fixture라서 속도 비교에는 의미가 없다. 온라인 생성 SIM 시간과 실제 통과는 미측정이다. 표준 `sim_cli workflow plan`의 등록·입력 해시 해석도 확인했다.

## 뒤이어 회수된 r80 대표 원본 4개

`r80-diagnostics.json`: v375/s61008·61009, v379/s61006·61009. ownmap 원장·final·transport trace·result의 선택 해시 16/16을 원본 artifacts 매니페스트와 대조했다. RGB/wire 원본은 이 회수본에서 제외됐다. 네 실행의 ownmap-final에는 grid odds/floor_frames/wall_frames가 없고 물리 integration checkpoint도 없어 **복원 가능한 저장 지도 0/8 상태**는 그대로다.
- e2e18-v375-s61008-r80: 경로 이벤트 [(38.4, False)], 경로 계산 실패 0/1, 그중 목표 외곽 막힘 0/0.
- e2e18-v375-s61009-r80: 경로 이벤트 [(277.8, False)], 경로 계산 실패 85/86, 그중 목표 외곽 막힘 85/85.
- e2e18-v379-s61006-r80: 경로 이벤트 [(292.2, False)], 경로 계산 실패 3/4, 그중 목표 외곽 막힘 0/3.
- e2e18-v379-s61009-r80: 경로 이벤트 [(165.0, False)], 경로 계산 실패 0/1, 그중 목표 외곽 막힘 0/0.
4/16 대표 원본 진단이며 후보 실측은 0회다. `(시각, observed_complete)`의 false는 미지 셀 가설 경로다. 경로 생성과 관측 완료·물리 통과를 구분한다.

## 2026-10-13 기록기 후속

[기록기·새 footprint 후보·공용 스테이징 연결](recording-followup.md). 기존 8개 합성 상태에서 새 후보 생성은 3/8로 v381과 같다. 새 후보를 실제 개선으로 채택하지 않았으며, 실제 입력 녹화와 짝비교가 필요하다.
