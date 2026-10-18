# gcp3setup — 세 번째 프로젝트 L4 준비

2026-10-16 사용자 원문: "프로젝트 그럼 하나 더 만들어". 계정 추가 없이 `changmin5781@gmail.com` / `ugrp-sim-c-1016`(443356522325)에 L4 실행 기반을 준비한다. 기본 호스트는 gcp2로 유지한다. 인프라 확인이며 교사·학생·학습·운반 관문 결과가 아니다. 최종 판정·모든 시도·비용 범위·해시는 [summary.json](summary.json)과 [evidence/](evidence/)에 기록한다.

## 최종 상태

**READY (GCP 인프라)**: 예산 정지 시험·시험 VM/디스크 삭제·L4 CUDA 2세계1스텝·고정 소스3개 해시·자격 증명 경로 부재·유휴 타이머를 확인하고 최종 VM **TERMINATED**로 두었다. 오래 남은 detached 임대가 자동 유휴 종료를 막지 않게 보강한 뒤 실제 재부팅에서 새 스크립트 해시와 타이머를 재확인했다. 비물리 검사 **11 passed**, shell/AST·diff 검사 통과다. 다른 임대/실행 프로세스가 없음을 확인하고 자기 임대를 해제했다.

**다음 실험 제출은 NOT_READY**: Mac 저장 예산 검사가 projected free16,536,748,032bytes <20GiB로 거부됐다. 정리·우회는 하지 않았다. 연구 실행기의 gcp2 전용 host pin, 실제 연구 장면/렌더/교사·학생 관문은 별도 작업이다. 공급가 경보가 있는 새 LLM 배치도 제출하지 않았다. PR/CI/검토/병합은 인프라 상태와 별도로 보고한다.

## 경계와 변경

- 브랜치 `codex/gcp3setup`, 시작 HEAD `684451f199f709fef79f1e9583e9bb8861c9a7b7`, fetch 뒤 origin/main 일치를 확인했다. 실제 실행 스크립트는 실행 전 커밋했으며 전송 SHA와 파일별 SHA256은 `evidence/probe-source.json`에 있다.
- 첫 프로젝트 `ugrp-act-train-1014`에는 gcloud/API/SSH 요청을 보내지 않았다. gcp2에서는 기존 L4 구성·부팅 디스크의 공개 이미지 출처·패키지 버전·비용 함수/토픽을 조회만 했다. 함수/토픽의 작업 전후 JSON이 같다. gcp2 장치·디스크·임대·실행 중 작업은 변경하지 않았다.
- `configs/gcp_hosts.json`에 gcp3만 추가하고 기본값은 gcp2다. 생성 명령은 GPU/이미지 프로젝트/8h를 반영한다. 실행기 대기는 호스트 상한에서 기존 정리 여유30분을 뺀 값이다(gcp2 23.5h, gcp3 7.5h).
- GCP 실행기 임대는 작업명·소유 Mac/PID·시작·예상 종료·소스SHA의 JSON이다. 파일 잠금 아래 VM당40개 상한을 검사한다. 완료 검증 전에는 임대를 남긴다. 정지 전 임대 및 ugrp 소유 Python/MuJoCo/ffmpeg를 확인하며 실제 설치 중 정지 요청이75로 거부됐다. GPU 배치 세계 수는 이 CPU 실행 수와 다르므로 제출 전 임대/PID/GPU 메모리도 확인한다.
- 공용 유휴 가드는 위 실행 프로세스를 확인한다. 임대는 수동 정지를 막고, 오래 남은 detached 임대만으로 자동 유휴 종료를 막지는 않는다. 이 새 스크립트는 gcp3 메타데이터에만 설치했으며 gcp2 VM 메타데이터는 바꾸지 않았다. 새 제어기·판정 상수·탐색 시간 제한·학습 기록 실행기는 만들지 않았다.

## 예산 정지 실증

같은 결제 계정 `01C770-8A2F1F-63BA5F`에 **이 프로젝트 번호만 필터**한 월1,000 KRW 예산을 생성했다. `INCLUDE_ALL_CREDITS`로 순비용을 계산하고 CURRENT_SPEND 50%/100% 알림을 둔다. `disableDefaultIamRecipients`가 false(기본값)이므로 결제 관리자/결제 사용자 이메일 알림이 켜져 있다. 이메일 실제 수신이나 실제 청구 집계의 지연은 시험하지 않았다.

`budget-stop` 토픽 → Gen2 ACTIVE 함수 `stop_on_budget`; `TARGET_PROJECT=ugrp-sim-c-1016`. 실행 계정 `budget-stopper@ugrp-sim-c-1016.iam.gserviceaccount.com`의 `roles/compute.instanceAdmin.v1`을 확인했다. 토픽 publisher는 gcp2와 같은 `billing-budget-alert@system.gserviceaccount.com`이다. 함수 소스·requirements는 [gcp2 보존본](../2026-10-15-gcp2setup/evidence/)과 바이트 동일하다.

| 파일 | SHA256 |
|---|---|
| function/main.py | dea9440eac028eb37e325b71ef5a5ddb0a5b4a1af037c55c5742f30d3b58e55f |
| function/requirements.txt | 2aecef10e2607325f8413568b93fe629c24ea11e8be01148d48aff091a585776 |

`e2-micro` 시험 VM `ugrp-budget-test-gcp3`(10GB, SA/scope 없음,10분 STOP)에 `costAmount=budgetAmount=1000`을 수동 발행했다. 발행 시작 기준 RUNNING → **5.424초 STOPPING →54.665초 TERMINATED**를 관측했고 함수의 `stop_all` 로그와 일치한다. 시험 VM과 디스크를 삭제한 뒤 각각 목록0을 확인한 다음 L4를 생성했다. 이는 Pub/Sub 이후 정지 동작의 시험이다. 실제 알림은 수시간 지연될 수 있고 VM 밖 디스크/네트워크 등의 비용은 계속된다.

설치 시도 중 실패도 보존했다. Budget API 활성화 전 조회1회, 잘못 적은 publisher 계정1회, 새 서비스 계정 IAM 연결 직후 거부1회다. gcp2의 실제 publisher를 조회해 바로잡았고 같은 새 IAM 계정은 재시도에서 성공했다(전파 지연으로 추정). 원본 오류·명령과 [분포](evidence/setup-rejections.json)를 남겼으며 실패를 성공으로 집계하지 않는다.

## L4와 환경

`ugrp-act-l4-gcp3`, `asia-northeast3-a`, STANDARD **g2-standard-8 / NVIDIA L4×1 /140GB pd-balanced**. gcp2 디스크를 복사하지 않고 같은 고정 공개 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`을 썼다. GPU/CPU 할당량 스냅샷은 `evidence/region-quota.json`, `global-quota.json`에 있다. 할당량 요청은 이번에 추가하지 않았다. 후속 요청은 계정·프로젝트 외 `--billing-project=ugrp-sim-c-1016`도 붙인다.

`maxRunDuration=28800s`, STOP, host maintenance TERMINATE, serviceAccounts 없음, scope 없음, 프로젝트 SSH 키 차단을 확인한다. 새 개인키는 Mac `~/.ssh/ugrp_gcp3`에만 생성하고 공개키만 VM에 둔다. `Host gcp3`는 이 worktree의 gcpctl/config를 명시하며 기존 SSH 블록은 보존했다.

공개 패키지/고정 공개 소스로 재설치한다([스크립트](setup_guest.sh)). CPU 재생 `~/ugrp-sim/ugrp/.venv-sim`은 MuJoCo3.12.0, MJWarp용 `.venv-warp`는 MuJoCo/MJWarp3.16.0·Warp1.15.0·소스57b4692f이다. 주요 영상 패키지/NumPy2.5.2를 gcp2 설치본과 대조한다. 전체 OS/전이 의존성의 바이트 동등성은 주장하지 않는다. 공용 `/home/ugrp/ugrp-sim/git-shared.git`은 자동gc/maintenance off·prune 금지로 준비한다. 후속 소스 사본은 이 저장소를 직접 `--reference`하고 다른 사본을 참조하지 않는다.

[smoke.py](smoke.py)는 작은 구/바닥 모델 **2세계·정확히1스텝**만 CUDA에서 실행한다. import·유한 상태·시간 진행·낙하 방향을 검사하며 렌더·모델 호출·학습은 없다. 0.002초는 이 작은 인프라 모형의 고정 스텝이며 연구 수용 상수가 아니다. 실제 연구 장면/자기 카메라 영상/성공률/E2E는 미검증이다. 기존 연구 실행기의 gcp2 전용 host pin 해제도 이 작업 범위 밖이다.

## 재현·비용·보관

```sh
python3 scripts/gcpctl.py status gcp3
# 시작 시 자기 leases/<TASK>.json 생성, 기존 임대/PID/GPU 메모리 검사
python3 scripts/gcpctl.py start gcp3
ssh gcp3 '/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python /home/ugrp/ugrp-sim/setup/smoke.py /home/ugrp/ugrp-sim/setup/NEW-smoke.json'
# 실행·회수·해시 확인 뒤 자기 임대만 해제, 다른 작업이 없을 때만 정지
python3 scripts/gcpctl.py stop gcp3
```

공식 요금의 현재 서울 단가와 실제 청구는 이번에 확정하지 못했다. GPU VM 실행 구간·시험 VM 생성/정지 시각은 최종 요약에 기록하며, 과거 실험의 가정1.096USD/h를 사용하는 계산은 **계획 추정**으로만 표시한다. 크레딧/환율/세금·설치/저장소·빌드·함수·네트워크 실제 청구와 다르다. 프로젝트 추가는 추가 크레딧 지급을 보장하지 않는다. 정지 뒤에도140GB 영속 디스크 및 비용 장치 빌드 이미지/소스가 남는다.

Mac 여유 약16GiB로 수KB 설정·요약만 회수하며 전체 원본/환경/디스크는 전송하지 않는다. 원본 설치 로그와 환경 freeze는 `gcp3:/home/ugrp/ugrp-sim/setup/`에 보존한다. 모든 결과·실패/HOST_ERROR·관문별 누적 수·해시를 요약에 연결하며 gcp1/gcp2와 합산하지 않는다. 프로젝트 예외에 따라 로컬/GitHub에 기록한다.

시작 시 기존 모델 공급 경보 파일에서 Gemma@DeepInfra prompt/completion/cache 단가50% 인상 경보를 확인해 사용자에게 알렸다. 이번 작업의 LLM 호출0이며 새 LLM 배치는 제출하지 않았다.

## 참고 자료

2026-10-16 공식 문서 열람: [예산 Pub/Sub 알림과 전달 지연](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications), [gcloud budget 생성과 기본 이메일 수신자](https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/create), [Gen2 함수 배포 옵션](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy). [Compute 요금](https://cloud.google.com/products/compute/pricing)은 열람했지만 accelerator-optimized 상세 표는 응답 크기 제한으로 수집하지 못해 현재 단가 미확인으로 남겼다. 구성은 [gcp2 원본](../2026-10-15-gcp2setup/README.md), MJWarp 소스 해시 기준은 [warp2 설치본 감사](../2026-10-16-warp2/runtime/l4-environment.json)를 따른다.
