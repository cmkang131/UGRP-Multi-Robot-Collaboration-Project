# 높은 자세 공동 운반 후보 v93

2026-10-03. D1의 새 학생 제어기 후보다. **v92 실측 보정(MEASURED_SIM)이 없으면 실행을 차단한다.**
기존 학생의 성공 판정은 승계하지 않는다. 렌더 수집과 P03 인수는 코디네이터가 수행한다.

## 변경과 입력 경계

기존 `zone-final-pair-v88`의 `zone_final_pair_skill.Team/Execution`과 b-v6g/b-v6h1 계열
beam-relative 제어기, 빔 추적기(BeamEdgeTracker), 정적 경로, 가드, 상태 통신, P03의 동일 PF·
0.16 SIM초 지연을 재사용한다. `scripts/run_camera_pair_transport.py`는 이전 LLM 두 로봇
경로이며, 현재 최종 v3 학생의 기반은 v88 어댑터다. 이를 새 LLM 제어기로 대체하지 않는다.

바닥 파지→기존 낮은 lift의 자기 RGB 확인→110/130 mm 경유→150 mm 높은 자세(HIGH)→
운반→역순 경유 하강→바닥 내려놓기→release 순서다. 높은 자세 PWM(3·4·5·6)은
`896,2035,1894,1500`으로 PR #361과 같다. 경유마다 1.2초 보간·2.8초 대기,
HIGH 도착 뒤 8초 대기를 둔다. 실제 발행에는 기존 ArmSequence와 0.05초 격자를 사용한다.
새 높은 영상에서 가장자리가 보인 뒤 유지 기준 영상을 갱신하고, 지연된 자기 영상의
가장자리 기준이 생겨야 운반 준비를 보고한다. HIGH 밖의 적재 base 명령은 거부한다.

10/3 사용자 결정에 따라 위치 추정은 OpenCV다. 기존 markerless probe의 왜곡 보정·
명암/색차·균일 벽 띠 검출을 재사용해, 모호한 여러 띠와 유채색 가림은 버리고 정적 지도
PF에 벽 경계를 전달한다. 기존 PF 수명·운동·관측 품질 검사는 유지하며 학습 분할망이나
체크포인트를 생성·호출하지 않는다. 새 OpenCV 경로의 실제 RGB 정확도는 인수 대상이다.

제어 입력은 자기 RGB·공개 정적 지도·자기 발행 명령과 기존 상태 메시지뿐이다. 현재 좌표,
측정 관절, 접촉, 성공 판정은 제어기에 전달하지 않는다. 카메라 배치/FOV, 로봇·화물 외관,
`masterpi_v3`, `floor_light_v1`, `cargo_noslip_v1`, weld OFF, 초음파 OFF를 유지한다.

## 등록과 보정 조건

- 기준 소스: `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`, 브랜치 `codex/pair-carry-highpose`.
- 새 번들·실행 경로: **`zone-final-pair-highpose-v93`**, 버전 **3.5.0**.
- main+열린 PR 9개 총 10 refs를 조회해 v92/3.4.0 최댓값과 원격 HEAD 일치를 확인했다.
  [조회 원본](reservation_scan.json)을 보존한다. 게시 직전 main+열린 PR 7개 총 8 refs를
  [다시 조회](reservation_scan_final.json)했고 최댓값 v92/3.4.0과 v93 미사용을 재확인했다.
- 새 [등록](../../configs/zone_pair_highpose_v93.json)과 [보정 계약](../../configs/calibration/zone_pair_highpose_v93_contract.json).
  v88/v90/v91 등록과 동결 B/B′/r4/r5는 수정하지 않는다. v91 held-out raw는 읽지 않는다.

새 로더는 schema `ugrp.final_pair_highpose_measured_calibration.v1`, `status=MEASURED_SIM`,
새 계약 hash, 세 지도 hash, `loaded_measurement_bundle_id=zone-final-pair-v92`,
`loaded_pose_id=masterpi-v3-pair-high-150mm-minus40-v1`, `loaded_camera_scope=high_only`를 요구한다.
source SHA, 실측 manifest·v92 일정·기준·조립기 SHA-256도 필수다. 이전 params/pair_model/
camera_models 형식은 재사용한다. loaded 카메라 키는 HIGH 하나이며 바닥/낮은 자세는 요구하지 않는다.
닫기부터 HIGH 정착 전, 하강 중에는 자기 영상의 grip/hold 검사만 유지하고 절대 위치 관측은
건너뛴다. 발행 명령 기반 예측과 불확실성은 유지한다. 이 구간에 임의 카메라 보정값을 채우지 않는다.

이 계약은 D1의 임시 소비자 인터페이스다. D5 담당자는 별도
`ugrp.final_environment_measured_calibration` 계열 HIGH 계약을 만들고 있어 **최종 D5
산출물과의 schema/필드/hash 호환 확인이 남았다**. 정확한 D5 원격 소스가 공개되면 새
로더에 연결하고 관련 회귀를 다시 검증해야 한다. 현재 로더의 synthetic 보정 수락 검사는
D5 호환 완료가 아니다. 실제 보정 파일·기준 B″·조립기 승인이나 v92 측정 완료를 만들지 않는다.

## 코디네이터 인수 계획

1. D2–D5의 기준·일정·조립기 고정 및 v92 수집/적합/독립 검토를 마친다. 해당 실측 파일과
   새 학생 후보 SHA·번들/소스 hash·환경을 고정한다. 아래 계획 출력의 실행 가능 조건을 먼저 검사한다.
2. 기존 stage probe의 구조로 최종 v3 장면에서 **단계별 준비 상태(staged state)**를 만든다.
   정렬 시작, 바닥 파지 직전, 낮은 lift 직후, HIGH 유지, 목적지 HIGH 상태에서 각각
   정렬→파지/lift→HIGH 상승→한 leg 운반→역순 하강/release를 검사한다. staging의 정답은
   평가 소유자만 사용한다. 학생에 전달하는 것은 동일 자기 RGB·발행 명령 이력뿐이며,
   준비 상태의 평가 좌표를 PF 현재 위치로 주입하지 않는다. staged 결과는 E2E/P03와 별도 분모다.
3. 각 단계에서 실제 RGB 가장자리 열/검출/기준 획득, 관절 제한, 빔 상승·기울기·네 집게 접촉,
   외부 지지/weld 없음, 명령·가드 중단을 평가 전용 출력으로 확인한다. 낮은/높은 영상 사이 IoU를
   같은 자세 유지 점수로 해석하지 않는다. 명령 이후의 실제 접촉·관절·카메라 응답을 독립 검토한다.
4. 단계 인수 뒤 **`zone_wide_door_geometry_v3` P03 3×120 SIM초**를 수행한다. 세 사례는
   지도 수가 아니라 문 앞·문 뒤·목적지 전 체크포인트다. 각 사례는 dock 독립 reset에서 시작하며
   실제 이전 leg를 거친다. lower→open→재관측→RGB 재정렬→grasp→low lift→HIGH를 같은 PF로
   이어야 한다. GT 재배치/PF 교체 없이 실행하며 미도달도 분모 3에 포함한다. reset은 회당 최대
   5초로 별도 기록한다(총 360+최대15 SIM초). stage 준비 상태를 P03 성공으로 합산하지 않는다.
5. `SEQUENCE_OBSERVED_UNQUALIFIED`는 순서 관측일 뿐이다. 별도 실제 오차·접촉·운반·방출 판정,
   가림/edge 실패·시간 초과·미시도·HOST_ERROR/ENOSPC를 전부 보존한다. 세 지도 전체 carry,
   일반화, 실물 성공은 별도이며 이번 P03로 확대하지 않는다.
6. raw는 기본 체크아웃 `outputs/` 새 절대 경로에 보존한다. 모델 입력·자기 JPEG/명령·평가 기록과
   SHA-256, source/calibration/bundle/environment를 회수하고 TensorBoard 새 스냅샷에 표시·검증한다.
   자기 세션·자식·잠금만 정리한다. Google Drive는 사용하지 않는다.

계획 확인(물리·렌더 시작 없음):

```bash
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
"$PY" -m scripts.run_pair_highpose --check p03 --expected-source-sha "$FINAL_SHA" \
  --output /Users/changmin/projects/ugrp/outputs/pair-highpose-P03-NEW
```

실측 보정 뒤 코디네이터는 자기 worktree의 고정 SHA·깨끗한 tree·10 GiB 여유·소유 잠금을
확인하고 `ugrp_session.py run <새 세션> -- "$PY" -m scripts.sim_cli workflow run
zone-final-pair-highpose-v93 -- --check p03 --expected-source-sha "$FINAL_SHA"
--calibration <실측 파일> --calibration-sha256 <실측 SHA256> --lock-owner <소유자>
--output <새 절대 raw 경로> --execute`로 실행한다. 보정 부재의 차단을 해제하는 별도 우회 옵션은 없다.

## 검증 기록

관련 5개 파일의 최종 통과 줄은 **`138 passed, 1 deselected in 70.08s (0:01:10)`**이다.
새 후보 검사 20개, 기존 v3·카메라 계약·가장자리 추적·P03 수명주기 회귀를 포함한다.
과거 v6e 재생용 로컬 JPEG `r2/00025.jpg`가 없어 해당 검사 1개는 실행 목록에서 제외했다.
첫 실행의 `138 passed / 1 failed`와 원본 오류도 보존한다. 실제 RGB 재생 통과로 바꾸지 않는다.
[검증 명령·환경·로그/JUnit hash](validation.json), [기존 30개 파일 보존 hash](preservation.json)를 따른다.
컴파일, `git diff --check`, 고정 CI 자료 3개, 표준 workflow 계획 출력도 확인했다.
이는 로컬 결과이며 원격 CI·독립 검토·렌더/P03 인수는 별도다.

추가 workflow 카탈로그 검사는 **`17 passed, 1 deselected in 1.00s`**다.
전체 파일의 첫 실행은 17 pass/1 fail이며, 프로세스 정리 검사의 `/bin/ps`가 샌드박스에서
거부되어 그 검사만 제외했다. 로컬 프로세스 정리 검증 완료로 보고하지 않는다.

[고정 진단 명령](probe_headless.py)을 커밋 **`a19e232a3a2576832a145a0435e9450da017f759`**로
고정하고 52 SIM초 실행했다. teacher station 시작에서 실제 학생의 ArmSequence 상승/하강
경로를 재사용했다. [전체 집계](headless_check.json)와 [집계 코드](summarize_headless.py)를 보존한다.

| 구간/검사 | 실제 결과 |
|---|---|
| 낮은 lift 정착 [8,10)초 | 40/40 표본 상승·네 집게 접촉·외부 지지 없음 |
| HIGH 상승 [10,27.2)초 | 344/344 같은 조건 |
| HIGH 유지 [27.2,34)초 | 136/136 같은 조건, 빔 바닥 최소 114.849 mm |
| 하강 [34,47.6)초 | 257 lifted / 15 not_lifted; 전부 보존 |
| 전체 1,041표본 | 849 lifted / 192 not_lifted; 초기·바닥·release 포함 |
| 목표 관절 2,352개 | 제한 위반 0, 팔 최소 여유 0.2992 rad, 집게 0 m |
| HIGH 순기구학 | 높이 149.857 mm, pitch −40.05° |
| 자기 카메라 기하 | 낮은 자세 양쪽 0열, HIGH 30/32초 양쪽 90열 |
| 비용/환경 | 1,948명령, 모델 호출 0, weld OFF, 렌더 0 |

`lifted`는 빔 바닥≥10 mm·네 집게 접촉·외부 지지 없음·weld 없음의 평가 전용 판정이다.
기하 가시성은 RGB 검출 성공이 아니다. 이 결과는 운반 base 주행·자기 RGB 학생·v92 보정·
P03 인수를 포함하지 않는다. raw manifest의 모든 파일 hash를 대조했으며 원본 위치는
`/Users/changmin/projects/ugrp/outputs/pair-highpose-offline-20261003/headless-a19e232a`다.
원본은 로컬 보관이며 원격 백업으로 표현하지 않는다.

첫 관리 세션은 샌드박스 `/bin/ps` 거부로 물리 시작 전에 종료되었다. 별도 자식/렌더가 없는
고정 종료 진단을 직접 실행했고 종료 코드 0·소유 잠금 해제를 확인했다. 시작/끝 부하 평균은
집계 JSON에 보존했다. 다른 작업의 세션/서버는 변경하지 않았다.

TensorBoard 새 스냅샷 `1003-pair-highpose-v93/high-hold`에 같은 진단의 low 0열/HIGH 90열,
유지 136/136, 상승 344/344, SIM 52초·명령 1,948·모델 호출 0을 등록했다. 이벤트와
서버 API를 원본과 대조했다. 새 영상 등록은 0개이며 없는 wall/model 지연·임무 성공을
0으로 채우지 않는다. [대시보드 검증과 고정 링크](tensorboard_verification.json)를 따른다.

## 참고 자료

- [D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)
- [높은 자세 후보 PR #361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361),
  [소스 고정 설계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a9481446d9c7c503bdbc53941d3538cd5ec5ee12/experiments/2026-10-03-v92-loaded-schedule/README.md)
- [현재 v3 학생](../../harness/zone_final_pair_skill.py), [기존 운반·빔 추적](../2026-09-29-pair-v6e-carry/README.md),
  [b-v6h1 범위](../2026-09-30-pair-v6h-carry/README.md)
- [P01](../2026-09-30-e2e-p01-env/README.md), [P03](../2026-09-30-e2e-p03-provider/README.md),
  [물리 인계](../../PHYSICS_HANDOFF.md), [실행 버전 관리](../../docs/execution_versioning.md)
- [재사용 OpenCV 검출기](../2026-09-26-markerless-probe/markerless_probe.py),
  [새 관측 어댑터](../../harness/opencv_wall_observation.py), [새 제어기](../../harness/zone_pair_highpose_runtime.py)
