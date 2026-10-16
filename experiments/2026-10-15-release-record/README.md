# rel22adapt — release21 B 관측 전용 학습 RGB

기준: `46afd8b095e74954439f98b28f2aa52af3eaea01`. 제어·물리·카메라 설정을 유지하고
`recording_adapter=act12_observer_v1` + `record_training=True`일 때만 학습 관측을 쓴다.
기록 off가 기본이며 예전 record_training 단독 호출은 계속 차단한다.

ACT12의 실제 dependency `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`의
`harness/grasp_act_solo_recording.py`에서 camera_config/segment/SoloRecorder를 재사용했다.
목적지 인자만 추가하고, solo 전용 승인 함수는 복사하지 않았다. 학생 계약은 act-train의
v6와 동일한 두 변경(schema v6, pickup_site 토큰)을 반영했다. release는 A/B/C 목적지다.

학습 파일은 `rgb/<robot>/*.jpg`, `student-<robot>.jsonl`, `teacher-<robot>.jsonl`,
`student-camera.json`이며 기존 압축/manifest writer로 전체 SHA-256을 보존한다.
기존 제어 상세 원장은 기록 on일 때 `teacher-raw/`로 옮겨 충돌을 피한다.
640×480, 0.1 SIM초, robot_cam, 같은 K/D·화각·장착이다. RGB는 명령 전,
라벨은 같은 시각의 명령 후에 저장한다. prefix는 학습에서 제외한다.
끝나지 않은 명령·timeout은 done으로 만들지 않으며 training_include는 항상 false다.

추가 렌더는 기존 SnapshotRenderBroker의 복사 렌더 방식을 따라 별도 mjModel/mjData에서 한다.
기존 broker의 기본 mount 재설정은 적용하지 않고 bound v3 카메라 배열을 그대로 복사한다.
렌더마다 정의된 기구학 출력(카메라 포함)·model 카메라 배열·mjSTATE_INTEGRATION 및 Python/NumPy/world/controller RNG의
바이트 해시가 동일한지 검사한다. 복구하거나 상태를 제어기에 전달하지 않는다.
기록은 SIM 단계·명령·제어 관측 주기를 바꾸지 않지만 렌더/I/O로 wall 비용은 증가한다.
새 탐색/수용 상수는 없다. 기록 주기 허용 편차 0.002초는 ACT12 그대로다.
release 경로의 계획/탐색은 반복 수·SIM 시간으로 제한된다. wall 타이머는 성능 기록이다.
시간 상한 종료는 기존 release_timeout과 함께 termination=cap_end로 표시한다.

구현 전 제출 차단 분포는 `preflight-rejections.json`이다. 세 범주는 같은 60개 실행에
중복 적용된다. 소스 검증과 원격 물리 결과는 구분하며, 모든 off/on 시도와 원본 위치는
후속 `equivalence.json`과 `summary.json`에 남긴다. 2시드 동일성은 새 관문 40회나
학습자료 수용이 아니다. 기록 대기열은 조정자 재승인 전 제출하지 않는다.

## 재현

```
.venv-sim/bin/python scripts/run_release_recording.py --episode 0 --out <off-raw>
.venv-sim/bin/python scripts/run_release_recording.py --episode 0 --record-training --out <on-raw>
.venv-sim/bin/python scripts/audit_release_recording.py --pair <off-raw> <on-raw> --output <report.json>
```

Mac 물리/렌더 0. 원본은 gcp1 영속 디스크, Mac에는 요약과 해시만 회수한다.

## 참고 자료

- ACT12 queue: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act12-record-da4727b6.json`.
- ACT12 v6 계약: `/Users/changmin/projects/ugrp-wt/act-train/harness/grasp_act_contract.py`.
- ACT12 writer: 위 dependency SHA의 `harness/grasp_act_solo_recording.py`.
- [MuJoCo Python 공식 문서](https://mujoco.readthedocs.io/en/stable/python.html): mjData는 참조이므로 상태 비교 시 복사한다.
- [MuJoCo state 공식 API](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html#mjtstate): mjSTATE_INTEGRATION 상태 집합. 렌더 순수성은 문헌 주장에 기대지 않고 실제 guard와 off/on으로 검증한다.

1라운드(`9df35e49`): 두 시드 모두 명령/물리 원장은 같고 입력 감사 0/0, 864프레임이지만,
직접 render_jpeg가 live 카메라 캐시를 갱신해 FK 진단값 48곳이 달랐다. 결과 JSON의
정확한 동일성은 실패로 보존했다. 분포를 먼저 기록한 뒤 복사 렌더로 수정했다.
원본: gcp1:/home/ugrp/ugrp-sim/ops-reviews/rel22adapt-round1-rejections.json.

2라운드(`7fcbe7c9`): off 2회 성공, on 2회 HOST_ERROR. 전체 mjData 배열을 무차별
해시한 감사가 비활성 arena efm_* 3필드를 읽어 오탐했다. GCP에서 물리 단계 0·렌더 전
연속 두 읽기만으로도 동일 필드가 달라짐을 확인했다. 공식 mjSTATE_INTEGRATION과
정의된 기구학/카메라 출력으로 감사 범위를 명시했다(허용 오차 추가 없음).
MuJoCo 문서상 efm_*는 implicit effective metric이 활성일 때 계산되는 arena 자료다.
원본: gcp1:/home/ugrp/ugrp-sim/ops-reviews/rel22adapt-round2-guard-diagnostic.json.

## 최종 검증 (3라운드, 2026-10-15 gcp1)

실행 소스: `f476338533b7608bab25422b360491d5795f6fde`.
고정 worktree: `/Users/changmin/projects/ugrp-wt/release22-src-f4763385` (clean).
후속 기록/CI 목록 커밋은 실행 소스와 구분하며, 이 소스를 바꾸거나 과거 결과를 승계하지 않는다.

| seed | off/on 성공 | 명령·물리 원장·제어/평가 결과 해시 | on RGB | off/on wall/SIM |
|---|---|---|---|---|
| 88600 | 2/2 | 동일 | r1 216 + r2 216 | 2.569 / 3.294 |
| 88601 | 2/2 | 동일 | r1 216 + r2 216 | 2.555 / 3.250 |

최종 864프레임 모두 JPEG 640×480·10Hz, 실제 주기 0.099999999999767–0.100000000000477초.
관측/라벨 짝·이전 발행 명령·자기 로봇 참조·전체 이미지 SHA를 검사했다.
SIM t=10.1–31.6의 release만 기록하고 prefix는 제외했다. 추가 렌더 864회에서
공식 통합 상태·정의된 기구학/카메라 출력·카메라 설정·RNG 변화 0, 입력 감사 0/0.

원격 원본은 `gcp1:/home/ugrp/ugrp-sim/runs/rel22adapt-r{1,2,3}-<seed>-<off|on>-<sha>/raw`.
`summary.json`에 12회 전부(완료 성공10, HOST_ERROR2)를 소스별로 구분했다.
서로 다른 소스를 성공률로 합산하지 않는다. 전체 파일 해시 12/12 통과.
1라운드 비교 0/2와 2라운드 HOST_ERROR2를 최종 2/2 인수 근거에 합치지 않았다.
실패 HOST_ERROR 두 실행은 prefix 각 로봇 6프레임(각 실행12장), 처음·중간·끝을
몽타주로 확인했다. r1/r2가 반대 끝을 보고 있었고, release 기록 전 감사에서 종료됐다.
Montage 원본/시각·해시는 `frame-review-round2.json`에 있다. Mac 물리/렌더·모델 호출0.

카메라는 ACT12 실제 원본의 MJCF 광학 인자·runtime 장착/해상도와 정확히 일치한다.
`student-camera.json`의 명목 vfov 42.1489488115246°와 MuJoCo intrinsic 카메라의
cam_fovy 42.18818654076867°는 기존 파이프라인의 서로 다른 값이다. 이를 바꾸지 않았고
두 값을 같다고 보고하지 않는다. 비교는 `camera-compatibility.json`에 있다.

오프라인: 관련 3파일 **32 passed** (MuJoCo/GL stub 포함). CI 목록에도 3파일을 등록했다.
`equivalence.json`은 wall/load/기록 메타데이터만 제외하고 제어·평가 결과 전체를 비교한다.
기록/수용은 별도이며 training_include=false다. 최종 on 2회는 대기열 pilot2와 같은
시드를 쓴 진단 원본이므로, 조정자가 원본을 검토해 pilot으로 수용할 수 있으나 자동 재사용·학습 수용하지 않는다.

대기열 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-rel22rec-record-46afd8b0.json`:
명령60/60, 고정 소스·adapter 파일 해시·동일성 결과·funnel 연결, pilot2→remaining48→reserve10 유지.
coordinator_approval은 이전 SHA의 승인 이력 그대로 보존하고, 현재 승인/ready/실행 플래그는 false,
status=awaiting_coordinator_approval이다. `rejection_table` 원래 값·해시를 유지했다.
공유 gcp1 VM은 현재 24h 상한이며 대기열 요구8h와 다르므로 bulk 전 운영 확인이 남아 있다.
우리 실행·예약·lease만 종료했고 다른 작업/공유 VM은 유지했다. Draft PR #521.

인계 갱신: 위 내용은 준비 시점의 검증 기록이다.2026-10-15 20:23:42 KST에 별도 조정자가
동일 f4763385의 기록 재승인을 추가한 것을 최종 확인에서 관측했다. 현재 approved/ready는 true,
status 문자열은 awaiting_coordinator_approval 그대로이며 submitted=false다. 변경을 덮어쓰지 않고
`queue-handoff.json`에 별도로 보존했다. 본 기록 배치는 이 작업에서 제출하지 않았다.
