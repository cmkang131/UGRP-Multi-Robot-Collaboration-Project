# search15 — 유한 재관측과 검증된 사전 파지 후보

2026-10-15 · PR #484 · 구현 소스 **`b0fd360f2496cbf781781951e0473950f37f8e3d`**.
부모 **`8d9ad79a42a8a5486ce6cbf65aef87e78cd87f8e`**, 저장 실행 소스 **`abe63b9034b400c61314e76b382dea3c8f81c0ce`**.
후속 기록 커밋은 구현·계획 파일을 바꾸지 않는다. 대기열의 `sha`는 기록까지 포함한 최종 push HEAD다.
[search14 표 1·제안](search14.md)을 먼저 읽고 그 두 층만 수정했다.
새 물리 실행·렌더·계산 호스트 접속·모델 호출 **0회**, 실제 회복 성공률 **미측정**이다.

## 변경과 경계

세 옵션은 **서로 독립적이며 기본 off**다. `progress_view_recovery_v3`, visible_only,
issued pose, coordination off 조합에서만 켤 수 있다. CLI → 배치 자식 → 교사 → 결과 원장에
전달하고, 속도/기록 관문의 옵션 불일치를 거부한다. 실제 진단 후보는 셋 모두 ON이다.

|옵션|발동 조건과 동작|
|---|---|
|`--peer-reobserve peer_reobserve_v1`|peer wait의 정지 지점에서 필요한 상대가 현재 보이지 않으면, 마지막 자기 관측 방향으로 카메라를 돌린다. 카메라만 → 몸 방향 −30°/＋30°의 3회 유한 시도, 실패하면 검사한 후퇴 후 재계획.|
|`--obstacle-reobserve obstacle_reobserve_v1`|축방향 후보 전부 실패했고 실제 `blocked_goal`을 만든 화물/벽이 기억이면, 그 ID를 현재 자기 카메라로 다시 보려 시도한다. 새 측정이 들어오면 좌표를 갱신하고 전체 후보를 다시 검사한다.|
|`--pregrasp-sampling pregrasp_sampling_v1`|기존 축방향 후보가 모두 거절되고 재관측이 진행 중이지 않을 때 `grasp_act_goal_set.ANGLES_DEG` 13각도 × 기존 AXIAL 5거리 = 65자세를 검사한다. 가능한 자세 중 전체 경로 비용 최소를 선택하고 선택 후 재검사하며 유지한다.|

정상 경로에는 새 선택기를 넣지 않는다. 목표 점유 여유, 80mm align 진입, 30mm READY 위치,
3초 목표 차단 시한, 6초 상대/자기 무진척 조건, 12초 상대 encounter 시한은 그대로다.
재관측은 시한을 초기화하지 않는다. 장애물 재관측 1회, 상대 encounter 최대 2회,
각각 view 3×0.6초·후퇴 최대 0.6초/60mm·전체 최대 2.8초다. 종료 사유를 원장에 남긴다.
실제로 새 관측을 얻을지는 새 실행에서 확인해야 한다.

기억 만료는 free 증거가 아니다. 재관측 중에는 기존 위험물을 보존해 카메라/몸체 동작을 검사하고,
재관측하지 못한 차단 화물/벽은 기억 만료만으로 계획에서 빠지지 않는다. 새 관측이 같은 ID를 갱신한다.
상대는 fresh 관측으로 goal clear를 0.3초 확인해야 wait가 해제된다. 스캔 때문에 띠가 잠시 안 보일 때는
마지막 관측 띠로 이 확인을 하되, 새 접근/READY/집기는 다시 현재 띠를 요구한다.

새 필드는 관측 어댑터가 이미 허용한 측정과 `seen_t`뿐이며 `visibility.observations` 아래에 둔다.
상대 마지막 좌표는 재탐색 방향/보수적 위험물 검사에만 쓴다. 새 위치를 추측해 fresh로 만들지 않는다.
정답·접촉·측정 관절·실제 자기 pose를 제어 입력으로 추가하지 않았다. ACT 학생 경로도 바꾸지 않았다.

## 후보 검증과 공동 파지 각도 근거

`sim/grasp_act_pregrasp.py`는 생성 → 기존 hover/8단 하강/상승 IK → 집게 기하 →
몸체/팔 swept 검사 → 접근 연결·60mm 사전 파지 퇴로 → 끝 띠 가시성 → 비용 순으로 필터한다.
기존 몸체 반경과 장애물 여유를 사용한다. 팔은 명령 PWM의 FK와 소스의 capsule/패드/카메라 bracket
기하를 검사한다. 5 PWM 이내 보간, capsule 축 4mm 표본과 4mm 팽창,
연결 경로 10mm 표본 및 yaw/PWM 전이 검사다. 바닥·벽·화물·상대·빔을 검사하며,
집게 닫기/들기 때 맡은 빔과 패드의 의도한 접촉만 기하 거절에서 제외한다.
물리 collision 설정이나 weld를 바꾸는 것은 아니다. 선택된 경로의 실제 발행 pulse/카메라 동작과
READY 직전 실제 잔여 오차에 대한 팔 경로도 다시 검사한다.

가시성은 기존 카메라 FK로 15개 알려진 띠 probe를 투영하고 보수적 18° cone 및
관측 장애물 시선 가림을 검사한다. 5개 이상이어야 한다. 이는 실제 렌더의 가시성 판정이 아니며,
실제 READY에는 기존 현재 visible_probes≥5를 계속 요구한다.

집게에 wrist yaw가 없으므로 ±90°를 허용하지 않는다. 빔 폭 `w=40mm`, 패드 길이 `14.3mm`,
패드 반높이 `3.5mm`, 명령 공간 IK의 pitch `p`에 대해 두 측면 접점의 종방향 이동은
`w·|tan(offset)|/2`, 패드의 수평 반길이는 `7.15·|cos(p)| + 3.5·|sin(p)| mm`다.
전자가 후자 이하여야 하며, `w/cos(offset)`가 모델 집게의 closed/open 내측 간격
**29–61mm** 안에 있어야 한다. 이 조건과 IK를 적용한 15° 격자에서 **0°, ±15°만 허용**된다.
예제 .198m/.024m IK는 약18.86° 한계이며 30°·90°는 거절된다. 저장 사례별 pitch/한계는
각 후보 `jaw_geometry`에 남는다. 양끝은 서로 반대의 outward 반원을 유지한다.
이는 양쪽 패드가 닿을 수 있는 **필요 기하 조건**이며, 양팔 실제 파지·마찰·하중 안정성의 증명이 아니다.

## 저장 입력 재생과 테스트

[요약 JSON](search15-summary.json)에 전체 13개와 첫 분기, 각도 분포, 거절 사유,
재관측 시작/시도/종료 및 파일 해시를 남겼다.

- `test_grasp_act_search15.py`, `test_grasp_act_recovery.py`, `test_grasp_act_goal_set.py`: **103 passed**.
- 기준 13개 **7,638/7,638 명령**과 done/phase 재현. 새 옵션 모두 off도 기준과 동일.
- 새 옵션 모두 on: 정상 **6/6**, **4,664/4,664 명령·상태 변화 0**. 이는 저장 정상 입력 보존이지 새 물리 6/6이 아니다.
- 전체 replay `invisible_measurements=0`, `held_world_reads=0`.
- 원본 입력 65개 + manifest 13개 = **78/78**를 실행 최상위 SHA256SUMS에 대조했다.
  압축 입력은 압축/해제 해시도 확인했다. 이번 라운드에서는 새 프레임 열람/렌더를 하지 않았다.
  실패의 영상 관찰 범위는 search14의 47시각·141장 기록을 인용하며 이번에 다시 봤다고 주장하지 않는다.

|idx / seed|저장 명령 수|변경 명령 / 상태|첫 변경 경과 SIM초|분기 뒤 확인한 내용|
|---|---:|---:|---:|---|
|6 / 79030|134|0 / 0|없음|65개 각도×거리 검사 추가; 가능한 자세 없음, 기존 handoff 유지|
|7 / 87003|354|43 / 1|13.4|기억 화물 재관측 → 이후 −15°/208mm 후보 선택(shadow)|
|8 / 87007|974|0 / 0|없음|이전 진단에서 성공한 사례; 변화 없음|
|9 / 87008|330|60 / 1|10.5|상대 기억 만료 뒤 능동 재관측|
|10 / 87014|504|60 / 0|19.2|상대가 시야에서 사라진 뒤 능동 재관측|
|11 / 87017|226|43 / 12|7.0|기억 벽 재관측 → 갱신/퇴로 재평가|
|12 / 87032|452|59 / 0|16.7|prefix 대기 중 상대 능동 재관측|

분기 뒤에도 입력 영상/측정과 적용 명령 이력은 **기존 실행 것**이다. 따라서 표의 변경은
shadow 결정이며 새 주행·재관측 성공·파지 성공이 아니다. idx8은 옛 관문 실패 집단에 속하지만
이번에 재생한 저장 진단에서는 이미 성공했다. hard6은 각도 후보가 늘어도 벽 점유/집게 기하 등으로
거절되고 명령은 그대로다. 이 결과를 hard 개선으로 보고하지 않는다.

재현 명령(기존 환경, World/렌더러 생성 없음):

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.replay_grasp_act_search15 --run /Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-abe63b90 --out /private/tmp/search15-replay.json
```

최종 재생 상세는 `outputs/e2e18-admin/gcp-reports/search15-replay.json.zst`에 있다.
압축 SHA-256 `275089fd6882e8daf6a2ef29c11cc60b040f912a35349c4f22097d42003deaa8`,
해제 SHA-256 `234c23c23087dffe9aac3efa1c43d9ef9261fca6ff40a69e6e2a770c7a53fb29`.
테스트·재생 stdout·manifest·이전 대기열 변경 기록도 같은 로컬 폴더에 보존한다. 외부 백업 완료를 뜻하지 않는다.

## 진단 대기열과 통과 기준

`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<최종 SHA8>.json`.
최종 push HEAD 및 두 계획 파일 해시를 고정하며, 이전 search 대기열 14개는 모두 ready=false다.
기존 실행 가능 표시가 남은 4개는 원문 해시를 붙인 before-search15 사본을 보존한 뒤 껐다.
그 상세와 전후 해시는 `search15-predecessor-queues.json`에 있다.

총 **19개 예정**: 정상6 → 정상 **실제 6/6**이면 옛 실패6+hard1 및 신규6을 함께 제출 가능하게 한다.
옛 실패 결과/완료 여부를 신규6의 제출 조건으로 넣지 않는다. 알려진 공통 제어 결함 정지 규칙은 유지한다.
각 batch는 `repeated_cause_v1`, cap60 SIM초, 같은 SHA/프로필/머신을 사용한다.
정상 6/6·신규 **6/6**·입력감사 0/0·HOST_ERROR/중단 0을 진단 통과 기준으로 둔다.
옛 실패6과 hard1은 개발 진단이며 **별도 분모**, handoff는 성공이 아니다.

신규 계획은 `teacher-search15-novel-plan.json`, 후보 seed **215500–215505**다.
기존 가시 시작/정적 nominal-goal 필터와 같은 생성 조건이며 이번 시작 제외는 **0/6**이다.
로컬 계획/대기열 검색에서 사용 이력을 찾지 못했다. **운영자가 실제 재고·타 작업 예약을 확인하고
예약한 뒤에만 실행**한다. 충돌 시 계획/해시를 새로 고정해야 하며 임의 치환은 금지한다.

GCP n4-highcpu-64, 운영자만 원격 실행. 비용/8시간/유휴20분·디스크/합산 부하 admission 유지.
모델 호출0·학습 RGB off·weld off. 새 원본 예상 상한 **19×160MiB=3,040MiB**(소스/환경/아카이브 별도).
진단 원장에 `reobserve_log`, `reobserve_pending`, `candidate_angle_counts`,
`candidate_rejection_counts`, `goal_set_log`를 보존한다. 실패/중단/HOST_ERROR도 회수·해시 확인한다.

**속도16·관문40은 조정자 새 승인 전 ready=false**,
`gate_promotion_authorized_if_all_conditions_pass=false`, speed 자동 승격도 false.
관문40은 모두 처음 사용하는 새 seed이며 기존 관문87000–87039, 개발 진단, 학습 seed를 재사용하지 않는다.
관문 ≥38/40 판정과 속도16동시×30초 측정은 아직 미수행이다. 신규6 실제 일반화와
각도 파지의 실제 성공·계산 비용은 다음 진단/승인된 속도 측정의 남은 검증이다.

## 참고 자료

2026-10-15 원문 열람:

- [MoveIt Task Constructor 공식 튜토리얼](https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html):
  GenerateGraspPose의 15° angle delta, ComputeIK wrapper, Cartesian approach/connector/retreat의 단계적 후보 검증 구조를 참고했다.
  이 저장소에 MoveIt을 설치하거나 예제의 attachment/물리 충돌 허용 설정을 적용하지 않았다.
- [MoveIt Grasps 공식 README](https://github.com/moveit/moveit_grasps): 자세 생성·IK 필터를 참고했다.
  README는 friction cone/동역학을 다루지 않는다고 명시한다. 두 자료는 우리 로봇 공동 파지 성공 근거가 아니다.
- 내부 기하 근거: `sim/masterpi_geometry_v3.py`의 PHYSICAL_V3/패드 길이,
  `sim/masterpi_dynamics_v2.py`의 arm capsule·jaw 35mm/16mm,
  `sim/masterpi_model_v3.py`의 pad 위치/길이 이관,
  `sim/zone_cargo.py`의 0.60m×40mm×32mm 빔/paint,
  `harness/visual_arm_v3.py`의 명령 FK/IK, `sim/grasp_act_gaze.py`의 기존 카메라 보정.
  출처 파일 해시는 요약 JSON의 구현 파일 및 Git 구현 SHA로 연결한다.
