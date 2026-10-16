# warp4 — NOT_READY / PR #549 DRAFT

빔 짝·release를 PR534 위의 공통 MJWarp 엔진으로 연결한 **미자격 후보**다. 새 `warp4-flow-teacher` 실행기의 기본 backend는 MJWarp다. 운영 경로 전환 완료나 교사 성공으로 보고하지 않는다. LLM E2E는 범위 밖이며 CPU 경로를 유지한다.

| 최종 R3 | 요청 world | GPU 초기화 | 완료 교사 | HOST_ERROR | SIM cap_end |
|---|---:|---:|---:|---:|---:|
| 빔 짝 |4|4|0|4|0|
| release S1 A/B |6|6|0|6|0|
| release S3 A/B |2|2|0|2|0|

최종 controller/backend는 `a2216618a2`, 빔 짝 adapter835ccef2 + teacher26f84d0f, release8e81b7d9다. private MPS client3개를 확인했으나03:47UTC CUDA illegal memory access700으로 빔 짝이 exit1, release 두 프로세스가 SIGSEGV(exit−11)했다. release의 원본 summary가 running으로 남았으므로 **원본은 보존하고 별도 종료 receipt로 HOST_ERROR 재분류**했다. 물리 실패나 성공0/12로 바꾸지 않는다. 정확한 CUDA fault 원인은 미분리다.

40 / A40 / B40 관문은 **미제출**, N16/64/256 정상상태·CPU16 동시 처리량도 미측정이다. [대기열](teacher-gate-queue.json)은 NOT_READY이고 승인하지 않았다. [원본 재계수](final-summary.json), [누적 통과·거부표](final-rejection_table.json), [원본 해시](raw-sha256.json), [manifest 독립 검사](integrity-verification.json). 1641파일49,836,988바이트, 선언된1219파일은1219일치·누락0·불일치0이다. 원본 전체는 gcp2 L4 영속 디스크 `/home/ugrp/ugrp-sim/runs/warp4/`에 있다. Mac에는 요약·몽타주·선택 실패 프레임·8MB 이하 영상만 회수했고 전체 원본 원격 백업을 주장하지 않는다.

## 단일 모델과 입력 경계

[모델 차이 표](model-differences.md): 같은 관절 구성에서도 숨겨진 warehouse 물체3종의 시드별 질량·크기가 다르다. 이를 변경하지 않고 지원되는 세계별 배열로 보존했다. `dof_length`는 PR534의 정확한 world-indexed sleep 읽기를 쓰며 SLEEP-off 무시 예외는 쓰지 않는다. 빔 짝 N4의 초기 qpos 기대=실측4/4, 서로 다른 qpos4·첫 r1 RGB4를 확인했다(완주·N16 증명 아님). release S3에는 S1의3개 free body가 없어 S1/S3는 별도 모델 구성이다. 하나의 완전히 동일한 모델로 합쳤다고 보고하지 않는다.

READY/GO/ACK·peer_yield·release_sweep_wall_aware·held suppression·성공식을 고정 소스에서 재사용했다. world별 모듈/port/명령 tape/감사를 격리한다. **release의 기존 observable_v2 grasp prefix는 특권 scene-preparation이며 visible-only 교사 성공으로 세지 않는다.** full-flow 입력 경계와 본 release 자격 검증은 미완료다. 학생·학습 기록·LLM 호출0, weldOFF, Mac 물리·렌더·GUI0이다. C 성공과 합산하지 않았다.

추가 전달된 사용자 결정에 따라 `placement_graspable_filter_v1`은 기본off, 새 후보에서는on으로 정답 runtime을 쓰지 않는 기존 certified stance 검사를 수행한다. 모드/장면/held profile을 진입점에서 검사한다.

## 영상·기록·검증

`playback-review.md`에 실제 검토 구간과 제한을 적었다. 두 HOST_ERROR/감독 중단 prefix를 전체2Hz와 가능한 terminal10Hz로 직접 보았고, 빔 짝의 native6시점/양쪽 카메라 파일을 회수했다. 새 MJWarp 성공 영상이 없어 성공 비교는 미완료이며 행동 실패의 인과 원인을 주장하지 않는다. GPU의 기존 반투명 구역 불투명 표시 차이도 남아 있다.

R3 SIGSEGV에서 release8world의 in-memory10Hz ring은 잃었다. 이후 기록 전용 `DiskRing`을 추가해 매 tick 원본JPEG를 atomic slot+hash journal로 남기고, finalizer 부재·부분 slot·깨진 journal 회복을 비물리 시험했다. 과거 누락을 복구한 것은 아니며 새 디스크 ring·C N1 비교 경로·terminal evaluation row 보존은 GPU/물리 미검증이다.

관련 비물리 시험 **27 passed**. C16/정상상태 처리량·독립40/A40/B40·완주 입력 감사·새 기록기의 GPU 검증은 남았다. MPS daemon/client는 종료됐고 다른 작업 PID에는 신호를 보내지 않았다. L4의 다른 작업 lease가 있어 VM을 정지하지 않았다. 8h·유휴20분·budget-stop을 변경하지 않았다. CPU 분석 호스트의 guestTerminate 기록을 확인한 뒤 승인 규칙에 따라 재시작했다.

참고: [MJWarp 배치/graph](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html), [freejoint](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-freejoint), [private MPS 진단](mps-plan.md), [SciPy1.17.1](https://pypi.org/project/scipy/1.17.1/). 조사·source/static·초기화·부분 GPU 물리·완주/관문을 구분한다.

최종 호스트 확인: CPU gcp2는 다른 lease/managed worker가0인 것을 검사한 뒤 STOP, `TERMINATED` 확인. L4는 `beamact3-A.json`·`warp3.json`을 보존하여 `RUNNING` 그대로다. [입장 검사](cpu-stop-admission.json), [실제 VM 상태](host-final-state.json).
