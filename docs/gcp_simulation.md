# GCP 시뮬레이션 실행 (2026-10-14)

사용자 요청: "GCP에서 비싼 거나 좋은 거 써서 시뮬레이션 더 빠르게", "GCP 빨리 시간 측정해서 이걸로 넘겨". 프로젝트는 `ugrp-act-train-1014`뿐이다. 다른 GCP 프로젝트와 Azure 자원은 건드리지 않는다. [Azure 실행](azure_simulation.md)은 보조로 남는다.

## 호스트와 안전장치

- `gcp1` = 인스턴스 `ugrp-sim-gcp1`, 서울 `asia-northeast3-a`, **n4-highcpu-64**(Intel Xeon 8581C Emerald Rapids, 64 vCPU, 128 GiB), 150 GB hyperdisk-balanced. 이미지 `ugrp-sim-bench-c1f02ac0`(Ubuntu 24.04, `.venv-sim`, 소스 c1f02ac0 포함)에서 만들었다.
- 생성은 `scripts/gcpctl.py create`가 고정한다: `--max-run-duration=8h --instance-termination-action=STOP --no-service-account --no-scopes`. VM에는 gcloud·모델·Kaggle 키가 없다(SSH 개인키는 Mac의 `~/.ssh/ugrp_gcp1`뿐).
- `scripts/gcp_idle_guard_startup.sh`(시작 스크립트): 시뮬레이션·pip·apt·rsync 프로세스가 20분 없으면 `shutdown -h now`.
- 비용 상한은 기존 예산(순비용 1,000 KRW) → Pub/Sub `budget-stop` → Cloud Function이 프로젝트의 모든 VM을 정지하는 장치다. 이 코드는 건드리지 않는다.
- Mac `~/.ssh/config`에 `Host gcp1` 블록이 필요하다(`python3 scripts/gcpctl.py ssh-config gcp1`이 출력). 외부 IP가 시작마다 바뀌어 `ProxyCommand`가 현재 IP를 gcloud로 찾는다. 스크립트 경로는 기본 체크아웃 기준으로 맞춘다.

## 사용

```sh
python3 scripts/gcpctl.py status gcp1
bash scripts/oracle_run.sh --host gcp1 --per-run-mb 128 --class dev WORKTREE RUN -- COMMAND
bash scripts/oracle_run.sh --host gcp1 fetch-lite RUN
python3 scripts/gcpctl.py stop gcp1     # 임대·시뮬레이션이 있으면 거부(75)
```

`--host gcp1`은 선택 토글이며 기본(oracle/azure) 동작은 바뀌지 않는다. 흐름: gcloud 시작 → 저장 예산(x86·Mac) → 소스 전송(전체 트리 shallow pack) → 실행 → 완료 대기 → VM에서 `sha256sum -c SHA256SUMS` → fetch-lite(`outputs/gcp1-runs`) → `outputs/gcp1-lifecycle/<RUN>.json` → 정지(디스크 보존). **ARM 보관은 아직 없다**: 원본은 GCP 영구 디스크에만 있다(미구현, 이월). `--detach`는 기다리지 않으며 VM 유휴 가드가 끈다.

## 속도 실측 (소스 c1f02ac0, 교사 visible_only, 30 SIM초 예비 실행)

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

CPU 세대가 다르면 렌더 이미지 바이트가 달라진다. GCP(Emerald Rapids) 결과는 Azure(Zen4/Zen3)·이전 결과와 합산하지 않고 호스트·머신 종류를 기록해 구분한다.

## 참고 자료

- [Compute Engine `--max-run-duration`·종료 동작](https://cloud.google.com/compute/docs/instances/limit-vm-runtime)
- [C4/N4와 Hyperdisk 부팅 디스크](https://cloud.google.com/compute/docs/general-purpose-machines)
- [예산 알림으로 자원 정지](https://cloud.google.com/billing/docs/how-to/notify#cap_disable_billing_to_stop_usage)
- [OpenSSH ProxyCommand](https://man.openbsd.org/ssh_config#ProxyCommand)
