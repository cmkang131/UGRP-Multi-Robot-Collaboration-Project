# gcp4setup — 네 번째 프로젝트 L4 준비

2026-10-16 사용자 원문: "프로젝트 하나 더 만들어서 L4 하나 더 써". `changmin5781@gmail.com` / `ugrp-sim-d-1016`(298701037365)에 gcp3와 같은 실행 기반을 추가한다. 조정자가 만든 프로젝트·결제 연결·할당량을 확인하고 PR #554/#558 위에 쌓는다. 기본 호스트는 gcp2이며 다른 프로젝트와 결과를 합산하지 않는다.

## 상태

**READY (GCP 인프라)**: 예산 정지 시험·시험 VM/디스크 삭제·L4 생성·**CUDA 2세계·1스텝 PASS**. MuJoCo/MJWarp3.16.0·Warp1.15.0, NVIDIA L4, 각0.002 SIM초 진행·유한 상태·낙하 방향을 확인했다. gcp3의 패키지 버전·핵심 소스3개 SHA256도 일치한다. 회수4파일과 설치 소스3파일 해시·유휴 타이머 active·알려진 자격 증명 경로 부재(SSH는 authorized_keys만)·자기 임대 중 정지 거부75를 확인했다. 다른 작업이 없음을 확인하고 자기 임대만 해제했으며 VM **TERMINATED**를 확인했다. 비물리 검사17개와 shell/AST·diff 검사를 통과했다. 최종 판정은 [summary.json](summary.json)·[관문 누적 표](evidence/funnel.json)·[ops-alert.md](ops-alert.md)에 남긴다. 인프라 확인이며 교사·학생·학습·운반 관문 결과가 아니다.

## 예산 정지

프로젝트 번호 `projects/298701037365`만 필터한 월 **순비용1,000 KRW** 예산(`INCLUDE_ALL_CREDITS`)·CURRENT_SPEND 50/100% 알림 → Pub/Sub `budget-stop` → Gen2 함수 `stop_on_budget`, `TARGET_PROJECT=ugrp-sim-d-1016`. 기본 결제 IAM 이메일을 유지한다. 이메일 실제 수신과 실제 청구 집계 지연은 시험하지 않는다.

함수·requirements는 gcp3 보존본과 바이트 동일하다. 새 실행 계정은 `budget-stopper@ugrp-sim-d-1016.iam.gserviceaccount.com`이며 compute.instanceAdmin.v1·eventarc.eventReceiver·run.invoker를 gcp4에만 부여했다. gcp1/gcp2/gcp3에는 API/SSH 요청을 보내지 않았고 기존 장치를 변경하지 않았다.

`e2-micro` 시험 VM `ugrp-budget-test-gcp4`(10GB, 서비스 계정/scope 없음, 시험 자체10분 STOP)에 `costAmount=budgetAmount=1000` 수동 발행 후 상태 시계열과 함수 로그를 보존한다. **RUNNING →6.364초 STOPPING →140.309초 TERMINATED**를 관측했고 함수 `stop_all` 로그의 대상 이름도 일치했다. 시험 VM과 부팅 디스크를 삭제한 뒤 각각 목록0을 확인하고 L4를 생성했다. 이 시험은 Pub/Sub 이후 동작만 검증한다. 비용 집계는 지연될 수 있고 VM 정지 뒤에도 디스크·네트워크·빌드 저장소 등 VM 밖 비용은 계속될 수 있다.

## L4와 입력 경계

`ugrp-act-l4-gcp4`, 서울 `asia-northeast3-a`, STANDARD **g2-standard-8 / NVIDIA L4×1 /140GB pd-balanced**. 공개 고정 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`과 [설치 스크립트](setup_guest.sh)를 사용한다. gcp3의 원본·디스크·키는 복사하지 않는다. 공개 소스·패키지 버전을 맞추며 전체 OS/전이 의존성의 바이트 동등성을 주장하지 않는다.

사용자 "8시간 상한 — 이건 좀 없애라"(PR #558)에 따라 `max_run_duration=null`로 두고 생성 명령에 실행 시간 상한을 넣지 않는다. **유휴20분 종료·예산 정지·서비스 계정/scope 없음·프로젝트 SSH 키 차단**은 유지한다. 새 개인키는 Mac `~/.ssh/ugrp_gcp4`에만 있고 공개키만 VM에 둔다. 기존 SSH 블록은 보존한다.

[smoke.py](smoke.py)는 작은 구/바닥 모델 **CUDA 2세계·정확히1스텝**만 실행한다. import·유한 상태·시간 진행·낙하 방향을 검사하며 렌더·LLM·학습은 없다. 0.002초는 작은 인프라 모형의 고정 스텝이며 연구 수용 상수가 아니다. 실제 연구 장면·자기 카메라·교사/학생·E2E 성공은 별도로 검증해야 한다.

## 실행과 보존

```sh
python3 scripts/gcpctl.py status gcp4
python3 scripts/gcpctl.py start gcp4
# 실행 전에 기존 임대/PID/GPU 메모리 확인, 자기 임대 생성
bash scripts/oracle_run.sh --host gcp4 WORKTREE RUN -- COMMAND
# 회수·해시 확인 뒤 자기 임대만 해제, 다른 작업이 없을 때만 정지
python3 scripts/gcpctl.py stop gcp4
```

실행기는 `configs/gcp_hosts.json`에서 gcp4를 읽는다. gcp2 기본값·다른 프로필은 그대로다. `leases/<RUN>.json`에 작업·Mac PID/호스트·시작·예상 종료·소스SHA를 기록하며 파일 잠금 아래 VM당40개 상한을 검사한다. 상한 없는 호스트의 예상 종료는 null이다. GPU 세계 수는 프로세스 수와 다르므로 제출 전 임대/PID/GPU 메모리를 확인한다. 다른 임대 또는 ugrp Python/MuJoCo/ffmpeg가 있으면 정지를 거부한다. 유휴 가드는 실행 프로세스가 없는 오래된 임대만으로 종료가 막히지 않게 한다.

공용 `/home/ugrp/ugrp-sim/git-shared.git`은 자동gc/maintenance off·prune 금지로 준비한다. 후속 소스 사본은 이 저장소를 직접 `--reference`한다. 다른 사본을 참조하지 않는다. 실행 원본은 `gcp4:/home/ugrp/ugrp-sim/` 영속 디스크에 남기고 Mac에는 작은 감사·환경 freeze·결과만 회수해 해시를 확인한다. 프로젝트 예외에 따라 로컬/GitHub에 기록한다.

현재 서울 단가·실제 청구는 조회하지 않았다. VM 실행 구간은 summary에 기록하며 정지 후140GB 디스크·함수/빌드 저장소는 남는다. 프로젝트 추가를 추가 크레딧 지급으로 해석하지 않는다. 새 계획기·제어기·판정 상수·학습 기록 실행기는 추가하지 않았다.

## 참고 자료

2026-10-16 공식 문서 열람: [예산 Pub/Sub 알림](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications), [예산 생성과 기본 이메일 수신자](https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/create), [Gen2 함수 배포](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy). 절차·버전 기준은 [gcp3setup](../2026-10-16-gcp3setup/README.md), 실행 시간 상한 제거는 PR #558을 따른다.
