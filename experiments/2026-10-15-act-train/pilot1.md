# ACT 학생 첫 파일럿 준비 — 2026-10-15

상태: **solo 본 학습 1회(총10,000 step) + 보류5 + 새 seed10 폐루프 평가 승인, 운영 큐 준비**.
목적은 학습·폐루프 연결 확인이며 최종 모델이 아니다. 이후 빔·상자·내려놓기 데이터를
합치는 학습은 별도 단계다. `gate_promotion_authorized_if_all_conditions_pass=false`를 유지한다.
이 작업의 기준 HEAD는 `8c4490ba3145f673f24944f405ccc0fea38e9efd`, PR은 #504다.
실행 소스는 새 큐의 전체 `source_sha`로 고정한다. 원격 접속·실행·VM 상태 재확인은 하지 않았다.

기존 `7caf9944` smoke는 운영 워커·조정자 보고상 완료했다. 변환50 에피소드/17,851행,
train45·보류5, 입력 감사0/0, grasp done50/50·release done0/50이다. 300 step에82.415초,
loss2.82619, 가중치 재로딩 통과, 보류5의 grasp done 검출0/40이다(중복 horizon 분모).
원본 보고는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act-smoke-7caf9944.json`,
SHA-256 `bc93bb38946030fe644af52c4bd100155048706ad9f15d595dba37af43ff85f0`.
현재 로컬 파일은 `parse_constant`로 비표준 수를 거부해도 읽혀 119행 오류를 재현하지 못했다.
원본은 보존했다. [준비·검증 기록](main-eval-preparation-summary.json)에 범위를 남겼다.

학생 계약은 PR #502 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`에 맞췄고
기준 main은 `c72a2b50628e549fee8032378f4c7cf709fe688c`다. 교사/장면 소스를 추가 병합하지 않았다.
기존 smoke는 이전 라벨의 결과이며 새 데이터·모델과 합산하지 않는다.

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
  나머지는 padding한다. timeout·실패 done은 계속 거부한다. 프로토콜 옵션이 없으면
  `done_label=teacher_v1`로 교사 done을 그대로 쓴다. 이번 프로토콜은 아래 조정자
  결정에 따라 `done_label=last_local_row_v1`을 명시한다.
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

수정 전 Mac 샘플 정적 변환 결과는 [local-audit.json](local-audit.json)에 원본·파생 해시와 함께 있다.

| seed | 전체 행 | 사용 행 | 참조 원본 영상 | grasp done | release done |
|---|---:|---:|---:|---:|---:|
| 86000 | 430 | 344 | 351 | 1 | 0 |
| 86001 | 464 | 375 | 385 | 1 | 0 |

수정 전에는 둘 다 release 완료가 제외된 inspection 구간에 있어 놓기 완료의 양성 표적이
없었다. 이는 실행 실패 진단이 아니라 표적 구성 확인이다. 실제 샘플 plan의 scenario ID는 `_v4`이며,
`v6`은 학생 계약 버전이다. 장면을 임의로 v6 시나리오로 치환하지 않았다.

### 완료 표적 프로토콜 수정 — 2026-10-15

조정자 결정: 각 grasp/release 스킬 구간의 마지막 `local_skill_sample is True` 행을
완료 양성으로 삼는다(release는 backoff 끝). 변환기에서만 새 라벨 사본을 만들고
교사 원본은 바꾸지 않는다. 선택에는 스킬·actor/episode/task 표시와 행 순서만 쓰며
정답 위치·접촉·평가 성공을 쓰지 않는다. 시간 간격·제외 구간은 청크 경계로 유지하지만
추가 done을 만들지 않는다. 같은 스킬이 다른 스킬 뒤에 반복되면 별도 구간으로 센다.
파생 done의 `terminal_reason=command_sequence_complete`는 표적 계약용 표시이며
물리 성공이나 RGB 완료 확인을 뜻하지 않는다.

| seed | 사용 행 | grasp done | release done | release 양성 행 / SIM초 | 제외 inspection 행 |
|---|---:|---:|---:|---|---:|
| 86000 | 344 | 1 | 1 | `train-86000:350:r1` / 36.3 | 79 |
| 86001 | 375 | 1 | 1 | `train-86001:384:r1` / 39.7 | 79 |

[새 샘플 감사](local-audit-last-local-row-v1.json)와 [검증 요약](done-label-v1-summary.json)에
원본·파생 해시를 보존했다. 두 release 양성은 모두 `backoff → lookaround` 행이다.
전체 894행 중 기존과 같은 719행만 사용하고 175행을 제외했다(inspection 158행 포함).
교사 원본 해시·학생 상태·done 외 행동 채널·padding·영상 index·영상 바이트는 수정 전과
같다. 입력 누설 검사 0/0, 제외 행의 정답 필드 주입 거부, 교사 부가 필드를 제거해도
표적 동일, 부분 데이터의 학습 거부를 확인했다. 이 두 샘플의 표적 수정만 검증했으며
전체 50개와 학생의 실제 놓기 완료 성능은 미검증이다.

완료 표적 수정 당시 프로토콜 SHA-256: `99a0ba8557120b75a786d92a5808926abdcbb7a9aa82529d4d60dca5f2230af2`
(새 폐루프 목록을 추가한 현재 프로토콜 해시는 새 큐에 별도 고정).
본 학습 전에 새 소스·프로토콜로 전체 50개를 다시 변환해 skill별 count/done/missing_done을
확인해야 한다. 기존 소스 smoke 결과와 새 표적 결과를 합산하지 않는다.

## 요약 JSON 저장

`harness.grasp_act_data.write_summary`는 중첩 dict/list/tuple 및 NumPy 수치의
NaN/±Infinity를 `null`로 바꾼 사본을 만든 뒤 `allow_nan=False`로 원자 저장한다.
학습·보류 평가·학생 실행 요약에 적용했다. 입력·표적·config·adapter는 계속 엄격한
`write_json`과 유한값 검사를 써서 잘못된 제어값을 허용하지 않는다. 운영 집계 요약도
이 함수를 사용한다. 분모가 없는 done precision/recall은 `null`이다.
[Python 공식 JSON 문서](https://docs.python.org/3/library/json.html#infinite-and-nan-number-values)는
기본 NaN/Infinity 처리가 표준 JSON 범위를 벗어나고 `allow_nan=False`가 이를 거부함을 설명한다.
이번 null 변환은 보고 지표의 결측 표현이며 실패를 성공으로 바꾸지 않는다.

## GCP 운영 워커 전달

```sh
python3 -m scripts.queue_grasp_act_pilot --mode main-eval \
  --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

커밋한 깨끗한 소스에서 `20261015-act-train-<SHA8>.json`을 새로 만든다. 이전 `7caf9944`
큐와 원본·산출물은 보존한다. `coordinator_approval`은 `approved=true`, `stage=main+eval`,
`steps=10000`, RGB main 1회다. 기존 blank-image 별도 학습은 **비활성 유지**한다.
데이터 확대 전 필요한 대조군 계획은 남겨 두며 이번 승인에 추가하지 않는다.

서울 `asia-northeast3-a`의 기존 `ugrp-act-l4-pilot1`(g2-standard-4, L4 1장, 100 GB
pd-balanced 부팅 디스크)을 재시작·재사용한다. TERMINATED·디스크/데이터 보존은 전달받은
상태이며 운영자가 현재 상태를 확인한다. 새 VM·snapshot·데이터 디스크를 만들지 않는다.
`/mnt/act-source/home/ugrp/ugrp-sim/runs`의 기존50개 기록을 쓰고, 새 산출물은
`/mnt/act-source/act-main-<SHA8>/`에 둔다. 저장 공간40 GiB 이상·원본 파일 해시를 확인한다.
원본 tar는 `gs://ugrp-act-train-1014-runs/solo-record-6f057f7e/solo-record-6f057f7e-milestone.tar`,
SHA-256 `2917caf7ff8c8c4a429a5b840ac2223c6d4c784eaa95e0e99a11267ea64b00f8`다.
기존 보고의 RUN_META100개 차이는 문서화된 milestone-update manifest와 대조하며 다른 차이는 중단한다.

순서: 전체 재변환 → 새300-step smoke → offline-smoke → RGB main 총10,000 step →
보류5 offline-main → gcp1 새10 seed 폐루프다. 변환 manifest에서 스킬별50개 에피소드,
각 에피소드 done1개, 합계 grasp50/50·release50/50, missing_done0, 입력 감사0/0를
확인한 뒤만 진행한다. 새 소스·manifest·정규화가 달라 **옛 smoke 가중치는 resume하지 않는다**.
새 smoke step300에서 main을 이어 총10,000 step으로 끝낸다(추가10,000이 아님).

개별 trainer 승인 파일의 `stage=main`은 기존 검증 계약대로 유지한다. 운영자는 큐의
명시적 `main+eval` 승인에 따라 새 source SHA·dataset manifest SHA·새 smoke summary SHA를
정확히 채워 `/approvals/main.json`을 만든다. 이 범위의 추가 조정자 승인은 필요 없다.
AdamW1e-5/backbone1e-5, weight decay1e-4, batch8, KL10, clip1, chunk8/8,
ImageNet ResNet18 미세조정과 시간 앙상블off는 위 조사 근거·고정 upstream을 유지한다.
보류 오차로 체크포인트를 선택하지 않고 고정 step10,000을 쓴다. 500 step마다
모델·optimizer·RNG를 보존하며 체크포인트 전체 파일 SHA-256·재로딩을 확인한다.

모든 gcloud 명령은 `--project=ugrp-act-train-1014`를 붙인다. 잔여 크레딧·budget-stop을
확인하고 발동 시 정지·보고한다. 8h STOP·유휴1200초를 유지하고 키를 저장하지 않는다.
각 단계 뒤 요약·해시를 회수하고 해당 VM을 정지해 `TERMINATED`를 실제 확인·기록한다.
다음 단계는 같은 VM을 재시작한다. 폐루프 후에는 소유 작업을 확인한 gcp1과 학습 VM 모두
정지를 확인한다. 다른 작업이 있으면 운영자가 조정하고 상태 미확인을 완료로 보고하지 않는다.

[가격 기록](pricing.json)의 $0.907714004/시간은 2026-10-15에 수집한 추정이다.
현재 가격·실제 크레딧·디스크/네트워크·세금은 이 작업에서 조회하지 않았으며 운영자가 실행 전
확인한다. 비용이 없다고 가정하지 않는다.

## 평가 실행 경로와 성공 기준

오프라인은 86045–86049 보류5개다. 행동 MAE(바퀴·pulse-width·PWM·투영 후 명령)와
완료 TP/FP/FN·양성/음성/예측 양성 분모·precision/recall을 seed/skill/task별 기록한다.
`first_action_by_skill`은 고유 timestep이고 `by_skill`의 all-horizons는 중복 청크다.
padding은 제외하며 분모0은 null이다. 행동 적합도를 폐루프 물리 성공으로 해석하지 않는다.

폐루프는 `closed-loop-main-plans/91100..91109.json`의 새10개 제안이다. BOX_KINDS는
cyan3·red3·green2·yellow2로, 10이4로 나뉘지 않아 최대 차이를1로 했다. 정적 설정으로만
만든 근거리 시작이며 원격 seed 재고·정적 충돌·실제 가시성은 운영자가 확인한다. 기존20개
cyan 집기 전용 계획은 재생용 보존한다. 새 계획은 작은 상자의 집기→들기→pickup_site 놓기
부품 평가이며 지도 주행·운반 경로·협력·연구 관문 승격을 주장하지 않는다.

표준 workflow `grasp-act-student-pilot` 1.1.0을 쓴다. 최종 actor의 config/adapter/weights/
SHA256.json을 gcp1에 복사해 전체 해시·CPU 로딩을 확인하고 기존 격리 CPU worker를
stdin/stdout으로 연결한다. 별도 네트워크 추론 서버는 만들지 않는다. 추론 청크당
n·median·p95 지연과 wall/SIM을 남긴다. 동시1의 첫 실행30 SIM초 원본·입력 감사0/0·
명령과 실측 속도를 확인한 뒤 나머지를 낸다. gcp1 실측 기준을 쓰고 Azure 속도 수치를 전용하지 않는다.

ACT는 grasp 명령을 받고, **학생 done→고정3.1초 대기→ACT release 명령→학생 done→고정3.1초**
순서로만 전환한다. 코드에 손 파지 경로·교사·정답 보정은 없다. 평가 정답은 분리된
`eval-only.jsonl`과 채점에만 쓴다. 들기 성공은 바닥 여유≥12mm·기울기≤10°·두 손가락
각≥0.5N을3 SIM초 유지한 경우다. 놓기는 release 지시 뒤 바닥 여유−5..6mm·기울기≤10°·
각 손가락<0.1N·선속도≤0.02m/s를3 SIM초 유지한 경우다. 두 조건을 순서대로 만족하고 관측된 낙하가 없어야
`physical_success=true`다. 들기 후 여유>12mm에서 양손가락 모두<0.1N이면 낙하 실패를
고정하며 이후 바닥에서 안정돼도 성공으로 바꾸지 않는다. 10Hz 표본 사이의 낙하는 놓칠 수
있으므로 영상에서 발견한 낙하도 실패로 기록한다. 기존 집기 전용 성공과 합산하지 않는다. 선속도는 [MuJoCo mj_objectVelocity 공식 API](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-objectvelocity)의
회전/병진6D 출력 중 병진 성분을 평가에만 사용한다. RGB 완료 확인은 계속 unknown이다.

10개 전체·색별 n/N, done 요청과 물리 성공, 실패 사유 분포·HOST_ERROR·미회수 상태를
각각 남긴다. 실제 실패 원인 판단 전 최소6장·60 SIM초마다1장 이상 영상을 보고 범위를
기록한다. 결함이 확인되면 같은 결함의 소유 실행·대기를 즉시 멈추고 원본을 보존한다.

## 검증 범위와 산출물 보존

이번 수정은 **25 passed / 2파일**(0.30초)로 JSON 비유한값의 null 저장·엄격 입력 거부,
done 분모/precision/recall, 승인·새 경로·10개 계획, 학생 명령만 쓰는 전환과
들기 뒤 안정 놓기 채점을 확인했다. [준비 요약](main-eval-preparation-summary.json)에 JUnit
경로·해시와 보고 원본을 남겼다. Mac 물리·렌더·학습·원격 접속은0이다.
기존 완료 표적 샘플 시험36개와 데이터 정적 감사는 이전 기록 범위 그대로다.
전체50개 새 변환, GPU 학습·보류 평가, 실제 폐루프·CPU 지연·현재 VM 정지는
**아직 검증하지 않았고 운영자가 수행할 일**이다. 순수 시험 통과를 이 결과로 확대하지 않는다.

실패/HOST_ERROR를 포함한 모든 요약은 표준 JSON과 원본 경로·해시를 기록한다.
회수·전체 hash·가중치 로딩을 확인하기 전에는 모델 보존/배포 완료로 표시하지 않는다.
선택 모델과 보고한 비교/실패 모델을 versioned GitHub Release asset으로 보존하고
`configs/model_artifacts.json`에 URL·크기·SHA·검증 범위를 기록한다. 재다운로드·전체
hash·로딩까지 확인한다. 원본·옛 큐·옛 체크포인트는 삭제하거나 덮어쓰지 않는다.
[모델 배포 규칙](../../docs/model_artifacts.md).

## 운영 참고 자료

- [실행 구조 결정](../../docs/act_execution_decisions.md), [GCP 운영](../../docs/gcp_simulation.md).
- [GPU 머신 규격](https://docs.cloud.google.com/compute/docs/gpus/).
- [VM 실행시간 상한](https://cloud.google.com/compute/docs/instances/limit-vm-runtime).
- [기존 디스크 snapshot 생성](https://cloud.google.com/compute/docs/disks/create-snapshots).
