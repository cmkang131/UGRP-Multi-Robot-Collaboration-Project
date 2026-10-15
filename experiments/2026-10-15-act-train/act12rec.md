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

## GCP 파일럿 결과 — push 전 직접 실행, 1라운드

[전체 수치·실행 argv·원본 위치·해시](act12rec-summary.json),
[시험·비활성 대기열 검사](act12rec-verification.json).

| seed | 원본 성공 | RGB/학생 행 | 디스크 할당 | 파일 논리 크기 | 첫30 wall/SIM | 회복 성공 구간 |
|---|---:|---:|---:|---:|---:|---:|
| 86820 | 1/1 | 460/460 | 7,876,608 B (7.512 MiB) | 6,804,819 B | 2.695 | 1 |
| 86821 | 1/1 | 460/460 | 8,093,696 B (7.719 MiB) | 6,967,568 B | 2.742 | 1 |

원본 result 재집계 **2/2**, 실패0·HOST_ERROR0·재시도0. 각각45.9 SIM초,
학습용 RGB 합920장/학생920행. JPEG 전부640×480이고 기록 간격은0.1초(허용 오차 .002초 이내)다.
카메라 전체 K/D·FOV·장착·source hash는 고정 solo camera_config와 정확히 같고,
실제 MuJoCo 카메라 pos/quat/resolution도 일치했다(intrinsic float32 오차<1e-4).
학생 root·rgb·issued 필드 전수 strict allowlist 통과, 금지 필드0. 두 InputAudit 모두
`invisible_measurements=0`, `held_world_reads=0`. 평가/표적은 분리되며
`training_include=false`다. 이는 교사 기록 결과이며 ACT 학생 성공이 아니다.

각 실행의 처음·중간·끝/접근9장과 회복6장, **15장씩 총30장**의 자기 카메라를 직접 봤다.
첫 묶음의 절대 SIM시각은1.3/2.0/8.2/10.5/14.4/19.7/28.8/38.0/47.2초다
(result의 경과 SIM초와 origin1.3초 차이). 접근·정렬에서 담당 청록/빨강 상자가 보였고,
86820은3.7/4.1/4.4/5.2/5.3/5.8초, 86821은3.7/4.2/4.5/5.3/5.4/5.9초에서
주입 회전 전 가시→화면 밖→재가시를 확인했다. 원장 기준 lost/reacquired는 각각
4.1→5.3초, 4.2→5.4초이며 성공 회복 에피소드는 **2/2**다. 고정 카메라의 들기/보유
구간에서는 물체가 보이지 않았고, 완료 꼬리에서는 화면 아래 가장자리에 놓인 상자가 보인다.
접근 중 전 구간 가시를 주장하지 않는다. top 출력 파일은0개다.

검토 이미지·모든 원본/회수 해시·입력 감사는
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/act12rec-1fce1155/`에 있다.
원본은 `gcp1:/home/ugrp/ugrp-sim/runs/act12-record-{86820,86821}-1fce1155`,
Mac lite는 `outputs/gcp1-runs/` 아래 같은 실행 이름이다. VM에서 전체 SHA256SUMS,
Mac lite/선택 RGB의 각 해시를 확인했다. 원본 전체의 독립 백업은 아니다.

제출 시 전체 실행+예약13/3개, 소유 실행1/2개로 상한40/4를 지켰다.
budget-stop ACTIVE, 최근 순비용 메시지0 KRW, 8h STOP·idle20분 유지.
잔여 크레딧·실청구는 미확인이다. 완료한 이 작업의 프로세스·임대·예약은 각각0개이며,
공유 gcp1에는 다른 시뮬레이션3개가 있어 정지하지 않았다.

실측 최대8,093,696B를60회로 단순 외삽하면 **463.125MiB**(성공50회385.938MiB)다.
긴 시드의 증가를 고려해 실행당256MiB,60회 **15GiB**를 계속 예약한다.
다른 승인 작업128GiB+source3GiB+기록15GiB를 빼면 종료 당시168GiB 가용 공간 중
**21.71GiB**가 남아 바닥8GiB를 충족했다. Mac은71.88GiB에서 lite예약4.25GiB를 빼도
바닥20GiB를 충족한다. 실제 배치 활성화 전에는 다른 작업 잔여 쓰기와 여유를 다시 잰다.

비활성 대기열:
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act12-record-da4727b6.json`
(SHA-256 `3be895a07fc02a7b5b21670ecdfc9bc240060d7bcfb8965ab7d5a5dd4fb7d28c`).
교사 SHA는1fce1155, 기록 wrapper는실제 실행한da4727b6로 각각 고정했다.
파일럿2의 실제 argv를 그대로 보존하고 나머지48·예비10을 연결했다. max_parallel16,
전역40이며 승인/활성/준비/제출/자동 승격 플래그는 전부false, training_rgb만true다.
Haiku 독립 재집계와 별도 bulk 관문 영수증 전에는 실행하지 않는다.
기존 학습 초안 SHA-256은 전후
`05818f4223b19aa0a77c147c62400badaa4d2aa7cc031232b5a683b01adfd2a0`로 동일하다.

## 재현 명령

관련 오프라인 시험(단일 pytest 프로세스, 물리/렌더 없음):

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_grasp_act_act12_record.py tests/test_grasp_act_data.py
```

실제로 제출한 첫 파일럿 명령(같은 이름은 덮어쓰지 않고 거부한다):

```sh
python3 scripts/remote_run.py --host gcp1 --detach --class dev --pr 504 --per-run-mb 256 /Users/changmin/projects/ugrp-wt/act-train act12-record-86820-1fce1155 -- bash -c 'cd /home/ugrp/ugrp-sim/src/1fce11554754d4609470e4fe4b172f9a583bc026 && exec /home/ugrp/ugrp-sim/src/1fce11554754d4609470e4fe4b172f9a583bc026/.venv-sim/bin/python /home/ugrp/ugrp-sim/src/da4727b69b71ccbeae68850a516ce010ac1c657b/scripts/run_grasp_act_act12_record.py --teacher-source /home/ugrp/ugrp-sim/src/1fce11554754d4609470e4fe4b172f9a583bc026 --own-review-only-v1 -- --plan /home/ugrp/ugrp-sim/act12rec-1fce1155/act12-record-plan.json --episode 0 --dependency-root /home/ugrp/ugrp-deps/solo-teacher-6f057f7e --noise experiments/2026-10-15-act-train/act11-noise.json --recovery-mode recovery_active_search_v1 --rotation-calibration act8_yaw_gain_v1 --training-rgb --gate-receipt /home/ugrp/ugrp-sim/act12rec-1fce1155/pilot-gate-receipt.json --cap-s 90 --out /home/ugrp/ugrp-sim/runs/act12-record-86820-1fce1155/raw'
```

두 번째는 seed86821·episode1이다. 재실행에는 새 run 이름과 out을 일치시키고
실시간 예산/동시 실행 수를 다시 확인한다.
저장된 GCP 원본의 학생 입력 재감사(기존 da4727b6 source 안에서 실행, 시뮬레이션 없음):

```sh
.venv-sim/bin/python -m scripts.audit_grasp_act_recording --raw /home/ugrp/ugrp-sim/runs/act12-record-86820-1fce1155/raw --output /home/ugrp/ugrp-sim/act12rec-1fce1155/86820-reaudit.json
```

큐 재생성은 새 출력 디렉터리에서만 수행하며 기존 큐는 덮어쓰지 않는다:

```sh
python3 -m scripts.queue_grasp_act_act12_record --pilot-summary experiments/2026-10-15-act-train/act12rec-summary.json --output-dir /tmp/act12-queue-recheck
```

관련 시험26 passed. 원격 실행은 push 전에 완료했다. 남은 작업은 독립 관문 재집계 확인과
나머지 기록/성공50·회복20 확인, 데이터 전송/manifest·기록 검토 영수증이다. 이전 결과와 합산하지 않는다.
