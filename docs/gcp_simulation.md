# GCP 시뮬레이션 실행 (2026-10-15)

사용자 요청: "GCP에서 비싼 거나 좋은 거 써서 시뮬레이션 더 빠르게", "GCP 빨리 시간 측정해서 이걸로 넘겨". 현재 실행 프로젝트는 **`ugrp-sim-b-1014`**, 계정은 **`changmin5781@gmail.com`**(gcloud 구성 `ugrp2`)다. 비용 정지된 첫 프로젝트 `ugrp-act-train-1014`의 VM·디스크·원본은 보존하며 시작·생성·삭제하지 않는다. [Azure 실행](azure_simulation.md)은 보조로 남는다.

## 학습·MJWarp VM 실행 시간 상한 제거 (2026-10-16)

사용자 원문: "8시간 상한 — 이건 좀 없애라". L4 등 학습·MJWarp VM은 실행 시간 상한 없음으로 바꾸고, 유휴 20분 종료와 budget-stop은 유지한다. 시뮬레이션 VM gcp1 및 후속 `ugrp-sim-gcp2`의 24시간 상한은 이번 결정 범위 밖으로 유지한다(조정자 해석, 사용자 미확인). 아래 생성 당시의 8시간 설정은 과거 기록이며 이 결정으로 대체한다.

새 VM 생성에서 `max_run_duration` 키가 없거나 JSON `null`이면 `--max-run-duration`과 해당 상한의 `--instance-termination-action=STOP`을 생략한다. 명시한 기존 상한은 그대로 반영한다. 저장된 L4 프로필 `gcp3`의 기본값은 `null`이며, CPU 시뮬레이션 프로필의 `24h`는 유지한다. 실행기도 상한 없는 호스트에는 대기 시한을 두지 않고 임대의 `expected_end_unix`를 `null`로 기록한다. 유한 상한에는 기존 정리 여유 30분을 유지한다. 이 동작은 [공식 생성 옵션](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/create#--max-run-duration)에 따른다.

기존 VM 처리에 관한 조정자 제공 상태: `ugrp-act-l4-gcp3`는 정지 상태에서 상한 제거 완료, 실행 중인 `ugrp-act-l4-gcp2`는 다음 정지 때 제거하는 Mac 감시가 동작 중이다. nocap 작업은 GCP 명령을 실행하지 않으며 이 상태와 감시 완료를 별도로 검증하지 않았다.

## gcp2 이관 결정과 구성

사용자 원문(2026-10-15): "gcp2에서 하면 될 거 같긴해", 이어서 "아니다 별로 빨리 쓰는 거 같지 않아". 이번 작업 지시: "시뮬레이션 호스트를 두 번째 GCP 프로젝트로 옮긴다(속도 우선, 비용 최적화 아님)", "첫 프로젝트는 이제 건드리지 않는다". 배경은 사용자 제공 기록상 22:54 KST 첫 프로젝트의 100% 예산 알림과 gcp1·L4 정지다. 이 작업에서는 첫 프로젝트에 API/SSH 요청을 보내지 않았다.

- 기본 호스트 `gcp2`: `ugrp-sim-gcp2`, `asia-northeast3-a`, `n4-highcpu-64`, STANDARD, 400 GB `hyperdisk-balanced`. 전용 SSH 키는 Mac `~/.ssh/ugrp_gcp2`이고 VM에는 공개키만 둔다.
- **24시간 상한 승계**: 사용자 지시 "gcp1에 적용한 사용자 결정 24h를 후속 시뮬레이션 VM에 승계"에 따라 `--max-run-duration=24h --instance-termination-action=STOP`. 유휴 20분 종료와 budget-stop은 유지한다. `--no-service-account --no-scopes`, 프로젝트 SSH 키 차단을 고정한다.
- 호스트별 계정·프로젝트·zone·머신·디스크·키는 `configs/gcp_hosts.json`에서 읽는다. 다른 설정은 `UGRP_GCP_CONFIG=/절대경로/설정.json`으로 선택한다. 모든 gcloud 호출은 대상의 `--account`와 `--project`를 명시한다. gcp1 설정과 결과 경로는 재생·조회용으로 보존하고 생명주기 변경은 `lifecycle_enabled=false`로 거부한다(`--force`도 우회 불가).
- 디스크는 속도 우선과 기존 400 GB 수용량을 유지한다. 첫 프로젝트 원본은 옮기지 않는다. OS/환경 30 GB, 공용 Git 2 GB, 소스 100개×실측 약1.3 GB, 동시24 실행 24 GB, 보관/후속164 GB, 여유50 GB의 **계획 배분**이다. 실측 사용량과 해시는 [gcp2setup 기록](../experiments/2026-10-15-gcp2setup/README.md)에 남긴다.
- 기본 Ubuntu 24.04 이미지에서 `docs/ubuntu_quickstart.md`와 같은 apt/Python venv 절차 및 `requirements-sim.txt`를 썼다. 환경·전이 의존성 전체는 `evidence/environment-initial.txt`에 남긴다. 저장된 gcp1 환경과 Python·MuJoCo·NumPy·OpenCV·Pillow를 대조한다. gcp1 전체 pip freeze가 없어 나머지 패키지 전체의 동일성까지 주장하지 않는다.
- 소스는 `/home/ugrp/ugrp-sim/git-shared.git`에 한 번 수입하고 모든 사본은 `git clone --reference /home/ugrp/ugrp-sim/git-shared.git --no-local ...`로 만든다. 다른 사본을 참조하지 않는다. 공용 저장소는 **삭제·gc/prune 금지**이며 자동 gc/maintenance를 끈다. Mac은 커밋된 Git 객체만 전송하고 모델 키·Kaggle·에이전트 자격 증명을 전송하지 않는다.

## 비용 정지 장치 시험

순비용(크레딧 포함) 1,000 KRW 예산 → gcp2 `budget-stop` 토픽 → ACTIVE 함수 `stop_on_budget`. 함수의 `TARGET_PROJECT=ugrp-sim-b-1014`와 서비스 계정의 `roles/compute.instanceAdmin.v1`을 확인했다. 코드가 모든 zone을 순회해 RUNNING/PROVISIONING/STAGING 인스턴스를 정지한다. 기존 장치는 변경하지 않았다.

가장 작은 시험용 `e2-micro`(10 GB, 서비스 계정/권한 없음, 시험 자체의 10분 STOP 상한)에 `costAmount=budgetAmount=1000` 수동 발행: RUNNING → **9.019초 STOPPING → 55.517초 TERMINATED**. 함수 로그에 시험 VM의 `stop_all`이 있다. 이후 시험 VM과 부팅 디스크를 삭제했고 둘 다 목록 0임을 확인한 뒤 본 VM을 생성했다. 이 시험은 Pub/Sub 이후 동작의 실증이며 실제 청구 집계 지연을 검증하지 않는다. 예산 집계는 지연되고 VM 외 디스크/네트워크 비용은 계속될 수 있다. 원본 설정·코드·상태 시계열은 [시험 근거](../experiments/2026-10-15-gcp2setup/evidence/)에 있다.

## gcp3 — 세 번째 프로젝트 L4 (2026-10-16)

사용자 원문: "프로젝트 그럼 하나 더 만들어". 같은 계정 `changmin5781@gmail.com`에 `ugrp-sim-c-1016`(443356522325)을 추가했다. 결제 계정은 gcp2와 같은 `01C770-8A2F1F-63BA5F`이며 프로젝트 추가를 새 크레딧 지급으로 해석하지 않는다. 기본값은 계속 gcp2다. 할당량 요청에는 `--billing-project=ugrp-sim-c-1016`도 붙인다.

- `gcp3` = `ugrp-act-l4-gcp3`, 서울 `asia-northeast3-a`, gcp2 L4와 같은 `g2-standard-8`·L4 1개·140 GB `pd-balanced`·STANDARD. 고정 공개 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`에서 재설치한다. 사용 중인 gcp2 디스크의 이미지·원본·키를 복사하지 않는다.
- 2026-10-16 생성 당시 옵션(상한 제거 결정 전): `--max-run-duration=8h --instance-termination-action=STOP --maintenance-policy=TERMINATE --no-service-account --no-scopes`. 전용 개인키는 Mac `~/.ssh/ugrp_gcp3`에만 있고 VM에는 공개키만 둔다. 시작 스크립트는 `scripts/gcp_idle_guard_startup.sh`; 유휴20분 가드는 ugrp의 Python/MuJoCo/ffmpeg 작업도 확인한다. 임대는 수동 정지를 막되 오래 남은 임대만으로 자동 유휴 종료를 막지는 않는다. gcp2 VM의 기존 메타데이터/장치는 변경하지 않는다.
- 프로젝트만 필터한 크레딧 포함 순비용1,000 KRW 월 예산·50/100% 이메일 알림 → `budget-stop` → Gen2 함수 `stop_on_budget`, `TARGET_PROJECT=ugrp-sim-c-1016`. 함수 소스·requirements는 gcp2 보존본과 바이트 동일하며 실행 서비스 계정은 `budget-stopper@ugrp-sim-c-1016.iam.gserviceaccount.com`(`roles/compute.instanceAdmin.v1`)이다. 기본 결제 IAM 이메일 알림은 켜 둔다. 실증·시간·해시는 [gcp3setup 기록](../experiments/2026-10-16-gcp3setup/README.md)에 남긴다. 예산 집계 지연·VM 밖 비용의 한계는 gcp2와 같다.
- 환경은 CPU 재생 `.venv-sim`과 고정 MJWarp `.venv-warp`를 분리한다. MJWarp3.16.0/소스57b4692f·Warp1.15.0·NumPy2.5.2와 주요 영상 패키지는 gcp2 설치본을 대조한다. 인프라 확인은 작은 모형의 2세계·1스텝뿐이며 교사/학생/영상/E2E 관문 통과를 승계하지 않는다.
- 사용: `python3 scripts/gcpctl.py start gcp3`, `bash scripts/oracle_run.sh --host gcp3 WORKTREE RUN -- COMMAND`, `python3 scripts/gcpctl.py stop gcp3`. 공용 Git 직접참조·해시/fetch-lite·`outputs/gcp3-runs`/`outputs/gcp3-lifecycle`을 사용한다. 2026-10-16 상한 제거 결정 전 대기 한도는 L4 8h에서 기존 정리 여유30분을 뺀7.5h였다.
- 실행기는 `leases/<RUN>.json`에 작업·Mac PID/호스트·시작·예상 종료·소스SHA를 기록한다. VM당40개 임대 상한을 파일 잠금 아래 확인한다. GPU 세계 수는 CPU 프로세스 수가 아니며, GPU 배치 제출 전 기존 임대/PID/GPU 메모리를 확인한다. 완료 검증 뒤 자기 임대만 지우고, 다른 임대 또는 ugrp Python/MuJoCo/ffmpeg가 있으면 정지를 거부한다. 원본은 gcp3 영속 디스크에 남기고 gcp1/gcp2 결과와 합산하지 않는다.

## gcp4 — 네 번째 프로젝트 L4 (2026-10-16)

사용자 원문: "프로젝트 하나 더 만들어서 L4 하나 더 써". `changmin5781@gmail.com` / `ugrp-sim-d-1016`(298701037365)에 gcp3와 같은 실행 기반을 추가한다. PR #554/#558 위에 쌓으며 기본 호스트는 gcp2다. gcp1에는 요청을 보내지 않고 gcp2/gcp3 장치는 변경하지 않는다.

- `gcp4` = `ugrp-act-l4-gcp4`, `asia-northeast3-a`, STANDARD `g2-standard-8`·NVIDIA L4×1·140GB `pd-balanced`. 고정 공개 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`과 공개 패키지로 설치하며 원본·디스크·키를 복사하지 않는다.
- 사용자 "8시간 상한 — 이건 좀 없애라"에 따라 실행 시간 상한을 두지 않는다. 유휴20분 가드·`--no-service-account --no-scopes`·프로젝트 SSH 키 차단을 유지한다. 새 개인키는 Mac `~/.ssh/ugrp_gcp4`에만 보관한다.
- 이 프로젝트 번호만 필터한 월 순비용1,000 KRW(`INCLUDE_ALL_CREDITS`)·50/100% 알림·기본 결제 IAM 이메일 → `budget-stop` → Gen2 함수 `stop_on_budget`, `TARGET_PROJECT=ugrp-sim-d-1016`. e2-micro 수동 발행 시험과 시험 VM/디스크 삭제를 확인한 뒤 L4를 생성한다. 실제 청구 집계 지연·VM 밖 비용은 별도다.
- 사용: `python3 scripts/gcpctl.py start gcp4`, `bash scripts/oracle_run.sh --host gcp4 WORKTREE RUN -- COMMAND`, `python3 scripts/gcpctl.py stop gcp4`. 임대 JSON·VM당40개 잠금 검사·공용 Git 직접참조·해시/fetch-lite 규칙은 gcp3와 같다. 다른 임대나 ugrp Python/MuJoCo/ffmpeg가 있으면 수동 정지를 거부한다. GPU 배치 수는 제출 전에 임대/PID/GPU 메모리로 별도 결정한다.
- 환경·시험 시간·정지 상태·관문·해시는 [gcp4setup 기록](../experiments/2026-10-16-gcp4setup/README.md)에 남긴다. `outputs/gcp4-runs`/`outputs/gcp4-lifecycle`을 사용하고 다른 프로젝트 결과와 합산하지 않는다. 짧은 CUDA 배치 스텝은 인프라 확인이며 연구 장면·렌더·교사/학생·E2E 성공 검증은 별도다.

## gcp1 과거 구성 (보존 기록)

- `gcp1` = 인스턴스 `ugrp-sim-gcp1`, 서울 `asia-northeast3-a`, **n4-highcpu-64**(Intel Xeon 8581C Emerald Rapids, 64 vCPU, 128 GiB), 150 GB hyperdisk-balanced. 이미지 `ugrp-sim-bench-c1f02ac0`(Ubuntu 24.04, `.venv-sim`, 소스 c1f02ac0 포함)에서 만들었다.
- 2026-10-14 당시 생성은 다음 옵션이었다: `--max-run-duration=8h --instance-termination-action=STOP --no-service-account --no-scopes`. VM에는 gcloud·모델·Kaggle 키가 없다(SSH 개인키는 Mac의 `~/.ssh/ugrp_gcp1`뿐). 단, gcp1은 2026-10-15 사용자 결정으로 `gcloud compute instances set-scheduling ugrp-sim-gcp1 --zone asia-northeast3-a --project ugrp-act-train-1014 --max-run-duration=24h --instance-termination-action=STOP`을 적용했다(정지 상태에서만 바꿀 수 있다).
- `scripts/gcp_idle_guard_startup.sh`(시작 스크립트): 시뮬레이션·pip·apt·rsync 프로세스가 20분 없으면 `shutdown -h now`.
- 비용 상한은 기존 예산(순비용 1,000 KRW) → Pub/Sub `budget-stop` → Cloud Function이 프로젝트의 모든 VM을 정지하는 장치다. 이 코드는 건드리지 않는다.
- 기존 Mac `Host gcp1` 설정과 디스크·원본 경로는 보존한다. gcp1 생명주기는 현재 차단돼 있으며 이 작업에서는 접속하지 않았다.

## 사용

```sh
python3 scripts/gcpctl.py status gcp2
bash scripts/oracle_run.sh --host gcp2 --per-run-mb 128 --class dev WORKTREE RUN -- COMMAND
bash scripts/oracle_run.sh --host gcp2 fetch-lite RUN
python3 scripts/gcpctl.py stop gcp2     # 임대·시뮬레이션이 있으면 거부(75)
```

`remote_run.py`/`oracle_run.sh`와 `gcpctl.py`의 기본값은 gcp2다. `--host`로 별칭을 선택한다(기존 `ORACLE_HOST` 명시값도 보존). 흐름: gcloud 시작 → 저장 예산·메모리 확인 → 공용 Git의 직접 참조 사본 → 실행 → 완료 대기 → VM에서 해시 검증 → fetch-lite(`outputs/<host>-runs`) → `outputs/<host>-lifecycle/<RUN>.json` → 정지(디스크 보존). GCP 원본의 ARM 보관은 아직 없다. `--detach`는 기다리지 않으며 유휴 가드/24시간 상한은 유지한다.

SSH 설정은 `python3 scripts/gcpctl.py ssh-config gcp2` 출력으로 만든다. ProxyCommand에는 설정 파일과 스크립트의 절대경로가 들어가며 시작마다 바뀌는 외부 IP를 해당 계정·프로젝트에서 조회한다. gcp2setup 종료 후 VM은 정지하고 조정자가 대기열을 낸다.

## gcp2 확인 실행 (2026-10-15)

| 호스트/근거 | 동시 수 | wall/SIM 중앙 | 최대 | 범위 |
|---|---:|---:|---:|---|
| gcp1 사용자 제공 최근 기록 | 16 | 2.35–2.66 | 미대조 | 실행별 소스가 달라 직접 짝 비교 아님 |
| gcp1 `c1f02ac0`, 10/14 저장 측정 | 16 | 2.486 | 2.701 | 같은 소스·동일 계획/스레드 설정의 과거 기준 |
| **gcp2 `c1f02ac0`** | **16** | **2.938** | **3.242** | 16/16, 각30 SIM초, 모두 `cap_end` |

이번 gcp2 측정은 과거 동일 소스 기준보다 약18.2% 느렸다. 차단 기준6.0과 경고 기준3.5는 통과했다. 원인은 확인하지 않았으며 속도 개선이나 전체 교사 관문 통과로 보고하지 않는다. 모든 실행의 결과·HOST_ERROR 수·해시·원본 경로와 관문별 통과 수 표는 [기록](../experiments/2026-10-15-gcp2setup/README.md)에 있다.

렌더는 소스 `4a69e6bc`·저장된 `release_gate-74039` 계획과 옵션을 그대로 재생했다. r1/r2 자기 카메라·평가용 개요 JPEG **16/16 SHA-256 일치**(prefix 첫0/1/2초의9장 + Mac에 남은 원본에서 고른7장 추가). gcp1 원본8장은 로컬에서도 원래 매니페스트와 일치했고, gcp2 선택16장도 Mac 회수 뒤 재검증했다. 단일 장면/선택 프레임의 결과이며 모든 장면·전체 시계열 동등성을 뜻하지 않는다. 새 호스트 결과는 합산하지 않는다.

## gcp1 과거 속도 실측 (소스 c1f02ac0, 교사 visible_only, 30 SIM초 예비 실행)

기준: Azure VM3(F16als_v6, 16코어) 동시 16개 wall/SIM 중앙 2.66. 가격은 시간당 정가. 상세는 `experiments/2026-10-14-gcp-sim-bench/summary.json`.

| 머신 | 동시 | wall/SIM 중앙 / 최대 | 처리량 SIM초/시간 | SIM초/$ |
|---|---|---|---|---|
| Azure F16als_v6 ($1.192) | 16 | 2.66 / 미기록 | 21,654 | 18,166 |
| GCP c2d-highcpu-32 (Zen3) | 1 / 16 | 2.97 / 3.02, 최대 3.32 | 19,073 (16개) | 가격 미확인 |
| GCP n4-highcpu-64 ($3.1454, 제3자 표) | 1 | 2.25 | 1,597 | - |
| 〃 | 16 | 2.49 / 2.70 | 23,167 | 7,365 |
| 〃 | 32 | 2.86 / 3.40 | 40,265 | 12,801 |
| 〃 | 40 | 3.34 / 3.83 | 43,089 | 13,699 |
| 〃 | 48 | 3.74 / 4.19 | 46,154 | 14,674 |

- 현행 속도 기준: 사용자 원문은 2026-10-15 "3.5초 이거 좀 더 유연하게 하라니까"(이전 2026-10-13: "16개 동시 실행으로 하고, 기준 좀만 여유롭게")다. 다음 수치와 적용 방식은 조정자 결정(사용자 미확인)이다. 속도 측정은 기록 전용이며 동시 실행의 wall/SIM 중앙값을 기록·보고하고, 중앙값 >3.5는 경고만 한다. 속도로 실행을 막는 경우는 중앙값 >6.0(평소 2.8–3.3의 약 2배) 또는 측정 실행 미완료/HOST_ERROR뿐이다. 그 배치의 남은 실행 제출을 멈추고(진행 중 실행은 끝까지 기록), 원인 확인 전 새 배치를 내지 않는다. 별도 속도 단계를 따로 돌려 기다리지 않고, 계획 동시 수의 본 실행(관문·진단) 첫 30 SIM초에서 같은 방식으로 잰다. 실행 중 경고 파일은 6.0×1.5(9.0)를 연속 10분 초과할 때 남긴다.
- 2026-10-14 당시 속도 게이트(중앙 ≤3.5)는 n4-highcpu-64에서 **동시 40개까지** 통과, 48개는 실패. 한 VM이 VM3의 약 2배 처리량이다. 달러당은 Azure가 더 낫다(Azure 18.2k > GCP 13.7k SIM초/$).
- `LP_NUM_THREADS=1`과 미설정은 동일했다(2.49 vs 2.51). 프로세스당 스레드는 최대 2개다.
- 서울 C4/C4D 할당량은 0, 도쿄는 24 vCPU라 64 vCPU c4/c4d는 증설 없이 못 만든다. 증설 신청은 하지 않았다. c4/c4d/c3 속도는 미측정이다.
- GCP 가격은 공식 페이지에서 가져오지 못했다(Cloud Billing API 비활성). n4 가격은 제3자 표(gcloud-compute.com)라 **미확인**이다.

## 합산 금지

CPU 세대가 다르면 렌더 이미지 바이트가 달라질 수 있다. 같은 머신 종류라도 gcp2는 별도 호스트로 기록하고 gcp1과 결과를 합산하지 않는다. GCP(Emerald Rapids) 결과는 Azure(Zen4/Zen3)·이전 결과와 합산하지 않고 호스트·머신 종류를 기록해 구분한다.

## 참고 자료

- [Git clone --reference와 alternates 보존](https://git-scm.com/docs/git-clone) — 공용 객체 저장소를 지우거나 prune하면 차용 사본이 손상될 수 있음.
- [Compute Engine `--max-run-duration`·종료 동작](https://cloud.google.com/compute/docs/instances/limit-vm-runtime)
- [C4/N4와 Hyperdisk 부팅 디스크](https://cloud.google.com/compute/docs/general-purpose-machines)
- [예산 알림으로 자원 정지](https://cloud.google.com/billing/docs/how-to/notify#cap_disable_billing_to_stop_usage)
- [OpenSSH ProxyCommand](https://man.openbsd.org/ssh_config#ProxyCommand)

## gcp6 — 여섯 번째 프로젝트 L4·다른 계정 (2026-10-16)

사용자 원문: "쳐낼 거 쳐내고, 빠르게 할 건 더 빠르게 할 수 없나", "프로젝트 하나 더 만들어서 L4 하나 더 써", "gcp 계정 하나 더 추가할래". 프로젝트 `ugrp-sim-f-1016`(503325597974)은 **`kcm5781kcm5781@gmail.com`**, 결제 `010CD7-4B991B-84AAC7`을 쓴다. 모든 gcloud에 이 계정·프로젝트를 명시하고 Mac 기본 계정 `changmin5781@gmail.com`과 기본 호스트 gcp2는 유지한다. 다른 계정 사용자에게 IAM 접근 권한을 부여하지 않는다.

- `gcp6` = `ugrp-act-l4-gcp6`, 서울 `asia-northeast3-a`, STANDARD `g2-standard-8`·NVIDIA L4×1·140GB `pd-balanced`. gcp4와 같은 공개 고정 이미지·패키지에서 새로 설치한다. 원본·디스크·개인키·모델/에이전트 자격 증명은 복사하지 않는다.
- 프로젝트만 필터한 월 순비용1,000 KRW 예산(모든 크레딧 포함)·기본 결제 IAM 이메일 → Pub/Sub `budget-stop` → Gen2 `stop_on_budget`(`TARGET_PROJECT=ugrp-sim-f-1016`). e2-micro 발동·시험 VM/디스크 삭제를 확인한 뒤에만 L4를 생성한다. 집계 지연·VM 밖 비용의 한계는 같다.
- 실행 시간 상한 없이 유휴20분 가드·`--no-service-account --no-scopes`·프로젝트 SSH 키 차단을 유지한다. Mac 전용 새 키는 `~/.ssh/ugrp_gcp6`. `leases/<RUN>.json`, 파일 잠금 아래 VM당40개 상한, GPU 메모리/기존 PID 확인·공용 Git 직접참조·해시/fetch-lite 규칙은 gcp4와 같다. 다른 임대/실행 프로세스가 있으면 수동 정지를 거부한다.
- `python3 scripts/gcpctl.py start gcp6`, `bash scripts/oracle_run.sh --host gcp6 WORKTREE RUN -- COMMAND`, `python3 scripts/gcpctl.py stop gcp6`. 원본은 gcp6 영속 디스크에 남기고 작은 기록은 `outputs/gcp6-runs`/`outputs/gcp6-lifecycle`로 회수한다. 다른 프로젝트 결과와 합산하지 않는다.
- 초기 act16w 용도(조정자 해석)는 작업 중 `COORDINATOR_NOTE.md`의 19:00 지시로 beamact3 C2 학습 준비로 바뀌었다. gcp2 L4의 ACT 환경을 동일 버전으로 재현한다. 짧은 MJWarp 2세계·1스텝과 기존 beamact3 B 모듈의 실제 TRAIN 데이터50스텝 저장·재로딩은 환경 확인이며 C2 본 학습·학생/교사/E2E 관문이 아니다. beamact3의 완료된 dataset-view 원본과 stages 파일만 Mac 중계 SSH 스트림으로 전달하고 파일별 SHA를 대조한다. C2 본 학습은 담당 작업에서 별도로 시작한다.
- 구성·검증 결과와 정지 상태는 [gcp6setup 기록](../experiments/2026-10-16-gcp6setup/README.md)에 남긴다. PR #559 위에 쌓으며 #554/#558에 의존한다.
