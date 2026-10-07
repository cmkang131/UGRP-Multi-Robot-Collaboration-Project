# egomap11 — 카메라 자세·바닥 투영 분해 (PR #405)

## 구현·계산 전 사전 등록

시작 `5ba7dd29`, `claude/ego-wall-map`. egomap10의 기존 검출기 pixel P94–99%, 수동 접점 투영
중앙0.457–0.665m와 `floor_boundary_v1` FAIL을 보존한다. 검출기 튜닝 없음. PR #406은 읽기 전용이다.
새 단계는 카메라 transform 진단 및 필요할 경우 default-off `camera_pose=servo_fk_v1` 하나다.

### 자료·좌표·입력 경계

- 기존 s1042/1043 개발, s1044–1047 확인 재생. 이미 본 자료이며 새 독립 확증으로 부르지 않는다.
- 기존 egomap10의 봉인된36 RGB/벽 접점 polyline·96열·ignore·무하중 정착 eligibility를 그대로 쓴다.
  추가 주석/좋은 프레임 선택/거리로 나쁜 점 제외 없음. 원 baseline에서 양의 깊이·4m를 만족한
  주석 열을 고정 분모로 하고, 새 투영의 무효/4m 초과도 별도 비율로 기록한다.
- s1045–1047 `eval_only/camera-pose.jsonl`의 실제 optical 원점/회전은 평가기에만 읽는다.
  s1042–1044에는 같은 파일·qpos가 없다. 실제 per-frame 자세 비교는 NA로 남기며 재구성값을 GT로 부르지 않는다.
  기존 문서의 '실제 camera pose 없음'은 이번 파일 인벤토리로 s1045–1047에 한해 정정한다.
- world→chassis yaw floor frame을 명시한다. 높이는 floor z, 전후/좌우는 chassis xy 원점,
  optical yaw/pitch/roll은 각각 전방 yaw·elevation·optical 축 회전이다. base roll/pitch/arm joints가
  기록되지 않은 경우 실제 camera 합성 오차를 그 두 기구 원인으로 임의 분할하지 않는다.
- 실제 카메라 로그와 RGB는 시각으로 exact join한다. cached/from-body transform 차이도 확인한다.
  GT 차체·실제 카메라·벽 지도는 scoring/단일항 counterfactual에만 쓰며 명령 FK·지도에 전달하지 않는다.
- 런타임에 허용된 servo 입력은 **자기 발행 PWM 이력**이다. frames의 actuator_state.servo_pulses는
  측정 encoder가 아닌 명령이다. 측정 관절을 있다고 가정하거나 simulation qpos를 입력하지 않는다.

### 분해·후보 규칙

1. 등록된 v3 무하중 표와 실제 카메라를 모든 exact-join 프레임에서 비교한다. eligibility 안/밖·명령 자세별로
   xyz(mm)·yaw/pitch/roll(deg) 차이 중앙/P05/P95와 표본 수를 기록한다. HIGH는 별도 표로 보존한다.
2. 봉인 수동 접점을 같은 GT 차체에 투영한다. nominal과 실제 카메라 전체 치환, 단일항 x/y/z/
   yaw/pitch/roll 치환, 실제에서 한 항만 nominal로 되돌린 결과를 계산한다. 비선형 효과이므로 기여율을
   임의 합산하지 않는다. nominal→실제 point displacement와 GT 벽 오차를 모두 기록한다.
3. 팔 자세 의존 기하 경로를 확인하면 ROS robot_state_publisher의 fixed transforms × joint rotation
   곱을 매 frame 계산하는 `servo_fk_v1`을 독립 옵션으로 구현한다. 기존 로봇의 고정 link/joint/mount/PWM
   정의만 재사용한다. GT 잔차를 fit하거나 새 sag/bias·mount·FOV를 튜닝하지 않는다. 명령 FK는 실제
   관절/바닥 자세 측정과 다르며, 이 한계를 숨기지 않는다. off bytes와 원 v3 table은 보존한다.

### 고정 투영 관문

s1042–1047 **각 녹화**에서 고정 주석 분모≥50개, 새 양의 깊이·4m 유효율≥95%,
GT 차체 자세의 벽 접점 투영 오차 **중앙≤0.10m, P90≤0.25m**, baseline 중앙 비악화,
behind-camera 출력0, off bytes 동일, GT 입력0을 모두 요구한다. 0.10m는 기존 지도 한 칸,
0.25m는 원벽과 혼동할 수 있는 오차 꼬리를 제한하는 개발 관문이며 검증된 실물 허용치가 아니다.
개발2→설정/소스 고정→확인4, 결과 뒤 임계값·방법 변경 없음. 항목별/녹화별 판정, 합산 금지.
실제 camera oracle는 평가 상한이며 후보 관문 통과로 세지 않는다.

모든6건 통과 시에만 기존 RBPF100 + positive_depth + pose_graph + wall_confidence를 재생하고
회색 GT벽/지도 confidence 음영/경로 그림을 갱신한다. §17·§19 기준은 그대로 유지한다.
미달/자료 부족이면 지도 재생·그림 갱신을 하지 않고 결과를 기록한다. 같은 원인 반복 시 추가 수정 중단.

오프라인만 예정: 새 물리·렌더·모델 호출0, freeze 옵션 사용0. 새 물리가 필요하면 별도 유한 사전 등록 후
agent_lock/ugrp_session/한 번에 하나를 따른다. 현재 남은 로그로 진단하며 자동 장기 물리 재생은 하지 않는다.
시험 통과 후에만 commit/push, Codex trailer, DRAFT 유지·병합/강제 push/reset 없음.
raw `/Users/changmin/projects/ugrp/outputs/camera-pose-projection-v1/`, 원본 보존, ENOSPC=HOST_ERROR.
PR #406 재사용 가능성만 기록하며 그 파일/브랜치는 수정하지 않는다. TensorBoard/Drive는 이전 결정대로 생략.

## 구현·조합

[REFERENCES](REFERENCES.md)의 표준 TF chain을 `harness/servo_camera_fk.py`에 구현했다.
명령 변화에 따른 카메라 geometry를 매 frame 다시 계산한다. 이 옵션은 **명령 FK 후보**이며 측정 자세 보정이 아니다.
실제 pitch 불일치는 확인했지만 관절·차체 원인 분리는 불가하므로, 명령 FK가 그것을 해결하는지는 관문으로 판단한다.

| 옵션/API | 기본 및 적용 |
|---|---|
| `camera_pose=off` | 기본. 기존 `geometry(servo, mode)`의 행렬·offset·기존 검출 scan/면/JSON bytes 불변 |
| `camera_pose=servo_fk_v1` | `geometry(servo,'off',camera_pose=...)` → 새 v3 fixed chain과 자기 PWM으로 `ColumnModel` 생성 |
| `wall_camera_calibration=v3_unloaded_extrinsic_v1` + FK | 두 모델 동시 선택은 오류. PnP 표와 명령 FK를 더하거나 보정 계수로 섞지 않음 |
| closed/unknown load, 범위 밖 명령 | 미지원으로 보류. 이번 관문은 기존 무하중/정착 프레임만 비교 |
| 기존 검출기·메모리 조합 | 검출은 기존 `wall_detector=off`. 통과 때 생성한 ColumnModel의 segments/camera transform을 기존 SelfWallMemory RBPF100+guard+graph+confidence에 전달 |

`code/audit.py`는 실제 camera 로그를 읽는 **평가 전용**, `code/evaluate_fk.py`는 자기 transform 예측을
저장·hash한 뒤에만 GT 차체/벽/주석으로 채점한다. runtime FK는 sim/평가/모델 모듈을 import하지 않는다.
공유 `visual_arm.py`, PR #406 파일, 실패 검출기, PnP table은 수정하지 않았다. 새 venv/의존성 설치0.

### 개발2 → 무튜닝 동결

구현 `00ea2387`, 관련16시험 통과. s1042/1043을 먼저 재생했다. 명령 FK는 기존 PnP 표보다
투영 오차가 커서 개발0/2 FAIL이다. 이득·pitch·mount·관문을 수정하지 않고 [freeze.json](freeze.json)에
동일 소스/기준을 고정한다. 확인4는 같은 후보의 실패 범위를 기록하는 단일 재생이며 새 독립 확증이 아니다.
지도 재생은6건 전체 관문 통과 때만 허용한다.
