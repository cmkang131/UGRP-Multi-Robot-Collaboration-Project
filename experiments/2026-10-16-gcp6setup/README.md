# gcp6setup — 여섯 번째 프로젝트 L4 준비

사용자(2026-10-16): "쳐낼 거 쳐내고, 빠르게 할 건 더 빠르게 할 수 없나", "프로젝트 하나 더 만들어서 L4 하나 더 써", "gcp 계정 하나 더 추가할래". 새 계정 `kcm5781kcm5781@gmail.com` / 프로젝트 `ugrp-sim-f-1016`(503325597974) / 결제 `010CD7-4B991B-84AAC7`에 구성했다. PR #559 위에 쌓으며 #554/#558에 의존한다.

## 결과

**READY — 인프라·ACT 환경·beamact3 데이터 준비.** `ugrp-act-l4-gcp6`의 **TERMINATED**를 확인했다(2026-10-16T02:58:12.642-07:00). L4 실행 구간은 924.815초였다.

- 순비용1,000 KRW 예산 → Pub/Sub → 정지 함수 시험: 발행 후 **6.660초 STOPPING →56.754초 TERMINATED**. 시험 VM·부팅 디스크 삭제 후 목록0 확인.
- MJWarp **CUDA 2세계·정확히1스텝 PASS**. 각0.002 SIM초·유한 상태·낙하 방향 확인, gcp4와 패키지 버전·핵심 소스3개 SHA 동일.
- 기존 beamact3 **B 모듈**과 실제 TRAIN60,023행에서 **batch8·50스텝 PASS**(83.787초). 모델·optimizer 저장/재로딩과 예측 비트 일치 확인. C2 성능·본 학습·학생/교사/E2E 성공으로 집계하지 않는다. 체크포인트는 인프라 검사 전용이며 연구용 모델로 선택하지 않았고 VM에 보존한다.
- 데이터 **1,483파일·21,052,583,548바이트**, 원본/수신 SHA 전부 일치. 원본 크기·mtime 불변, gcp2 자기 전송 임대만 제거, gcp2 정지 시도0.
- 비물리 호스트 검사 **18 passed**, Python AST·shell syntax·diff 검사 통과. 유휴 타이머 active·알려진 자격 증명 경로 부재·자기 임대 중 수동 정지 거부75·다른 작업 없음·자기 임대 제거 확인.

전체 성공·실패/복구는 [summary.json](summary.json), [관문 표](evidence/funnel.json), [실패 분포](evidence/setup-rejections.json), [파일 SHA](evidence/SHA256.json)에 남겼다. HOST_ERROR1은 첫 dependency import 실패이며 optimizer0스텝이다. 예산 IAM 전파 지연1, 의존 소스 누락1, torchcodec 빌드 변형 차이1을 보존하고 각각 복구했다. 학습·MJWarp 성공 검사는 반복하지 않았다.

## 예산·계정 경계

월 예산은 `projects/503325597974`만 필터하고 `INCLUDE_ALL_CREDITS`로 순비용1,000 KRW를 측정한다. CURRENT_SPEND50/100% 알림, 기본 결제 IAM 이메일 활성 → `projects/ugrp-sim-f-1016/topics/budget-stop` → Gen2 `budget-stop` / entry point `stop_on_budget` / `TARGET_PROJECT=ugrp-sim-f-1016`. 함수·requirements는 gcp4와 동일하다.

전용 `budget-stopper@ugrp-sim-f-1016.iam.gserviceaccount.com`에 이 프로젝트의 정지·Eventarc·호출 권한만 추가했다. 사람 IAM 구성원은 `kcm5781kcm5781@gmail.com` 하나이며 다른 계정 사용자에게 권한을 부여하지 않았다. Mac 기본 gcloud 계정 `changmin5781@gmail.com`은 유지한다. 모든 명령은 대상 계정·프로젝트를 명시한다. 첫 프로젝트 API/SSH0, gcp2/gcp3 기존 장치 변경0. gcp2 L4는 환경 조회·데이터 읽기와 자기 전송 임대만 사용했다.

e2-micro 시험은 Pub/Sub 이후 동작을 검증한다. 이메일 실제 수신·청구 집계 지연·실제 청구액은 미검증이다. 비용 집계가 늦을 수 있으며 VM 정지 뒤에도140GB 디스크·함수/빌드 저장소 비용은 남는다. 계정·프로젝트 추가를 추가 크레딧 지급으로 해석하지 않는다.

## 환경·자료

서울 `asia-northeast3-a`, STANDARD **g2-standard-8 / NVIDIA L4×1 /140GB pd-balanced**, 공개 고정 이미지 `deeplearning-platform-release/common-cu129-ubuntu-2404-nvidia-580-v20261001`. 사용자 "8시간 상한 — 이건 좀 없애라"에 따라 실행 시간 상한 없음. 유휴20분·`--no-service-account --no-scopes`·프로젝트 SSH 키 차단 유지. 새 개인키는 Mac `~/.ssh/ugrp_gcp6`에만 두고 공개키만 VM에 넣었다.

[setup_guest.sh](setup_guest.sh)로 공개 패키지를 새로 설치했다. C 비교 `/home/ugrp/ugrp-sim/ugrp/.venv-sim`, MJWarp `/home/ugrp/ugrp-sim/ugrp/.venv-warp`, ACT `/home/ugrp/ugrp-rl1b-act-env`. ACT115패키지 freeze는 gcp2와 전부 일치한다: torch2.11.0+cu128·torchvision0.26.0+cu128·numpy2.2.6·LeRobot `89236ea0f4f81a81ca566081e20dd1ff5f823cbe`, ACT modeling 원본 SHA `8d622935…93111`. CUDA 추가 인덱스가 고른 torchcodec0.10.0+cu128은 PyPI의0.10.0으로 맞췄고 최초 freeze·설치 스크립트·복구 명령을 보존했다. 모델 계산과 관계없는 이 패키지 교정 뒤 새 freeze·pip check·입력 소스/회수 해시를 다시 검사했다.

작업 중 `COORDINATOR_NOTE.md`의 19:00 지시로 첫 용도를 act16w 해석에서 **beamact3 C2 준비**로 바꿨다. gcp2의 완료된 `ops-reviews/actdiag/infer-final-v1/dataset-view`와 `ops-reviews/beamact2/data-v1/stages.json.zst`만 Mac SSH 스트림으로 전달했다(225.612초, Mac 원본 저장0). VM·디스크·환경·자격 증명을 복사하지 않았다. [원본](evidence/source-data-manifest.json)·[수신](evidence/target-data-manifest.json)·[전달 검증](evidence/data-transfer-verification.json).

[beamact_smoke.py](beamact_smoke.py)는 gcp6 자체 메타데이터를 확인하고, 커밋 `bbb757ad3…`의 의존 소스와 `train_shared.py` import·기존 B 모델 함수를 검사한다. 소스는9.1MB의 커밋 고정 의존 발췌이며 연구 checkout이나 Git 이력을 복사한 것이 아니다. 관리형 연구 실행기의 gcp2 host guard를 수정하거나 우회해 호출하지 않았다. **C2 구현·관리형 실행기의 gcp6 수용·본 학습은 beamact3 담당 작업에 남는다.** `act_smoke.py` 합성 대안은 실행하지 않았다.

## 사용·보존

```sh
python3 scripts/gcpctl.py start gcp6
# 기존 임대·PID·GPU 메모리 확인 후 자기 임대 생성
bash scripts/oracle_run.sh --host gcp6 WORKTREE RUN -- COMMAND
# 회수·해시 확인, 자기 임대만 제거, 다른 작업 없을 때만 정지
python3 scripts/gcpctl.py stop gcp6
```

기본 호스트는 gcp2다. 임대 JSON·VM당40개 파일 잠금 검사·GPU 메모리 확인·정지 거부 규칙은 gcp4와 같다. 상한 없는 호스트의 expected_end는 null이며 다른 임대 또는 ugrp Python/MuJoCo/ffmpeg가 있으면 수동 정지를 거부한다. 후속 source checkout은 `/home/ugrp/ugrp-sim/git-shared.git`을 직접 `--reference`하고 이 공유 저장소의 gc/prune를 하지 않는다.

원본은 `gcp6:/home/ugrp/ugrp-sim/setup/`와 전달된 dataset-view에 남긴다. 모델·optimizer·설치/실패 로그도 VM에 보존한다. Mac에는 작은 환경·감사·SHA·결과만 회수했다. 프로젝트 예외에 따라 로컬/GitHub에 기록하며 다른 프로젝트 결과와 합산하지 않는다. 인프라용 작은 구/바닥 스텝은 연구 장면·렌더·자기 카메라·교사/학생·E2E 관문을 대체하지 않는다.

## 절차 참고

2026-10-16 공식 문서 확인: [예산 Pub/Sub 알림](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications), [예산 생성·기본 이메일](https://docs.cloud.google.com/sdk/gcloud/reference/billing/budgets/create), [Gen2 함수 배포](https://docs.cloud.google.com/sdk/gcloud/reference/functions/deploy). [gcp4 준비](../2026-10-16-gcp4setup/README.md)를 기준으로 계정·결제·프로젝트를 바꿨다. PR #561의 CI·검토·병합은 인프라 READY와 구분한다.
