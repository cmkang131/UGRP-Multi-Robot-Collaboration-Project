# gcp2setup — 두 번째 프로젝트 시뮬레이션 호스트

2026-10-15 사용자 요청에 따른 인프라 이관 기록. 속도 우선이며 비용 최적화 작업이 아니다. 연구 관문·ACT 학습·새 코호트 결과로 사용하지 않는다.

## 결정과 검증 범위

사용자 원문: "gcp2에서 하면 될 거 같긴해", "아니다 별로 빨리 쓰는 거 같지 않아". 이번 지시: "첫 프로젝트는 이제 건드리지 않는다(시작·생성·삭제 금지, gcp1 디스크와 원본 보존)", "gcp1에 적용한 사용자 결정 24h를 후속 시뮬레이션 VM에 승계".

작업 브랜치 `claude/gcp2-host`는 fetch 후 `origin/main=580f37ebc3129984c0dc07d1f73ccfe92e273202`와 같은 HEAD에서 시작했다. 기존 미추적 실험 폴더를 보존했다. AGENTS.md는 수정하지 않았다. 첫 프로젝트에 gcloud/API/SSH 요청을 보내지 않았고 기존 gcp1 SSH 블록도 보존했다. gcloud 구성은 전환하지 않고 모든 실행 명령에 계정·프로젝트를 명시했다.

## 결과

- 비용 정지: 크레딧 포함 순비용 1,000 KRW 예산, 프로젝트 번호655795919803, Pub/Sub `budget-stop`, 함수의 대상과 VM 정지 IAM 권한 및 모든 zone 순회 코드를 확인했다. `e2-micro` 시험 VM으로 수동 발행 후 RUNNING → 9.019초 STOPPING → 55.517초 TERMINATED. 함수 로그의 `stop_all`과 일치한다. 시험 VM·디스크 삭제 후 목록 0을 확인하고 본 VM을 생성했다. 장치는 변경하지 않았다. 실제 청구 집계 지연과 VM 외 비용 정지는 이 시험의 범위가 아니다.
- 본 VM: `ugrp-sim-gcp2`, `asia-northeast3-a`, `n4-highcpu-64`, STANDARD, 400 GB Hyperdisk Balanced, 24h STOP. 서비스 계정 없음·scope 없음·프로젝트 SSH 키 차단, 시작 스크립트 바이트 일치와 유휴20분 타이머 active 확인. CPU Xeon8581C·64 vCPU. 디스크 배분은 [계획](disk-plan.json); 설치/실행 뒤 실측 사용 약8.2GB·여유406.7GB(십진 bytes 기준)는 `evidence/gcp2setup-final-guest.json`.
- 환경: Ubuntu24.04 공개 이미지 → apt(`python3.12-venv`, `libosmesa6`, `libgl1`, `libglfw3`, `ffmpeg`, `fonts-noto-cjk`, `rsync`, `zstd`) → `~/ugrp-sim/ugrp/.venv-sim` → `requirements-sim.txt`와 SciPy1.17.1. Python3.12.3, MuJoCo3.12.0, NumPy2.5.2, OpenCV-headless5.0.0.93, Pillow12.3.0은 저장된 gcp1 관리 매니페스트와 일치한다. 전체 전이 의존성·OS 라이브러리의 gcp1 lock은 없으므로 전체 동일성은 미확인이다. gcp2 전체 pip freeze와 Mesa25.1.7 등을 기록했다.
- 소스: 공용 `git-shared.git`을 처음부터 만들었다. c1f02ac0·4a69e6bc 두 사본 모두 `--reference`로 이 공용 저장소를 직접 참조한다. 사본별 `.git/objects`는43 bytes(대체 저장소 경로 파일), 전체 이력을 사본마다 복사하지 않았다. 공용 저장소 자동gc/maintenance는 off; 삭제·gc/prune 금지. 첫 작업트리는 실제1.3GiB여서 사본0.9GB 가정 대신 디스크 계획을 갱신했다.
- 자격 증명: 전용 SSH 개인키는 Mac `~/.ssh/ugrp_gcp2`에만 생성했다. VM의 `.ssh` 파일은 공개 `authorized_keys`뿐이고 gcloud·Kaggle·`.env`·Claude/Codex 설정 경로가 없음을 확인했다. 모델 호출0·학습0·Mac 물리/렌더0·화면 앱 실행0. 키 값이나 인증 파일을 전송하지 않았다.

## 동시16, 첫30 SIM초

실행 소스 `c1f02ac0a81f50d0235823a845c31f1d4116c9e9`, 기존 `teacher-gate-plan.json`의0–15번, visible_only·`--probe --cap-s 30`, OMP/OpenBLAS/MKL/LP 스레드1, MUJOCO_GL=osmesa. 교사·계획·관측·제어 코드를 바꾸지 않았다. `host_probe.py`는 실행 전 커밋8e9979c8에 고정했고 호스트 측정/기록만 담당한다. 새 탐색 예산·파지 상수·제어 경로·실패 분석을 추가하지 않았다.

| 근거 | 중앙 wall/SIM | 최대 | 실행 |
|---|---:|---:|---:|
| gcp1 사용자 제공 최근 범위 | 2.35–2.66 | 미대조 | 소스별 별도 기록 |
| gcp1 동일c1f02ac0 저장 벤치마크 | 2.486 | 2.701 | 16 |
| gcp2 이번 실행 | **2.938138** | **3.241852** | **16/16** |

gcp2는 같은 소스의 과거 중앙값보다18.2% 느리다. 원인은 미확인이다. 기존 경고3.5·차단6.0 기준을 통과했다. 16회 모두30 SIM초 상한까지 완료한 `cap_end`로 표시했고 HOST_ERROR0이다. 성공률 관문으로 집계하지 않는다. 원본1667파일 SHA 검증에서 불일치0, Mac 요약의 해시도 일치했다. 실패·HOST_ERROR를 제외해 시간을 계산하지 않았다(해당 항목0).

[관문별 누적 통과 표](evidence/speed16/funnel.json): 계획16 → 시작16 → 정상완료16 →30 SIM초16 → 결과/속도16, 거부0. 이 표는 호스트 확인용이며 교사 성공률 관문과 다르다. 조정자 전달 기록의 `rejection_table`에 이 파일의 절대경로를 연결한다.

## 렌더 바이트

`4a69e6bc1fb5d07ccf6b0e2e552140d9e839af9b`의 `scripts.run_grasp_act_release`와 저장된 `release_gate-74039` 계획을 재생했다. 옵션은 commands/backoff_v3/zone/pad_window_v2/hidden_v1, cap90 SIM초, 스레드와 렌더 백엔드는 위와 같다.

r1·r2 자기 카메라와 평가용 개요 JPEG16/16의 SHA-256이 gcp1 원장과 같았다. 초기0/1/2초의9장을 먼저 고정하고, Mac에 남은 원본을 카메라별 이름순으로 최대3장씩 골라 겹치는1장을 제외한7장을 추가했다. gcp1 원본8장은 원래 매니페스트와 직접 대조했다. 나머지8장은 보존된 gcp1 매니페스트가 비교 근거다. gcp2의16장을 Mac에 개별 회수한 뒤 다시 해시를 확인했다. 선택 과정과 각 해시는 `evidence/gcp1-render-reference.json`, `evidence/gcp2setup-render-comparison.json`에 있다.

전체 장면/전체 프레임 동등성·재생 일반성은 검증하지 않았다. 같은 머신 종류·선택 프레임 일치여도 새 호스트 결과는 gcp1과 합산하지 않는다. replay의 성공 표시는 단일 진단이며 새 교사 관문 승계가 아니다.

## 재현과 원본

```sh
# 새 출력 디렉터리 사용; 사용자 승인된 호스트에서만 실행
python3 host_probe.py --source /home/ugrp/ugrp-sim/src/c1f02ac0a81f50d0235823a845c31f1d4116c9e9 --out /home/ugrp/ugrp-sim/runs/NEW_SPEED_RUN
MUJOCO_GL=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 LP_NUM_THREADS=1 .venv-sim/bin/python -m scripts.run_grasp_act_release --plan /home/ugrp/ugrp-sim/gcp2setup-render-plan.json --episode 0 --out /home/ugrp/ugrp-sim/runs/NEW_RENDER_RUN/raw --cap-s 90 --own-pose-source commands --observe-mode backoff_v3 --zone-slots zone --reach-mode pad_window_v2 --held-object hidden_v1
```

- 속도 원본: `gcp2:/home/ugrp/ugrp-sim/runs/gcp2setup-speed16`와 실행 소스의 `outputs/simulation-runs/` 표준 기록. 각 실행 결과 경로·해시는 [summary.json](summary.json)에 전부 있다.
- 렌더 원본: `gcp2:/home/ugrp/ugrp-sim/runs/gcp2setup-render39/raw`; 전체 파일 원장은 `evidence/gcp2setup-render-sha256.json`.
- Mac 선택16장: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/gcp2setup/render-frames/`. 전체 원본은 회수하지 않았다. 대량 원본은 gcp2 영속 디스크에 남고 ARM 백업은 없다.
- 로컬 검사: `tests/test_gcp_host.py` 7 passed, `git diff --check` 통과. 실제 VM 플래그·시작 스크립트·환경·직접 alternates·수동 정지 시험은 별도 실증했다. CI/검토/병합은 PR 상태로 구분한다.
- 최종 정지·조정자 전달·PR은 [summary.json](summary.json)에 기록한다. 다른 연구 대기열은 제출하지 않았다. AGENTS.md와 첫 프로젝트는 변경하지 않는다.

## 참고 자료

2026-10-15 공식 원문 열람: [Compute Engine 실행 시간 제한과 STOP](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime), [Cloud Billing 예산의 Pub/Sub 알림과 지연](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications), [Git clone --reference와 alternates 보존](https://git-scm.com/docs/git-clone). 공식 문서는 설정 의미·보존 의무의 근거이고 실제 작동은 위 gcp2 시험으로 따로 확인했다. [이전 소스별 벤치마크](../2026-10-14-gcp-sim-bench/summary.json), [Ubuntu 설치](../../docs/ubuntu_quickstart.md), [GCP 운영](../../docs/gcp_simulation.md)도 참고했다.
