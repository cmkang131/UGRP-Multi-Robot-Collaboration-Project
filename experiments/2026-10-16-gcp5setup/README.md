# gcp5setup — 다섯 번째 프로젝트 L4 / beamact3 C2 준비

사용자(2026-10-16): "프로젝트 하나 더 만들어서 L4 하나 더 써", "쳐낼 거 쳐내고, 빠르게 할 건 더 빠르게 할 수 없나". `changmin5781@gmail.com` / `ugrp-sim-e-1016`(1034909621664)에 gcp4와 같은 기반을 추가한다. PR #554 → #558 → #559 위에 쌓으며 기본 호스트는 gcp2다. gcp1에는 API/SSH 요청을 하지 않았고 gcp2/gcp3/gcp4의 기존 비용 장치는 변경하지 않았다. gcp2 L4는 데이터·환경 조회/전송에만 공유했다.

## 상태

**READY (인프라·ACT 환경)**: 예산 발동·시험 VM/디스크 삭제·MJWarp CUDA 2세계1스텝·115패키지 버전 일치·데이터1,482/1,482 SHA·ACT50step 저장/재로딩·같은 입력 예측 완전 일치를 통과했다. ACT smoke97.27초·학습60,023행·GPU peak1.57GB. CPU/MJWarp freeze와 핵심 소스3파일 SHA도 gcp4와 일치한다. 임대 중 정지 거부75·유휴 타이머 active·전용 키·실행 시간 상한 부재를 확인하고, 다른 작업이 없을 때 자기 임대만 해제해 **TERMINATED**로 인계한다. 비물리18개와 shell/AST·diff 검사를 통과했다. 최종 판정은 [summary.json](summary.json)·[누적 관문 표](evidence/funnel.json)·[ops-alert.md](ops-alert.md)에 남긴다. 이번 범위는 인프라와 학습 환경 준비다. C2 본학습·교사/학생·폐루프·운반 성공 관문은 실행하지 않는다.

## 예산 정지

프로젝트 번호 `projects/1034909621664`만 필터한 월 **순비용1,000 KRW**(`INCLUDE_ALL_CREDITS`)·CURRENT_SPEND 50/100% 알림 → Pub/Sub `budget-stop` → Gen2 함수 `stop_on_budget(TARGET_PROJECT=ugrp-sim-e-1016)`. 기본 결제 IAM 이메일을 유지한다. 함수 코드는 gcp4와 바이트 동일하며 별도의 gcp5 실행 계정만 사용한다.

`ugrp-budget-test-gcp5`(e2-micro, 10GB, 서비스 계정/scope 없음)에 `costAmount=budgetAmount=1000` 수동 발행 후 **6.983초 STOPPING·36.474초 TERMINATED**를 관측했다. 함수 `stop_all` 로그 대상도 일치한다. 시험 VM·부팅 디스크 삭제 후 각각 목록0을 확인한 다음에만 L4를 생성했다. 실제 비용 집계 지연·결제 이메일 수신은 시험하지 않았다. VM 정지 후에도 디스크·네트워크·빌드 저장소 등 비용은 남을 수 있다.

## L4와 환경

`gcp5` = `ugrp-act-l4-gcp5`, `asia-northeast3-a`, STANDARD **g2-standard-8 / NVIDIA L4×1 /140GB pd-balanced**. 공개 고정 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`과 [설치 스크립트](setup_guest.sh)를 사용한다. 사용자 "8시간 상한 — 이건 좀 없애라"에 따라 실행 시간 상한은 붙이지 않는다. 유휴20분·예산 정지·`--no-service-account --no-scopes`·프로젝트 SSH 키 차단은 유지한다. 새 개인키 `~/.ssh/ugrp_gcp5`는 Mac에만 있다.

- CPU: `/home/ugrp/ugrp-sim/ugrp/.venv-sim`, MuJoCo3.12.0.
- MJWarp: `/home/ugrp/ugrp-sim/ugrp/.venv-warp`, MuJoCo/MJWarp3.16.0·Warp1.15.0, pinned MJWarp `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`.
- ACT: `/home/ugrp/ugrp-rl1b-act-env`, gcp2 L4의 [115패키지 freeze](evidence/act-freeze-reference.txt)를 공개 소스에서 같은 버전으로 재설치. Torch2.11.0+cu128·torchvision0.26.0+cu128·LeRobot `89236ea0f4f81a81ca566081e20dd1ff5f823cbe`.

PyTorch 추가 인덱스가 `torchcodec==0.10.0`에 CUDA 로컬 버전 `0.10.0+cu128`을 선택하여, [보정 스크립트](pin_act_codec.sh)로 PyPI의 원본 버전을 다시 설치하고 freeze를 재검증한다. 새 설치는 `setup_guest.sh` 뒤 이 스크립트를 실행한다.

전체 OS·패키지 wheel의 바이트 동등성을 주장하지 않는다. 패키지 버전 전체 일치·실제 CUDA 동작을 따로 확인한다. 알려진 자격 증명 경로의 부재와 SSH 파일 목록도 기록한다.

## 학습 데이터와 smoke

원본은 **gcp2 프로젝트의 L4** `ugrp-act-l4-gcp2`에 있다(CPU SSH 별칭 gcp2와 구분). `/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view`의 1,482파일·21,052,237,810바이트를 [출발 SHA 목록](evidence/dataset-sha256.json)으로 고정했다. 매니페스트 SHA는 `a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd`다. [해시 계산](hash_source.py)·[전송/도착 검증](transfer_dataset.py)을 사용하고, 같은 절대경로로 복사한다. Mac에는 raw를 저장하지 않고 SSH 압축 스트림만 중계한다. 전체 홈·원본 디스크·키·에이전트 자격 증명은 복사하지 않는다.

beamact3 소스 **`bbb757ad3735a98c7778f4d43aab041495a6c201`**의 harness/scripts 및 `train_shared.py`만 `git archive`로 `/home/ugrp/ugrp-sim/setup/beamact3-reference`에 보낸다. 1,592파일 원본 SHA를 [출처 목록](evidence/training-source-provenance.json)과 비교한다. 이 경로는 설치 점검용 코드 아카이브이며 Git 이력을 복사하지 않는다. 후속 실제 `src/<sha>` 사본은 공용 `git-shared.git`을 직접 `--reference`해야 한다. 공용 저장소는 gc/maintenance off·prune 금지다.

[training_smoke.py](training_smoke.py)는 실제 `scripts.train_grasp_act`·`train_shared.py` 의존성을 import한 뒤 같은 beamact3 B 모듈·실제 TRAIN 데이터로 **50step**을 학습한다. 50은 사용자가 제시한 환경 확인 계산량이며 연구 수용 상수가 아니다. 고정 seed20261015·batch8·기존 optimizer/loss를 사용하고 actor·optimizer 저장/재로딩 및 같은 TRAIN 입력의 예측 완전 일치를 검사한다. 출력은 `gcp5:/home/ugrp/ugrp-sim/setup/training-smoke-v1`; 새 실행은 다른 출력 이름으로 남긴다. 이 smoke 가중치는 인프라 원본으로 원격에 보존하며 연구 결과에 선택/배포한 모델이 아니다.

**C2 전달:** ACT 환경·데이터는 위 경로로 준비한다. 현재 참조 `train_shared.py`는 gcp2 전용 host guard·A/B만 지원한다. C2 실행기의 gcp5 허용과 C2 설정은 beamact3 브랜치에서 연결해야 한다. 이 준비 작업은 guard를 우회하거나 C2 코드를 대신 정하지 않는다.

## 운영과 보존

```sh
python3 scripts/gcpctl.py status gcp5
python3 scripts/gcpctl.py start gcp5
# 기존 임대/PID/GPU 메모리 확인 후 자기 임대 생성
bash scripts/oracle_run.sh --host gcp5 WORKTREE RUN -- COMMAND
# 원본·회수 해시 확인 뒤 자기 임대만 해제, 다른 작업이 없을 때 정지
python3 scripts/gcpctl.py stop gcp5
```

`configs/gcp_hosts.json`을 읽는 gcpctl/remote_run이 gcp5를 지원한다. 기본 gcp2와 기존 프로필은 그대로다. `leases/<RUN>.json`·VM당40개 잠금 검사·다른 임대/Python/MuJoCo/ffmpeg가 있으면 정지 거부 규칙도 같다. GPU 세계 수는 프로세스 수와 다르므로 실제 제출량은 메모리·PID를 보고 정한다. 원본은 gcp5 영속 디스크에, 요약·환경 freeze·검증 기록·전체 SHA는 로컬/GitHub에 보존한다. 다른 프로젝트 결과와 합산하지 않는다.

공식 절차 확인(2026-10-16): [예산 Pub/Sub 알림](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications), [예산 생성·기본 이메일 수신자](https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/create). 기반은 [gcp4setup](../2026-10-16-gcp4setup/README.md), 시간 상한 제거는 PR #558이다.
