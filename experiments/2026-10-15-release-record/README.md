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

추가 렌더마다 mjSTATE_INTEGRATION 및 Python/NumPy/world/controller RNG의
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
