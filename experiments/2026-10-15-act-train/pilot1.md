# ACT 학생 첫 파일럿 준비 — 2026-10-15

상태: **오프라인 파이프라인 준비, GCP 실행 전**. `claude/act-train`에서
PR #502의 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`에 맞춘 학생 계약만
가져왔다(파일 SHA-256 `6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056`).
교사/장면 소스는 병합하지 않았다. 기준 main은 `c72a2b50628e549fee8032378f4c7cf709fe688c`.
실행 소스의 전체 SHA는 커밋 후 생성하는 대기열에 고정한다.

50/50 기록의 조정자 승인과 86045–86049 보류는 이번 사용자 지시를 근거로 한다.
교사 성공률을 여기서 재측정하지 않았다. 원본 result의 `data_admitted=false` 등을
고쳐 쓰지 않고 별도 protocol에 승인 근거를 남겼다.

## 참고 자료와 선택

| 항목 | 원 논문 / 고정 LeRobot | 이번 파일럿 |
|---|---|---|
| 청크 | 논문 100, 50 Hz; LeRobot chunk/n_action_steps 100 | 계약에 맞춘 8 / 8, 10 Hz = 0.8 SIM초 |
| KL | β=10; LeRobot `kl_weight=10` | 10, CVAE 사용, 추론 z=0 |
| 시간 앙상블 | 논문 중첩 청크 가중 평균; LeRobot 기본 None, 선택 시 0.01·매 tick 추론 | off; CPU 부하와 0.8초 계약을 우선. 변경 시 별도 프로필 |
| 영상 | 논문 640×480 RGB·ResNet-18; LeRobot ImageNet ResNet-18 | 각 이력 프레임 320×240, 비율 보존 bilinear, crop 없음 |
| 모델 입력 영상 | 원 논문은 여러 카메라 | 자기 카메라 이력 4장을 `[5.2s,1.5s;0.5s,현재]` 2×2로 묶은 640×480 한 장 |
| Transformer | 논문 enc4/dec7, dim512/FF3200/heads8; LeRobot dec1 | 고정 LeRobot 기본 구조 그대로, dec1 |
| 학습률·배치 | 논문 1e-5·8, LeRobot LR/backbone LR 1e-5 | AdamW 1e-5, weight decay 1e-4, batch8, grad norm1 |
| 학습량 | 실물 작업별 50 시연; LeRobot 안내는 100k step 예시 | 45 train + 5 보류; 300 smoke → 승인 → 총 10,000 step 후보 |

논문 IV-C·부록 D 표 III를 읽었다. 수십 시연이 출발점이라는 근거이며 우리 시뮬레이션
성공률의 보장이 아니다. [Zhao et al., ACT/ALOHA (2023)](https://arxiv.org/html/2304.13705v1).
고정 LeRobot의 decoder 1은 원 구현의 첫 decoder 층만 쓰는 동작과 맞춘 선택이다.
[고정 ACTConfig](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/configuration_act.py).
배치 8·단일 GPU 소규모 시작 안내도 확인했다.
[LeRobot ACT 공식 안내](https://huggingface.co/docs/lerobot/act).

320×240은 논문에서 최적이라고 검증한 값이 아니다. 원본의 절반으로 줄여 영상 이력
네 장을 논문 한 장 크기로 유지하는 **파일럿 설계값**이다. 세부 파지 단서 손실은
새 시작 상태에서 검증해야 한다. 고정 upstream은 카메라마다 같은 위치 인코딩을
반복하므로, 이력 네 장을 단순히 다른 카메라 key로 넣으면 순서를 구별하지 못한다.
2×2 고정 배치가 lag 순서를 공간 위치로 구별한다. 테스트에서 순서 반전·blank 입력을
확인한다. [고정 ACT 영상 토큰 구현](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py).

`requirements-reference-act.txt`의 LeRobot SHA와 PyTorch 의존성을 그대로 사용한다.
새 학습 프레임워크를 추가하지 않았다. 기존 `harness/act_training.py`의 activation
checkpoint 도구를 재사용한다. ResNet은 ImageNet 초기화 후 미세조정하고, frozen
feature cache와 기존 다른 작업용 sampling/metric은 사용하지 않는다.

## 데이터와 누설 경계

- 원본: gcp1 `/home/ugrp/ugrp-sim/runs/solo-record-860{00..49}-6f057f7e/raw/`.
- 학습 seed 86000–86044, 보류 86045–86049. 원본 plan의 `split=train`보다 이번 protocol이 우선한다.
- `student-<robot_id>.jsonl[.zst]`와 teacher의 sample ID·시각·skill·kind를 정합한다.
  행동 표적은 `clean_teacher_command`, 행 선택은 `local_skill_sample is True`만 쓴다.
- 제외 행, 시간 간격, episode/robot/skill/kind/role/destination 변경, done에서 청크를 끊고
  나머지는 padding한다. timeout·제외 구간의 done을 새 표적으로 만들지 않는다.
- 모든 학생 행은 중첩 허용 목록을 검사한다. 정답 위치·접촉·측정 관절·자유 문장·타 로봇
  영상 key를 거부한다. actor 입력은 `observation.images.own_history`와
  `observation.state`뿐이다. 후자는 측정 상태가 아니라 자기 발행 명령 16개와 계약의
  번호표·명령 시계다. robot_id/sample_id/seed는 텐서에 넣지 않는다.
- 청크 중복·padding을 제외한 **학습 seed의 선택된 timestep만** 정규화 통계에 사용한다.
  이산 번호표는 그대로 두고 명령/시계 성분과 표적을 정규화한다. 보류 데이터는 fit에
  들어가지 않는다. 배포 adapter에 통계·계약 SHA·영상 순서·출처를 함께 저장한다.
- 원본 JPEG는 640×480/10 Hz 및 SHA를 확인하고 원본 파일을 수정하지 않는다.
  K/D/mount와 contract hash가 다른 기록을 합치지 않는다. 일반 loader는 r1/r2/r3,
  모든 계약 kind/role/skill을 지원한다. 새로운 교사 코호트 합산은 별도 데이터 승인이 필요하다.
- 변환 산출물은 uint8 NPY 영상, NPZ 상태·청크·mask·영상 index, 별도 sample metadata,
  원본/산출물 해시, train-only normalization, JSON manifest다. 모두 `milestone`으로 보존한다.
  부분 변환 결과는 학습 loader가 거부한다.

Mac 샘플 정적 변환 결과는 [local-audit.json](local-audit.json)에 원본·파생 해시와 함께 있다.

| seed | 전체 행 | 사용 행 | 참조 원본 영상 | grasp done | release done |
|---|---:|---:|---:|---:|---:|
| 86000 | 430 | 344 | 351 | 1 | 0 |
| 86001 | 464 | 375 | 385 | 1 | 0 |

둘 다 release 완료가 제외된 inspection 구간에 있다. 이는 실행 실패 진단이 아니라
표적 구성 확인이다. **놓기 완료를 배우는 양성 표적이 이 두 샘플에는 없다.** 전체 50개
변환 시 skill별 count/done/missing_done을 확인하고 조정자가 본 학습 전에 판단한다.
진행 중에 임의로 라벨을 바꾸지 않는다. 또한 실제 샘플 plan의 scenario ID는 `_v4`이며,
`v6`은 학생 계약 버전이다. 장면을 임의로 v6 시나리오로 치환하지 않았다.

## GCP 운영 워커 전달

대기열 생성(로컬 JSON 작성만):

```sh
python3 -m scripts.queue_grasp_act_pilot \
  --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

파일명 `20261015-act-train-<SHA8>.json`, `gate_promotion_authorized_if_all_conditions_pass=false`.
convert/smoke만 운영 사전 점검 뒤 가능하고 main·폐루프·blank 학습은 비활성이다.

계획 머신은 서울 `asia-northeast3-a`, `g2-standard-4`, L4 1장(24 GiB), 4 vCPU/16 GiB.
부팅 pd-balanced 60 GiB + 데이터 pd-balanced 250 GiB. 원본 gcp1 디스크의 snapshot을
같은 프로젝트 `ugrp-act-train-1014`에 만들고 데이터 디스크로 복원한다. `/mnt/act-source`
아래 원본 runs는 보존하며, 새 결과는 `/mnt/act-source/act-pilot1/`에 둔다. source disk명과
snapshot ID는 아직 조회하지 않았고 운영 워커가 기록한다. 완료된 원본의 해시가 변하지
않는 시점에 복제하고, source/복제본의 `SHA256SUMS` 전부를 맞춘 뒤에만 변환한다.
공개 dataset 업로드·VM에 SSH 개인키/모델키 저장은 없다.

운영 워커의 모든 gcloud 명령은 `--project=ugrp-act-train-1014`를 포함한다.
VM 생성에 `--max-run-duration=8h --instance-termination-action=STOP --no-service-account
--no-scopes`를 유지한다. 기존 budget-stop을 변경하지 않고 잔여 크레딧·활성 경보를
확인한다. 발동하면 정지·보고하며 다른 호스트로 넘기지 않는다. 이번 소스의
`gcp_idle_guard_startup.sh`는 새 학습/변환/평가 프로세스도 작업으로 인식하며 유휴
20분 종료를 유지한다. 운영 워커가 설치·timer 활성 상태를 검증한다.

추정 디스크 사용: 입력 전체는 미실측; 기록된 22,268 frame 기준 파생 uint8 영상 약
4.8 GiB + 표적/메타데이터 + 체크포인트/optimizer 약 15 GiB 여유. 복원 후 40 GiB 이상
여유를 요구한다. snapshot·정지된 VM 디스크도 비용에 포함한다. 원본 삭제는 하지 않는다.

공식 서울 시간표에서 g2-standard-4 **$0.907714004/시간**을 확인했다(2026-10-15,
[가격 출처](https://cloud.google.com/products/compute/pricing/accelerator-optimized),
[추출 기록](pricing.json)). 300-step smoke는 5–20분 예상, 프로세스 상한 30분으로
계산 비용 최대 약 $0.454. 본 학습 10k step은 **미실측 추정 2–6시간**, 계산 비용
약 $1.82–5.45, VM 8시간 계산 비용 약 $7.26. GPU를 중복 과금해 더하지 않는다.
snapshot/디스크/네트워크·세금·환율·실제 크레딧 잔액은 미확인이다.
[디스크 공식 가격](https://cloud.google.com/compute/disks-image-pricing).

smoke에서 실제 step/s·GPU peak memory·finite loss/gradient·샘플/청크 정합·가중치
재로딩 예측 동일성·5개 보류 seed 행동 오차를 회수한다. 이후 VM은 정지 상태
`TERMINATED`를 확인하고 조정자 승인을 기다린다. main 승인 JSON은 source SHA,
dataset manifest hash, smoke summary hash, 10,000 step, blank 여부에 묶인다.
학습은 고정 마지막 step을 평가하며 보류 오차로 체크포인트를 고르지 않는다.
100-step(smoke)/500-step(main)마다 optimizer·RNG·모델을 저장한다. SIGINT/SIGTERM과
wall cap에서 현재 step을 저장하고 미완료로 기록한다. main은 smoke step300에서 이어서
총10k를 목표로 한다. 8시간 안에 끝나지 않으면 재승인된 다음 세션에서 같은 소스로 잇는다.

## 평가 실행 경로와 성공 기준

오프라인: `scripts.evaluate_grasp_act_offline`은 86045–86049만 열어 첫 명령과 전체
유효 horizon의 wheel MAE, pulse-width 초 MAE, PWM MAE, 투영 후 명령 오차,
완료 양성/음성 분모와 누락/거짓 완료 수를 JSON/JSONL로 저장한다. padding은 제외한다.
완료 양성이 0개이면 recall 성공으로 표시하지 않는다. 모델 선택이나 물리 성공 수치가 아니다.

폐루프: 표준 `sim_cli workflow run grasp-act-student-pilot` →
`scripts.run_grasp_act_student` → 별도 CPU 프로세스 `scripts.grasp_act_student_worker`.
기존 Scene·카메라·stiffness·v7 바퀴 물리 조합을 사용한다. actor에는 world/teacher/IK가
없고 직렬화된 허용 관측과 자기 JPEG만 보낸다. 출력은 wheel/PWM 청크이며 교사·정답
보정·손으로 짠 파지 대체는 없다. 초기 배치만 setup 소유자가 만든다. 영상·명령·평가
파일을 분리하고 입력 허용 목록 위반 시 실행을 거부한다.

초기 계획은 `closed-loop-plans/91050..91069.json`: 같은 학습 지도에서 **cyan의 새로운
근거리 시작 20개**다. seed는 제안 예약이며 운영 워커가 원격 사용 이력과 정적 충돌
검사를 끝내야 한다. 학습/보류 50개와 겹치지 않는다. 0.4–0.8 m 구간에서 시작하는
집기 부품 평가이며 지도 주행 인계·다른 색·새 지도·빔·상자·연속 운반 성공을 뜻하지 않는다.
그 범위 확대는 다음 코호트로 나눈다. 실행 전 CPU 추론이 포함된 첫 30 SIM초,
동시1 속도·관측/명령·입력 감사 0/0를 운영 워커가 확인한다. 오류/실패는 분모에서 빼지 않는다.

집기 물리 성공은 평가 전용 접촉/geometry로 **전체 바닥 여유 ≥12 mm, 기울기 ≤10°,
두 손가락 각각 ≥0.5 N을 3 SIM초 연속 유지**, weld off로 센다. 평가값은 명령·전환에
되돌리지 않는다. 모델 done 이후 고정 3.1초 관측하며 추가 집기 코드는 없다.
RGB 완료 확인기는 아직 연결하지 않아 `completion_confirmation=unknown`,
`skill_completion_success=null`로 둔다. 따라서 성공 lift도 전체 스킬 완료·놓기·E2E 성공으로
승격하지 않는다. 전체 n/N, 실제 완료 요청 n/N, 실패/시간초과/HOST_ERROR, CPU 추론
중앙/p95를 별도로 보고한다. 영상 검토 범위(최소6장, 긴 실행 60초마다)를 기록해야 한다.

화면 사용 점검은 동일 train split·step의 **별도 blank-image 학생**을 학습해 같은 새로운
시작 상태에서 비교한다. 사후에 RGB 학생의 화면만 가리는 실험으로 대신하지 않는다.
n/N 차이가 없으면 데이터 확대 전에 원인을 확인한다. blank 학습은 별도 smoke/승인 대상이다.

## 검증 범위와 산출물 보존

- 최종 시험 **27 passed / 3파일**(pytest 표시 0.44초), Python 문법·idle guard shell 문법·
  diff 검사 통과. 표준 workflow `plan`도 실행하지 않은 명령/입력 해시를 반환했다.
  [검증 요약과 JUnit 해시](summary.json).
- 이번 Mac 검증: 3개 시험 파일의 순수 데이터/계약/명령·승인 경계 시험과 저장 JPEG 변환.
  실제 샘플 2개 719행과 원본 참조 736개 해시 정합. 원격 접속·학습·물리·렌더 실행 0.
- GPU LeRobot forward/backward·메모리·속도·resume, 전체 50개 데이터, 시뮬레이터 actuator
  연결·폐루프 성능은 아직 실행하지 않았다. 테스트 통과를 이 결과들로 확대하지 않는다.
- 각 단계는 running/complete/HOST_ERROR·원본 위치·해시를 summary JSON에 남긴다.
  회수 뒤 로컬 프로젝트 기록과 hash를 갱신한다. 현재 원본 전체의 두 번째 복사본은 미확인이다.
- 모델이 생기면 선택 모델·보고한 비교/실패 모델을 config/adapter/정규화/출처와 묶어 새
  GitHub Release asset으로 보존한다. `configs/model_artifacts.json`에 URL·크기·SHA·검증
  범위를 기록하고 재다운로드·전체 해시·모델 로딩을 확인한다. 현재는 가중치가 없으므로
  배포 완료 항목을 만들지 않았다. [모델 배포 규칙](../../docs/model_artifacts.md).

## 운영 참고 자료

- [실행 구조 결정](../../docs/act_execution_decisions.md), [GCP 운영](../../docs/gcp_simulation.md).
- [GPU 머신 규격](https://docs.cloud.google.com/compute/docs/gpus/).
- [VM 실행시간 상한](https://cloud.google.com/compute/docs/instances/limit-vm-runtime).
- [기존 디스크 snapshot 생성](https://cloud.google.com/compute/docs/disks/create-snapshots).
