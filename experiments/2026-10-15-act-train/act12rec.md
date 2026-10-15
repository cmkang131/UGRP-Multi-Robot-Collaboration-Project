# ACT12REC — ACT11 rotation-on 기록 파일럿과 비활성 대기열

교사/회복 어댑터는 `1fce11554754d4609470e4fe4b172f9a583bc026`, 격리된 solo 교사는
`6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`로 고정한다. noise는 기존 `act11-noise.json`
(SHA-256 `c5fc20e0dae610afd24f60960dab9b5b9f77ae057719274ae13e12734fa16565`),
`recovery_active_search_v1`, `act8_yaw_gain_v1`(0.6790684337506349),
GCP `ugrp-act-train-1014`의 기존 gcp1 / n4-highcpu-64만 쓴다.
관문 보고는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act11-1fce1155.json`,
SHA-256 `23a982cac22d1655efdd9998dcacbec204876ce1ee5a2c6e471d193df22dc2a4`다.
rotation-on 40/40 및 입력 감사 0/0을 기존 검사기로 원본에 다시 연결한다.
Haiku 독립 재집계는 대기 중이다. 이 작업의 두 DEV 파일럿 권한만 별도 영수증으로 기록하며
대량 기록·학습 승인으로 쓰지 않는다. 대기열의 승인·준비·활성·제출 플래그는 모두 false다.

[계획](act12-record-plan.json)은 새 시드 86820–86869, train45/validation5와
예비 86870–86879(오름차순)다. 관문 시드 및 기존 로컬 큐/계획, 원격 plan/result 메타데이터와
중복을 검사했다. 고정 recorder의 raw split은 train이며 별도 dataset_split이 오프라인
45/5 배정을 정한다. validation은 모델 선택/정규화 학습에 쓰지 않는다.
실패 시 원본·실패 수/전체 시도 분모를 남기고 학습에서 제외한다. 예비 시드는 실패 슬롯의
split을 이어받으며 train/validation 사이를 이동하지 않는다. 성공50 미달 또는
lost→reacquired를 포함한 성공 에피소드20 미달이면 학습 준비가 아니다.

학생 카메라는 기존 robot_cam 640×480, 10Hz, 기존 K/D·화각·장착 그대로다.
기본 off인 `--own-review-only-v1`은 고정 runner의 top 검토 폴더/출력 **두 문장만**
AST로 정확히 제거한다. 나머지 제어/평가 AST는 그대로이며 예상 문장 변경 시 거부한다.
원본/적용 함수 SHA를 `review-policy.json`에 남긴다. teacher·ACT11 소스는 수정하지 않고,
신규 wrapper의 소스 SHA와 실행 중인 교사 SHA를 구분한다. 옵션을 끄면 원래 runner를 호출한다.
학생 원장은 기존 `validate_observation`의 root/rgb/issued 엄격한 허용 목록으로 전수 검사한다.
자기 RGB4장·자기 발행 명령16개·skill/kind/role/destination 번호표·자기 명령 기반 clock와
정렬/출처 메타데이터만 허용한다. 정답 위치·접촉·측정 관절·성공은 학생 필드에서 거부한다.
학습 표적 및 평가는 별도 파일이며 `training_include=false`로 검토를 기다린다.

## 파일럿·저장 예산

두 기록 파일럿은 push 전에 run-first로 실행한다. 최대3라운드, 소유 실행 최대4개,
제출 전 gcp1 전체 실행+예약 ≤40, 메모리 여유≥6GiB를 원격 잠금 아래 확인한다.
budget-stop ACTIVE/최근 순비용 메시지, 8h STOP/idle20분을 확인하며 가드 발동 시 신규 제출을 막는다.
원본은 GCP 영속 디스크에 유지하고 Mac에는 가벼운 원장/해시와 선택한 자기 RGB만 회수한다.
초기 예산은 실행당256MiB×60=15GiB, 다른 승인 작업 예약128GiB와 source3GiB,
GCP 바닥8GiB를 함께 계산한다. 파일럿 실측 뒤 보수적 실행당 예약을 다시 산출한다.
실측·원본 위치·해시는 후속 `act12rec-summary.json`에 기록한다.

## 기록 완료 뒤 채울 학습 초안 칸

`20261015-act-train-ready-9dc44d90.json`은 수정하지 않는다. 기록이 끝난 뒤 채울 항목은
데이터 실제 경로, manifest SHA-256와 전체 파일 해시/전송 영수증, 독립 검토를 마친 rotation-on
관문 영수증(교사·noise·호스트·카메라·회전 설정 포함), 성공50/시도분모와45/5 배정,
회복 구간 포함 성공 에피소드 수(≥20), 기록/학생 입력 감사·6장 이상 영상 검토 영수증이다.
새 데이터로 matching smoke도 다시 필요하다. 기존 GPU 경로는 [ACTGPU1 L4 시험](actgpu1.md)과
[해시 기록](actgpu1-summary.json)만 참조하며 이번 작업에서 GPU를 시작하지 않는다.
기존 데이터·다른 호스트·머신·교사/회전 설정의 결과는 합산하지 않는다.
