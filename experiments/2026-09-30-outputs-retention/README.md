# outputs 보존 v2 조사 — 삭제 전 초안

**76.91 GiB 중 이번 확정 후보는 3.48 GiB다. 승인 후 예상 잔량은 73.42 GiB로,
요청한 40 GiB에 도달하지 못한다.** 40 GiB까지 추가 33.42 GiB, 25–30 GiB까지
추가 43.42–48.42 GiB를 줄여야 한다. 불확실한 원자료를 삭제로 바꿔 목표를 맞추지는 않았다.

이 작업은 `/Users/changmin/projects/ugrp/outputs/`를 읽기만 했다. 삭제·이동·압축·수정·
새 스냅샷 생성·Drive 접근은 하지 않았다. `--execute`는 실제 원자료에 실행하지 않았다.
단위 테스트의 삭제는 `/private/tmp/ugrp-retention-pytest/`의 가상 자료에서만 수행했다.
이 문서와 manifest는 **배치 승인을 받기 위한 초안**이며, 실행 담당자는 코디네이터다.

## 측정과 예상 잔량

09-30 19:57 KST `disk_report.py --sections outputs,retention`은 76.908916 GiB,
795개 최상위 항목을 보고했다. 이어진 파일별 조사는 2,632,454개 파일/디렉터리 항목,
76.909000 GiB였다. 두 측정은 동시 작업 때문에 원자적 스냅샷이 아니며 차이는 약 88 KiB다.
이후 새 자료가 생길 수 있으므로 이 값을 현재 파일시스템의 고정 크기로 읽지 않는다.

단위는 **GiB, `du` 방식 할당 바이트**다. 하드 링크는 한 번만 센다. APFS clone 공유분도
각 경로에서 계산하므로 아래 절감량은 `df`의 실제 확보 공간을 약속하지 않는다.

| 분류 | 현재 | 조치 | 예상 잔량 | 이유 |
|---|---:|---|---:|---|
| 최근·분석 미병합·날짜 불명 자료 | 32.10 | 유지 | 32.10 | 24시간/7일 보호와 열린 분석 |
| 시험·사전 등록 관련 표식이 있는 자료 | 18.40 | 유지 | 18.40 | 확증/보고 범위를 확정하기 전 보수적으로 보호 |
| 모델 요청·학습·체크포인트 포함 자료 | 13.50 | 유지 | 13.50 | 실제 모델 입력 연결과 미배포 모델 보호 |
| 퇴역 실시간 연구 | 3.69 | 부분 정리 | 0.78 | 비모델 반복 JPEG 49,684개만 후보 |
| 캐시가 섞인 ACT/보고 영상 작업 폴더 | 3.48 | 부분 정리 | 2.91 | 설치본/캐시 0.57만 후보; 모델·소스·영상 유지 |
| TensorBoard·대표 영상 원자료·작은 기록 | 2.05 | 유지 | 2.05 | 수치/영상/출처 보존 |
| 09-07 유일 압축본·기타 불확실 자료 | 3.68 | 유지 | 3.68 | 대체 사본 또는 폐기 근거 미확정 |
| **합계** | **76.91** | **3.48 정리 후보** | **73.42** | **40 GiB 목표 미달** |

앞 세 행만 64.00 GiB다. 이는 폴더 전체를 보호한 현재 분류의 합이며, 전부 필수 raw라고
독립 검증했다는 뜻은 아니다. 보고서 범위와 모델 입력 연결을 더 좁혀 확인해야 다음 배치를 만들 수 있다.
수치 기록이나 TensorBoard가 있다는 사실만으로 원자료가 불필요하다고 판단하지 않았다.

## 실제 삭제 목록과 보존 목록

- [manifest.json](manifest.json) / [manifest.csv](manifest.csv): 257개 작업, 파일 63,553개,
  논리 크기 3,593,677,729바이트, `du` 예상 감소 3,741,364,224바이트.
- `selections/01.json`–`19.json`: 실시간 19회 실행의 **정확한 삭제 파일명**과 보존 파일명.
  `*.jpg`는 설명용이며 실행기가 새 파일을 글롭으로 주워서 지우지 않는다.
- `keep/01.json`–`05.json`: 남길 manifest/JSON/JSONL/명령/로그/소스/설정/영상/표본 7,899개의 크기와 SHA-256.
  manifest가 이 목록 파일 자체의 해시도 고정한다.
- [inventory.csv](inventory.csv)와 `inventory/*.json`: 최상위 795항목과 은퇴 폴더 내부 85항목.
  `retired-worktrees` 행은 **비가산 소계**(`non_additive=true`)다. 총합에는 하위 항목만 더한다.
- [uncertain.csv](uncertain.csv): 불확실한 587항목을 모두 `KEEP (uncertain)`으로 남기고 Q1–Q5를 연결했다.

실시간 19회는 result의 SHA가 실제 Git 커밋으로 존재하고, config·seed 11·저장 계획 경로가 있다.
`llm_calls=0`, `carry_act_model=null`을 확인했다([실행별 근거](run-evidence.json)).
모델 요청/응답 JSON과 그 안에서 가리키는 이미지, 계획/참조 이미지, 모든 실행 영상,
각 pair 단계/카메라 및 solo 단계의 처음·중간·끝 표본 **4,405장**을 유지한다.
문서에서 요구한 RGB 규칙 제어 캡처와 모델 요청 입력을 구분한 후보다.

실시간 스케줄링 때문에 SHA+config+seed가 같아도 과거 픽셀을 정확히 재생성한다고 주장하지 않는다.
S2를 승인하면 삭제된 프레임의 원본 RGB 재감사 능력은 잃는다. 기존 수치·명령·실패·영상과 해시는 남는다.
이번 배치는 모델 입력, confirmatory/test raw, 새 버전의 대표 case 후보에는 삭제를 제안하지 않는다.

캐시는 Python `__pycache__`와 `status-video/remotion/node_modules` 안의 검증된 238개 디렉터리다.
심볼릭 링크가 있는 패키지 등은 [제외 목록](cache-exclusions.json)에 남겼다.
`package-lock.json`, 제작 소스, 최종 MP4와 체크포인트는 유지한다.
미참조 smoke/HOST_ERROR는 종료·모델 입력·분모 관계를 확정하지 못한 경우 그대로 보존했다.

## 기록·TensorBoard·모델 대조

`origin/main@6594536b1a1afec6d9d109b35dd85a8426142d01`과 당시 열린 PR 12개(#285,
#292, #293, #295, #299–#306)의 정확한 head SHA는 manifest의 `source_refs`에 있다.
폴더 이름으로 `git grep -l -I -F`를 실행해 `experiments/`, `docs/`, `configs/`,
추적 view 경로를 조사하고 실제 `outputs/tensorboard-view.json`도 읽었다.
같은 blob은 재사용하고 달라진 blob만 다시 조사했다. [참조 색인](references.json.gz)은
출처 파일/행과 ref ID를 연결한다. 이름을 구성하는 동적 경로는 놓칠 수 있으므로 미참조는 삭제 증거가 아니다.

`claim_evidence`, test/prereg 표식, 상태 문자열은 **보호를 위한 신호**다. 모든 README의 주장·봉인·
진행 상태를 독립적으로 인증한 것은 아니다. 확정하지 못한 항목에는 질문을 붙였다.
날짜는 실행 시작 시각으로 꾸미지 않고 폴더 날짜 또는 `mtime_not_run_date`로 구분했다.
09-26/27 APFS 정리가 mtime을 바꾼 자료도 있어 mtime을 과거 실행 날짜로 역산하지 않는다.

- TensorBoard: 기존 manifest 3,531개를 읽고 EventAccumulator로 **3,529개 스냅샷의
  scalar sample 1,197,721개**, 읽기 오류 0을 확인했다([감사](tensorboard-audit.json.gz)).
  여러 스냅샷의 중복 수치가 포함되며 독립 실험 수가 아니다. 각 inventory 행은 경로가 연결된
  스냅샷/스칼라 수를 갖는다. 과거 worktree 이동 경로는 현재 raw 해시 일치까지 보증하지 않는다.
  모든 `tensorboard*`와 view 설정을 보호했다. 새로운 실험 결과가 아니므로 재변환/뷰어 재시작은 하지 않았다.
- 보고서: [대표 영상 색인](../../docs/version_videos.md)의 원자료를 보호했다.
  b-v6g/v6h, 파지·내려놓기 등 아직 영상이 없는 행은 미완료 그대로 두었다.
  이번에 선택한 실시간 표본/영상과 현재 연구의 보존 raw에서 보고서용 장면을 고를 수 있다.
- 모델: 체크포인트 45개를 해시했고 6개만 현재 배포 registry의 파일 해시와 일치했다.
  나머지 39개는 같은 크기라는 이유로 대체/삭제하지 않았다([해시 목록](checkpoint-audit.json)).
  GitHub의 3개 Release 태그에 있는 4개 모델 ZIP은 크기·digest가 registry와 일치했다
  ([조회 결과](release-audit.json)). 이번에 새 다운로드/모델 로딩은 하지 않았다.
  과거 재다운로드·전체 해시·로딩 검증은 기존 배포 기록과 구분한다.
- 중복: 은퇴 폴더의 **1 MiB 이상 일반 파일**을 같은 크기의 비은퇴 파일과 전부 SHA-256 대조했다.
  일치 사본은 0개였다([범위와 결과](duplicates.json)). 작은 파일까지 중복이 없다는 뜻은 아니다.

## 추가로 결정할 항목

| 질문 | 결정이 필요한 내용 | 그 전 조치 |
|---|---|---|
| Q1 | 최근 7일 및 미병합 분석 자료를 언제 분석 완료로 볼지, 대표 case를 어느 것으로 고를지 | 유지. 특히 v6h·door·stage probe는 아직 열린 분석이 있음 |
| Q2 | 최종 보고서가 과거 Jev/ACT/RGB/지도·시험 결과 중 무엇을 수치/그림 근거로 쓸지 | 관련 raw 유지. 실험 중단과 과거 주장 근거 폐기는 같은 결정이 아님 |
| Q3 | 미등록 체크포인트 39개 중 실제 결과에 쓰인 모델/필수 자산이 무엇인지 | 식별과 필요한 Release 검증 전 유지 |
| Q4 | 유일 사본인 09-07 ZIP 2.71 GiB의 과거 결과를 포기할지 | 유지. 외부 보관을 해결책으로 전제하지 않음 |
| Q5 | 나머지 자료가 재생성 가능한 비모델 dev인지, SHA/config/seed·입력 연결이 충분한지 | `slim-plus`: 작은 기록과 bulk 모두 보류 |

경로별 질문과 크기는 uncertain.csv에 있다. 우선 zone-rgb-outcome-v2(3.42 GiB),
plan-guidance(2.93), dynamic-team-recovery(2.33), 현재 pair/own-camera 자료부터 범위를 좁히는 것이 필요하다.
새 40 GiB 이하 배치를 만들려면 보호 대상과 비모델 캡처를 하위 실행/파일 단위로 더 분리해야 한다.
현재 manifest는 이 추가 판단이 이뤄졌다고 가정하지 않는다.

## 실행기와 검증 범위

`scripts/outputs_prune.py`는 기본적으로 dry-run이다. **사용자가 이 manifest 배치를 승인한 뒤에만**
코디네이터가 같은 파일로 실행한다.

```sh
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json
# 아래 명령은 이번 작업에서 실행하지 않았다. 사용자 배치 승인 후 담당자가 실행한다.
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json --execute
```

경로 이탈·심볼릭 링크·24시간 변경·실행 잠금·크기/mtime/전체 내용 해시 변화·보존 목록 겹침을 거부한다.
모든 후보를 먼저 검사한 뒤 항목마다 다시 검사하며, 디렉터리 fd를 통해 명시한 항목만 삭제한다.
도중 실패는 `partial_failure` 영수증으로 남긴다. 성공 끝에는 보존 파일 해시도 다시 확인한다.
실행 잠금에 raw 경로 범위가 없으므로 살아 있는 잠금은 배치 전체를 막는다.

임시 폴더 회귀 **38건 통과**(약 1초): 경로·보호 영역·symlink·최근 변경·동일 크기 내용 변경,
실행 잠금/불명 잠금, keep/selection 목록 해시, dry-run 불변, 실제 temp 삭제와 영수증,
중간 OS 오류, 검사 뒤 삽입을 확인했다. 공용 outputs에 테스트 잠금을 만들지 않기 위해 관련 소스와
테스트를 `/private/tmp/ugrp-retention-tests/`로 복사했고 원본과 해시 일치를 검증했다.
전체 CI·실물·시뮬레이션·모델 재로딩 성공으로 확대하지 않는다.

[실제 dry-run](dry-run.json)은 257개 작업과 바이트를 확인했으며, 당시 다른 작업의 physics 잠금으로
실행 차단 사유를 표시했다. 테스트 영수증은 임시 폴더에만 있고, 실제 `outputs/prune-receipts/`는 만들지 않았다.

새 dev/diag의 문서 기준은 `dev_1hz_decisions_v1`로 정했다. 다만 공용 정책을 주요 러너에 연결하는
작업은 아직 남아 있다. 이번 문서 변경을 실행기의 저장량이 이미 줄었다는 증거로 보고하지 않는다.

`audit/`은 이 조사에서 쓴 읽기 전용 수집/계획 작성 코드다. 임시 SQLite는 파일 메타데이터만 포함하며
약 0.9 GiB라 커밋하지 않는다. 승인 없는 자동 분류/삭제 작업이나 예약 작업은 만들지 않았다.

## 참고 자료

- [디스크 관리 v2](../../docs/disk_management.md), [AGENTS.md](../../AGENTS.md),
  [TensorBoard](../../docs/tensorboard.md), [모델 배포](../../docs/model_artifacts.md),
  [대표 영상](../../docs/version_videos.md).
- [09-23 실시간 실행 기록](../2026-09-23-realtime-dispatch/README.md),
  [09-26 속도 연구](../2026-09-26-sim-speed/README.md),
  [09-27 디스크 정리](../2026-09-27-disk-cleanup/README.md),
  [09-24 모델 다운로드/로딩 검증](../2026-09-24-model-release/verification.json).
- 이 기록의 `disk-report.json.gz`, `metadata-audit.json.gz`, `references.json.gz`,
  `tensorboard-audit.json.gz`는 이번에 만든 조사 메타데이터다. 기존 raw를 압축하거나 대체한 것이 아니다.
