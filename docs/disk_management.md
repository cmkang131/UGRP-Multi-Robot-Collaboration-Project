# UGRP 디스크 사용 관리

2026-09-26 사용자 요청 "남은 게 중요한 게 아니라 이 프로젝트 자체가 너무 많이 잡아먹고 있다"에 따라 작성했다. 목표는 여유 공간 경보가 아니라 **프로젝트 자체의 사용량을 줄이고 작게 유지하는 것**이다. 수치는 `du` 기준 할당 크기(GiB)다. APFS clone은 전체 크기로 세므로 물리 사용량보다 클 수 있다. 측정 원본은 [사고 기록 폴더](../experiments/2026-09-26-disk-incident/footprint/)에 있다.

## 1. 한눈에 보기

| 구분 | 측정 (09-26 15:26) | 적용 뒤 측정 (16:05) | 제안 예산 |
|---|---|---|---|
| 기본 체크아웃 `outputs/` | 66.74 | 67.98 (Codex 은퇴분 0.82 유입, 다른 작업의 새 실행) | ≤ 40 |
| worktree | 78.07 (69개) | 63.04 (57개. 이 PR의 worktree 등 2개는 sparse) | ≤ 10 |
| 기본 체크아웃 나머지(`experiments/` 1.01, `.git` 0.96, `work/` 1.13 등) | 3.47 | 3.46 | ≤ 6 |
| 가상환경(`Project-Runtimes/ugrp`) | 1.12 | 1.12 | ≤ 2 |
| **프로젝트 합계** | **149.4** | **135.6** | **≤ 60** (58 + 여유 2) |
| 에이전트 상태(`~/.codex` worktree 제외, `~/.kiro`, `~/.claude`) | 6.55 | 6.77 | 예산 밖, 보고만 |

- 2026-09-26 18:24–18:54 사용자 승인 4항목을 적용했다. 결과·제외 목록·검증은 [적용 기록](../experiments/2026-09-26-disk-apply/README.md)에 있다. 아래 1–2절 수치는 그 전 측정이다.
- 처음 적용은 두 가지다.
  - 병합된 Codex-app worktree 14개를 은퇴시켜 checkout 14.38 GiB(추정)를 확보했다. 파일시스템 여유는 32.47 → 46.88 GiB로 늘었는데, 이 값에는 다른 작업의 쓰기가 섞여 있다.
  - 이 PR의 worktree를 sparse로 바꿔 1.05 GiB → 0.13 GiB가 됐다.
- 두 측정 사이에도 다른 에이전트의 새 실행·worktree가 늘었으므로, 차이 13.8 GiB는 순수 절감량이 아니다.
- 이 표는 09-26 측정이다. 현재 감축은 3–4절 v2의 로컬 유지·승인 후 삭제 규칙을 따른다.
- `outputs/`는 하루 5–15 GiB씩 늘었다(폴더 이름 날짜 기준 09-24 8.3, 09-25 15.1 GiB). 보관 주기 없이 정리만 하면 며칠 안에 다시 찬다.

## 2. 측정 결과 (09-26 14:42–15:49, 적용 전)

### 2.1 기본 체크아웃 `outputs/` (66.74 GiB, 497항목)

- 파일 종류별: 이미지 46.06 GiB(JPEG 106만 장, 평균 약 16 KB), JSON 11.42, 압축 3.91, 모델·배열 2.50, 영상 1.37, 기타 1.49.
- 큰 폴더: `retired-worktrees` 12.25, `simulation-realtime-20260923` 3.69, `jev-semantic-motion-20260921-v1` 3.52, `zone-rgb-outcome-v2-20260925` 3.42, `plan-guidance-20260925` 2.93, `experiment-archives-20260907` 2.71, `act-action-training-20260924` 2.60, `dynamic-team-recovery-20260925` 2.33.
- 연구 줄기별 분류(폴더 이름 기준 추정, 합계는 반올림):

| 줄기 | GiB | 비고 |
|---|---|---|
| `retired-worktrees` (9/7–9/20 worktree 보관분) | 12.25 | 9/23에 프레임 23.4 GiB 삭제 뒤 남은 결과·영상·모델 |
| 현재 연구: zone·owncam·M1·M2 | 10.74 | dev 4.23 / test 2.92 / 미분류 3.60 |
| Jev (9/21) | 10.49 | 보조 과제 |
| 계획·동적 협업·재파지·지도 (9/24–25) | 9.25 | |
| 실시간·시뮬레이션 속도 (9/23–24) | 5.92 | 현재 연구 대상 아님(사용자 방침) |
| RGB·파지 (9/10) | 5.71 | |
| dispatch·ACT·markerless·nav·pair | 8.18 | 9/8–9/24 |
| 9/7 실험 ZIP 보관분 | 2.71 | 9/22 정리로 비압축본을 지운 뒤 남은 **유일 사본** |
| TensorBoard·기타 | 1.49 | 스냅샷 98개 0.10 GiB + archive 0.26 GiB |

### 2.2 worktree (69개, 78.07 GiB)

| 위치 | 개수 | 합계 | 추적 checkout | 무시 `outputs/` | 캐시 |
|---|---|---|---|---|---|
| `~/.codex/worktrees` | 23 | 27.08 | 23.52 | 3.50 | 0.07 |
| `ugrp-wt/` | 42 | 44.54 | 43.86 | 0.58 | 0.10 |
| `ugrp-worktrees/` | 3 | 5.40 | 3.14 | 2.24 | 0.02 |
| 기타(`ugrp-kiro-agent`) | 1 | 1.04 | 1.04 | 0 | 0 |

- 전체 checkout 1개는 약 1.03 GiB다. 그중 0.93 GiB가 `experiments/`의 추적 미디어다(아래 2.3).
- 주인별: Claude 20개 23.19 GiB, Codex 23개 27.08 GiB, Kiro 26개 27.79 GiB.
- 15:49 기준 56개: 병합됐고 열린 PR 없음 19개(22.14 GiB), 열린 PR 22개(23.53 GiB), 미병합이며 열린 PR 없음 15개(18.14 GiB).
  - 미병합 15개는 Codex 9개(PR 없는 브랜치 6, detached 감사 2, 닫힌 PR #120 1)와 동결 소스 detached 6개다.

### 2.3 추적 `experiments/` (origin/main, 1.00 GiB)

- 종류별: zip 0.69 GiB(51개), gz 0.11(680), mp4 0.06(129), json 0.06(1,673), jpg 0.05(627), png·jsonl·xml 각 0.01.
- 무거운 미디어(sparse에서 빼는 종류) 합계는 0.93 GiB다. 대부분 9/10–9/17 증거 ZIP이다: `2026-09-10-rgb-short-approach` 347 MiB, `2026-09-10-rgb-varied-start` 157 MiB, `2026-09-13-rgb-short-transport` 111 MiB, `2026-09-13-pair-carry-sync` 76 MiB.
- 최근 기록은 작다. 9/20 이후 기록의 미디어는 실험당 최대 5.7 MiB(`2026-09-25-zone-cargo-catalogue`, 파일당 최대 0.5 MiB)다.
- 실행 코드가 읽는 추적 압축 파일은 두 개뿐이다: `experiments/dispatch-skill-integration-20260917/models.zip`, `experiments/2026-09-10-rgb-varied-start/models.zip`(`tests/test_agent_worktree.py`가 소스를 검사한다).

### 2.4 `.git`과 기타

- `.git` 0.96 GiB(pack 931 MiB). 과거 증거 ZIP이 이력에 있어 줄이려면 이력 재작성과 강제 push가 필요하다. 금지된 작업이므로 제안하지 않는다. sparse checkout은 `.git`을 줄이지 않는다(worktree끼리 공유).
- 새 clone에서는 `git clone --filter=blob:none --sparse`(partial clone)에 같은 sparse 패턴을 쓰면, 제외한 과거 증거 ZIP을 내려받지 않는다. 절감량은 측정하지 않았다.
- 기본 체크아웃의 무시 폴더: `work/` 1.13 GiB(Raspberry Pi 이미지 작업 공간), `.venv-dev` 0.26 GiB, `작업 증거/` 0.04 GiB.

### 2.5 실행 1회 크기

| 실행 | 크기 | 구성 |
|---|---|---|
| M1 자기 카메라 1대 에피소드 (`m1-owncam-20260926/test`) | 25–48 MiB (6회 평균 36) | wrist JPEG q90 640×480 5 Hz 1,414–2,748장(장당 약 16 KB) 23–43 MiB, `eval_only/` 0.9–2.1 MiB, 영상 1.8–2.8 MB는 별도 |
| 3대 dispatch LLM 실행 (`plan-guidance-20260925/legacy-1`) | 224 MiB | RGB 스킬 프레임 3,406장 187 MiB, LLM 요청·결정 61개 18 MiB, result.json 3.2 MB, 영상 1.9 MB |
| M2 2대 운반 단계 (`zone-m2-pair-20260926`) | 단계당 159–363 MiB | 프레임 76k장 1.36 GiB |
| 인식 평가 렌더 (`zone-rgb-outcome-v2-20260925`) | 3.42 GiB | JPEG 63k장 |
| TensorBoard 스냅샷 | 98개 106 MiB | 평균 1.1 MiB, 최대 38 MiB |
| 영상 | mp4 2,361개 1.37 GiB | 평균 0.6 MB |

### 2.6 중복

- **worktree마다 들어 있는 추적 미디어 사본이 가장 큰 중복이다.** 전체 checkout 68개 × 0.93 GiB ≈ 63 GiB다. Git은 같은 내용을 `.git`에 한 번만 압축해 둔다.
- `outputs/`와 큰 worktree의 1 MiB 이상 파일 중 내용이 같은 파일: 논리 2.70 GiB, 물리 추정 2.50 GiB. 종류별로 JSON 0.90, 재생용 `model.mjb` 0.76, ACT `model.safetensors` 0.34, zip 0.24, mp4 0.10이다. `retired-worktrees`와 다른 위치 사이의 중복은 논리 1.26 GiB다.
- TensorBoard는 raw 사본이 아니다. 스칼라·텍스트와 결정당 이미지 표본(최대 8장)만 담아 합계 0.36 GiB다.

## 3. 감축 계획 v2 (2026-09-30, 삭제 배치는 사용자 승인)

**09-30 3차 재작성:** PR #309의 2차 D1–D5 목록은 독립 검토에서 실제 학습·추론 입력과
보고된 수치의 원본을 삭제하는 반례가 확인되어 **실행 금지**다. 파일명에 `request` 등이
없다는 사실은 비모델 프레임이라는 근거가 아니다. 2차의 23.74 GiB를 현재 후보로 쓰지 않는다.
[3차 manifest와 검증 기록](../experiments/2026-09-30-outputs-retention/README.md)은 이전 목록에서
리뷰 제외 전체와 내용·참조 그래프의 보호 집합을 뺀 별도 배치다. 모든 JSON/JSONL/CSV
(gzip 포함)의 이미지 경로·해시, 외부 폴더를 가리키는 학습 데이터, 보고 수치를 계산한 분석기의
입력과 glob 디렉터리를 보존한다. 참조 해석 실패·동적 입력 연결 불명은 보존한다.
연구 줄기별 선택 삭제는 잃는 재검증 능력을 제시한 질문 목록이며 실행 목록이 아니다.
모델 입력·수치 근거를 포기하는 선택이나 새 배치 실행 승인은 코디네이터가 사용자에게 확인한다.
새 실행 캡처 기본값이나 과거 봉인 기록을 소급 변경하지 않는다.

v3 실행기는 큰 목록을 512파일 이하 묶음으로 검증·처리하고 진행 수를 출력한다.
중단된 v3 배치는 **같은 manifest와 영수증**으로 `--execute --resume <receipt.json>`을 사용한다.
미완료 묶음의 durable pending 기록을 검증하며, 완료 경로 재생성·내용 변화·의도 기록 밖 누락은 거부한다.
폴더별 삭제/보존 수와 삭제 경로 목록 SHA-256을 영수증에 남긴다. v2의 중간 실패를 자동 재개하지는 않는다.

UGRP는 외부 보관을 기본 경로로 쓰지 않는다. 자료는 **로컬 유지 또는 승인 후 삭제**한다.
09-26의 외부 이동 계획은 현재 계획에서 제외한다. 과거 조치·측정은 1–2절과 당시 기록에 남긴다.
이번 [전수 목록과 삭제 제안](../experiments/2026-09-30-outputs-retention/README.md)은 실행 전 초안이다.

1. `disk_report.py --sections outputs,retention`으로 재고를 잡고, main·열린 PR의 기록, 실제 manifest,
   모델 요청, TensorBoard, 대표 영상 원자료를 대조한다. 폴더 이름·파일 나이·TensorBoard 유무만으로 지우지 않는다.
2. 4절 우선순위로 분류한다. 모르는 것은 `KEEP (uncertain)`과 질문으로 남긴다. 목표 용량을 맞추려고 이 항목을 삭제로 바꾸지 않는다.
3. 삭제할 정확한 경로·바이트·내용 해시, 부분 정리의 파일 목록·보존 파일 해시, 예상 잔량을 고정한다.
   사용자는 **그 manifest 배치**를 승인한다. 정책 승인이나 PR 병합은 raw 삭제 승인이 아니다.
4. 승인 뒤 담당자가 `python3 scripts/outputs_prune.py <manifest.json>`을 먼저 확인하고 같은 파일에
   `--execute`를 붙인다. 기본 동작은 읽기 전용이다. 실제 삭제 파일·바이트·시각은 `outputs/prune-receipts/`에 남긴다.
   목록이 바뀌거나 검사가 실패하면 다시 조사한다. 실패한 배치를 묵시적으로 이어서 지우지 않는다.

도구는 공용 `outputs/` 밖, 심볼릭 링크, TensorBoard·잠금·삭제 영수증, 최근 24시간 변경,
크기·mtime·내용 해시 불일치, 보존 파일 변화/겹침을 거부한다. `agent_lock`에는 raw 경로 정보가 없으므로
살아 있는 잠금 하나라도 있으면 배치 전체 실행을 거부한다. 읽을 수 없는 잠금도 거부하며 직접 해제하지 않는다.
글롭은 설명에만 쓰고, 실행은 목록에 고정된 디렉터리 또는 파일명만 대상으로 한다.
`du`는 APFS clone 공유분도 전부 센다. 예상 `du` 감소를 실제 `df` 확보 공간으로 보고하지 않는다.

## 4. raw 보존 등급 v2

위에서 먼저 해당하는 보호 규칙을 적용한다. `test`와 `dev`가 섞인 폴더는 하위 실행별로 나누거나 전부 보존한다.

| 규칙 | 결정 | 기준 |
|---|---|---|
| K0 | 전체 유지 | TensorBoard 원본 이벤트·스냅샷·view 설정, agent-locks, 삭제/은퇴 영수증 |
| K1 | 전체 유지 | 주장 근거인 test/확증 코호트·봉인된 사전 등록 실행. 실패와 HOST_ERROR도 분모에서 빼지 않는다 |
| K2 | 전체 유지 | 실행 중·종료 여부 불명, 최근 24시간 변경. 7일 미만 자료와 분석이 미병합된 자료는 검토 대기 |
| K3 | 전체 유지 | 모델 요청/응답과 입력 이미지·텍스트(개발 실행 포함), 학습 표본, 결과에 쓴 미배포 체크포인트·설정·adapter |
| K4 | 전체 유지 | 버전별 대표 영상과 재렌더에 필요한 원자료, 보고서에 쓸 단계별 예시 프레임. 아직 대표 case를 못 고른 버전의 후보 raw |
| S1 | 부분 유지 | 분석이 병합된 오래된 dev/진단. manifest·JSON/JSONL·명령·지표·실패 요약·해시 목록·대표 영상·단계 예시를 유지하고, **모델에 보내지 않은** 대량 프레임/중복 영상만 후보로 올림 |
| S2 | 부분 유지 | 사용자가 연구 중단을 정한 실시간/속도 연구(T4)의 비모델 대량 캡처. K0·K2의 24시간·K3·K4를 계속 적용하고, 숫자 기록과 각 버전 영상은 남김. 과거 raw 재감사 범위가 줄어드는 것을 명시 |
| D1 | 삭제 후보 | 원본 경로·전체 파일 해시가 일치하는 중복 사본. 살아남는 쪽의 해시도 실행 직전 확인. 은퇴 폴더라는 이유만으로 중복 처리하지 않음 |
| D2 | 삭제 후보 | 재설치 가능한 캐시/의존성 설치본. 설정·lockfile·분석 로그·소스·최종 산출물은 유지 |
| D3 | 삭제 후보 | 미참조 smoke/scratch 또는 HOST_ERROR-only 실행: 열린 PR 참조·분모·실패 분석·모델 요청·고유 산출물이 없고, 종료·실패 기록을 남겼을 때만 해당 |
| U1 | 불확실 → 유지 | 출처·모델 입력 연결·보고서 필요성·진행 상태를 확정하지 못한 자료, 유일 사본 압축본 |

S1에는 **존재하는 커밋 SHA + 실제 설정 + seed**와 입력/환경 연결이 필요하다. 하나라도 빠지면
`slim-plus`로 작은 기록뿐 아니라 해당 bulk도 보류한다. 세 항목이 있어도 실시간 스케줄링·모델 호출·
물리 수치 차이 때문에 과거 JPEG/행동을 똑같이 재생성한다고 주장하지 않는다. 재실행은 과거 증거 복원이 아니다.
TensorBoard 스칼라와 표본 이미지는 원자료를 대체하지 않는다. 모델 Release도 학습 데이터 전체 백업이 아니다.
Release 등록만으로 지우지 않고 업로드·재다운로드·전체 파일 해시·로딩 기록을 확인한다.

보고서 최소 묶음은 **버전마다 전형적인 대표 영상 1개(실패도 포함)**, 그 case의 result/trace/robots/manifest,
새/이전 버전을 비교한 같은 case, 단계별 시작·중간·끝 예시 프레임, TensorBoard와 원래 수치 표다.
[대표 영상 색인](version_videos.md)의 미제작 행은 임의로 완료 처리하지 않는다. 그림에 쓸 버전/단계가 미정이면
그 후보 원자료는 U1이다. 삭제한 바이트의 해시를 남기는 것과 바이트를 보존하는 것은 다르다.

## 5. 캡처 설정 (앞으로의 실행)

AGENTS.md는 **실제 모델 요청의 이미지·텍스트 보존**을 요구한다. 그래서 먼저 프레임의 용도를 나눈다.

| 종류 | 예 | test 코호트 | dev·진단 |
|---|---|---|---|
| 모델 요청 입력 (LLM·ACT·학습 학생) | `team/*-request.json`, ACT 입력 | 바이트 그대로 전부 | 바이트 그대로 전부 |
| 규칙 기반 제어 입력 프레임 | 자기 카메라 추정기·RGB 스킬의 5 Hz JPEG | 전부 | 1 Hz 표본 + 결정·단계 전환 프레임. 나머지는 해시만 |
| 평가 전용 추가 캡처 | TOP·개관 이미지, `eval_only/` 렌더 | 저해상도 영상 1개 + 요약 프레임 | 영상만 |
| 실행 영상 | `execution.mp4` | 유지(약 2 MB) | 유지 |

- 같은 이미지를 요청 JSON(base64)과 프레임 폴더에 두 번 저장하지 않는다. 한쪽은 해시로 가리킨다.
- 추정 효과: M1형 dev 에피소드는 36 → 약 8–10 MiB, 3대 dispatch형 dev 실행은 224 → 약 40–60 MiB다.
- 2026-09-30부터 **새 dev·diag의 캡처 기준은 `dev_1hz_decisions_v1`**이다. test/봉인 실행은 `all_v1`을 유지한다. 연결된 러너에서는 프로필을 명시하고 실제 saved/frames를 확인한다. 아직 연결되지 않은 러너는 아래 표처럼 모든 프레임을 쓴다. 문서 변경을 런타임 절감 완료로 보고하지 않는다.

### 5.1 2026-09-27 결정과 공용 프로필

코디네이터가 전달한 2026-09-27 사용자 결정은 "dev만 1초 1장, test는 5장 유지, 결정 시점 프레임은 항상 저장"이다. 이를 `harness/frame_storage.py`의 버전 고정 프로필로 만들었다(테스트 `tests/test_frame_storage.py`).

| 프로필 | 쓰는 파일 | 허용 split |
|---|---|---|
| `all_v1` (기존 코드 기본값·test) | 모든 프레임. 09-27 이전 모든 러너와 test 코호트, 과거 사전 등록의 동작이다 | 모두 |
| `dev_1hz_decisions_v1` | 스트림(로봇 카메라·TOP)마다 1.0 SIM s에 주기 프레임 1장, 그리고 모든 결정 프레임 | `dev`, `diag`만. 그 밖의 split은 생성 시 `ValueError`로 거부 |

- 결정 프레임은 세 가지다: 제어기가 요청한 capture, macro 뒤의 capture, 제어기가 이벤트를 내거나 단계를 바꾼 프레임. 결정 프레임은 주기 시계를 움직이지 않는다.
- 파일을 쓰지 않은 프레임도 러너의 프레임 로그에 SIM 시간·sha256을 남긴다.
- 모델 요청 이미지(LLM·ACT·학습 학생)는 이 정책 대상이 아니며, 항상 바이트 그대로 보존한다.
- 러너는 실행 기록(manifest)에 `FrameStoragePolicy.record()`를 넣는다. 프로필 이름이 실행 번들 조건의 일부가 된다([실행 버전 관리](execution_versioning.md)).
- 예: `policy = FrameStoragePolicy('dev_1hz_decisions_v1', split='dev')`로 만든 뒤 프레임마다 `policy.decide(rid, now, decision=..., reason=...)['saved']`가 참일 때만 JPEG를 쓴다.

**공용 기록 계층 조사 결과:** 모든 러너가 거치는 공용 프레임 기록 계층은 main에 없다. 러너마다 JPEG를 직접 쓴다. 이번 변경은 정책 모듈과 테스트만 넣었고, 어느 러너의 기본 동작도 바꾸지 않았다. 러너별 연결은 아래 순서로 주인이 한다.

| 러너 (프레임을 쓰는 곳) | 쓰임 | 연결 방법 | 상태 |
|---|---|---|---|
| `harness/zone_own_team_host.py` `_capture_raw` (`frames_dir/<rid>/NNNNN.jpg`, 5 Hz) | 자기 카메라 실행기 3대 host: own-executor 스모크, vision-worker, 통합 러너(#229), 공동 운반(#235) | `OwnCamTeamHost(..., frame_profile=, split=)` 인자 추가. 주기 capture(`_physics_until`)는 `decision=False`로 넘긴다. `_decide_raw`의 capture와 macro 뒤 capture는 `decision=True`로 넘긴다. `on_frame` 중 `executor.events`가 늘어도 `decision=True`로 처리한다 | **보류**: 열린 PR #235(Codex)·#229(Kiro)가 이 파일을 고치는 중이라 병합 뒤 연결한다 |
| `scripts/run_m1_owncam.py` (`frames/NNNNN.jpg`) | M1 1대 배달 dev·test | `--frame-profile`(기본 `all_v1`)과 `--split`. test 사전 등록 명령은 바꾸지 않는다 | 미연결 |
| `scripts/run_zone_pair_dev.py`, `zone_pair_dev_runtime.py` (Codex 브랜치) | M2 공동 운반 dev | 위 host와 같은 방식 | **이번에 수정 금지**(Codex가 `ugrp-wt/codex-pair-grasp`에서 수정 중). 목록에만 남긴다 |
| `harness/rgb_skill_execution.py` (`rgb/<oid>-<label>.jpg`) | 3대 dispatch RGB 스킬(`plan-guidance` 등) | 관측 id를 스트림으로 쓴다. 스킬 단계 전환·LLM 결정 직전 관측은 결정 프레임 | 미연결 |
| `harness/task_stage_execution.py` (`rgb/<request>-<label>.jpg`) | 단계 요청 실행 | 요청마다 쓰는 이미지는 모델 요청 입력이라 **전부 유지**(정책 대상 아님) | 해당 없음 |
| `harness/rgb_communication_runtime.py`, `harness/camera_runtime.py` | RGB 대화·카메라 런타임(모델 요청) | 모델 요청 이미지라 **전부 유지** | 해당 없음 |
| `scripts/record_owncam_localization.py`, `experiments/2026-09-26-vision-loc/run_vl_teacher_render.py` | 위치 추정 학습·평가 데이터 | 학습 표본이라 **전부 유지** | 해당 없음 |
| `scripts/eval_zone_*`, `probe_*` | 인식 평가 렌더·진단 | 평가 표본은 전부 유지. 진단 probe는 러너 주인이 판단한다 | 미연결 |

- 효과(추정, 5 Hz 기준): 결정 프레임이 적은 구간에서 dev 프레임 파일은 약 1/5가 된다. M1형 dev 에피소드는 36 → 약 8–12 MiB다. 실제 비율은 연결 뒤 `record()`의 `saved/frames`로 확인한다.

## 6. 예산과 검토 시점 (2026-09-30)

- `outputs/` 목표 25–30 GiB, 상한 40 GiB. 프로젝트 합계 기존 상한은 60 GiB(worktree ≤ 10, 기본 체크아웃 나머지 ≤ 6, 가상환경 ≤ 2, 여유 2)다. 보호 자료 때문에 초과하면 부족분과 결정할 항목을 보고한다. 목표를 이유로 보호 조건을 무시하지 않는다.
- 실험 ID당 raw ≤ 2 GiB가 기본이다. 더 필요하면 사전 등록에 예상 크기(에피소드당 × 수)를 적고 사용자 승인을 받는다. 예를 들어 3대 자기 카메라 5 Hz 주 연구는 에피소드당 약 150 MiB라 test 48회에 약 7 GiB다.
- Git 미디어: `experiments/`에 파일당 1 MiB, 실험당 5 MiB. 20 MiB 초과 파일은 기존 hook이 거부한다.
- 세션 시작 하한: 여유 공간 10 GiB(`ugrp_session.py run`).
- 기록이 병합되고 실행 후 7일이 지난 dev·진단은 다음 수동 정리 때 후보로 올린다. 나이는 실행 manifest의 날짜를 우선하고, 복사·중복 제거 mtime을 실행 날짜로 바꾸지 않는다. 예약 작업·상시 감시는 만들지 않는다. 배치별 실제 삭제는 사용자 승인 뒤에만 한다.

## 7. 에이전트 규칙

1. **worktree 생성:** `python3 scripts/agent_worktree.py new <이름> --branch <kiro|claude|codex>/<주제>`를 쓴다.
   - sparse checkout이며 `experiments/`의 zip·gz·영상·이미지·pdf·html·npz를 빼고, 실행에 쓰는 `models.zip` 두 개는 남긴다.
   - 동결 소스는 `--detach --owner <에이전트>`로 만든다.
   - 에이전트당 등록 worktree가 8개 이상이면 거부한다. 넘겨야 하면 `--allow-over-cap --reason "<이유>"`를 쓴다.
   - sparse worktree에서 뺀 종류의 새 파일을 커밋하려면 `git add --sparse <경로>`가 필요하다. 크기 제한을 지킨다.
   - 기존 worktree는 주인이 `python3 scripts/agent_worktree.py sparsify <경로>`로 바꿀 수 있다.
2. **raw 위치:** 실행 raw는 기본 체크아웃의 `outputs/`(절대 경로 `/Users/changmin/projects/ugrp/outputs/...`)에 쓴다. worktree 안의 `outputs/`는 worktree와 함께 사라질 수 있다.
3. **병합 뒤 정리:** `python3 scripts/agent_worktree.py retire <경로>`로 계획을 본 뒤 `--execute`를 붙인다.
   - 무시된 `outputs/<이름>`은 기본 체크아웃의 같은 상대 경로로 옮긴다. 그 경로가 이미 있거나 `outputs/` 밖의 무시 파일(`MUJOCO_LOG.TXT` 등)은 `outputs/retired-worktrees/<주인>-<이름>/`으로 옮긴다(`--archive-layout`이면 전부 이쪽).
   - 옮기기 전후 모든 파일의 개수·바이트·sha256을 비교하고 같을 때만 `git worktree remove`를 실행한다. 목록은 `outputs/retired-worktrees/<주인>-<이름>/MANIFEST.tsv`, 영수증은 같은 폴더의 `RETIRED.json`이다. 불일치면 worktree를 남기고 실패 영수증을 쓴다.
   - 프로세스 cwd·열린 파일·명령줄이 그 경로를 가리키거나 60분 안에 바뀐 파일·git index가 있으면 거부한다(`--idle-minutes`). `sparsify`도 같다.
   - 미병합 작업은 HEAD를 원격 `codex/archive-<이름>-0926` 같은 보관 브랜치에 올리고 `--archive-ref <브랜치>`를 준다. `ls-remote`로 원격 SHA가 HEAD와 같을 때만 진행한다.
   - `git worktree remove`를 직접 쓰지 않는다. `--force`는 쓰지 않는다. `git status --porcelain`만 보고 지우지 않는다(무시 파일이 안 보인다).
   - 다른 에이전트의 worktree는 주인이나 사용자가 정한다.
   - Codex-app worktree(`~/.codex/worktrees/<이름>/ugrp`)도 같은 절차이며, 은퇴 폴더 이름은 `codex-<이름>`이다.
4. **Git 미디어:** `experiments/`에는 기록(JSON·Markdown·작은 그림)만 둔다. raw 프레임·영상·큰 로그는 `outputs/`에 두고 sha256을 기록한다. 경고는 `scripts/check_media_size.py`(pre-commit·CI)가 낸다.
5. **확인:** `python3 scripts/disk_report.py`(읽기 전용, 약 2–3분)로 사용량·예산·은퇴 후보를 본다.

## 8. 사전 등록 지침: 디스크 부족은 HOST_ERROR

2026-09-26 M1 test에서 s103·s104가 디스크가 가득 차 카메라 프레임을 쓰다 멈췄다(`OSError [Errno 28] No space left on device`). 예외 처리기가 `result.json`을 남겨, 사전 등록 문구대로라면 과제 실패로 집계된다. **M1 사전 등록은 소급해 고치지 않는다.** s103·s104 처리는 사용자·코디네이터 결정으로 남는다. 앞으로의 사전 등록에는 다음을 넣는다.

- 실행 중 `ENOSPC`(errno 28), `EDQUOT`(errno 122) 또는 "No space left on device"로 끝난 에피소드는 과제 결과가 아니라 **HOST_ERROR**다. `result.json`을 썼는지와 무관하다.
- HOST_ERROR는 공간을 확보한 뒤 같은 동결 소스·seed로 1회 재실행한다. 원 시도의 raw·로그는 지우지 않고 보고한다. 재실행도 HOST_ERROR면 결측으로 보고하고, 분모 처리 규칙을 미리 정한다.
- 시작 전 여유 공간 검사와 에피소드당 raw 예상 크기를 적는다. 집계기는 HOST_ERROR를 성공·실패와 다른 열로 센다.

```json
"host_error": {
  "match": ["OSError errno 28 (ENOSPC)", "OSError errno 122 (EDQUOT)", "No space left on device"],
  "applies_even_if_result_json_written": true,
  "action": "rerun once on the same frozen source and seed after freeing space; keep and report the failed attempt",
  "second_host_error": "report as missing; use the pre-registered denominator rule",
  "free_space_floor_gib": 10,
  "expected_raw_mib_per_episode": 150
}
```

## 9. 보관 대상 비교 (Google Drive는 사용하지 않는다)

| 방식 | 비용 | 장점 | 단점 |
|---|---|---|---|
| GitHub Release asset (모델과 같은 방식) | 무료. 릴리스당 asset 1,000개, 파일당 2 GiB 미만, 전체 크기·대역 제한 없음([GitHub 문서](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)) | 원격 보관. 기존 모델 배포 절차(manifest·재다운로드·해시 검증) 재사용 | **저장소가 PUBLIC이라 raw가 공개된다.** 업로드 시간이 걸리고 2 GiB 분할이 필요하다. 올린 뒤 회수를 보장할 수 없다 |
| 외장 디스크 | 1회 구매. 2026년 시세 1 TB 휴대용 SSD 약 $150–200(메모리 가격 상승기), HDD는 TB당 더 쌈. 구매 시점 가격 확인 필요 | 비공개. 빠름(USB 3.2 SSD 약 1 GB/s). 대용량 | 한 벌은 백업이 아니다(두 벌 권장). 수동 관리, 분실·고장 위험 |
| Git LFS | Free/Pro 계정에 저장 10 GiB·월 다운로드 10 GiB 포함, 초과분은 사용량 과금([GitHub 문서](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)) | Git 기록과 연결 | clone·fork·GitHub Actions의 다운로드가 모두 소유자 대역으로 계산된다. 공개 저장소에서 빠르게 소진된다. raw에는 권장하지 않는다 |

- 권장: raw 보관은 외장 디스크 두 벌(비공개)로 한다. GitHub Release는 공개해도 되는 선별 묶음(모델, 대표 영상)에만 쓴다.
- 어느 쪽이든 옮긴 뒤 해시를 대조하고 새 위치를 기록에 적은 다음에만 로컬 삭제를 사용자에게 제안한다.

## 10. 도구

```sh
# 새 sparse worktree (fetch 후 origin/main에서)
python3 scripts/agent_worktree.py new kiro-topic --branch kiro/topic
python3 scripts/agent_worktree.py new zone-x-s1-frozen --detach --owner claude --base <SHA>
# 기존 worktree 줄이기 (주인만)
python3 scripts/agent_worktree.py sparsify /Users/changmin/projects/ugrp-wt/<이름>
# 병합 뒤 정리: 먼저 계획, 그다음 실행
python3 scripts/agent_worktree.py retire /Users/changmin/projects/ugrp-wt/<이름>
python3 scripts/agent_worktree.py retire /Users/changmin/projects/ugrp-wt/<이름> --execute
# 미병합 작업: HEAD를 보관 브랜치에 올린 뒤
python3 scripts/agent_worktree.py retire <경로> --archive-ref codex/archive-<이름>-0926 --execute
# 읽기 전용 보고서
python3 scripts/disk_report.py --json /tmp/disk.json
# 미디어 경고 (pre-commit hook이 자동 실행; 기존 worktree는 한 번 설정)
git config --worktree core.hooksPath .githooks
python3 scripts/check_media_size.py --base origin/main
# 여유 공간 하한 무시(사유를 기록할 것)
python3 scripts/ugrp_session.py run --allow-low-disk <이름> -- <명령>
```

- `new`는 새 worktree에 `core.hooksPath=.githooks`를 worktree 설정으로 넣는다. 공유 설정과 다른 worktree는 바꾸지 않는다.
- `retire`의 영수증은 각 은퇴 폴더의 `RETIRED.json`과 `outputs/retired-worktrees/retirements.jsonl`이다.
- `ugrp_session.py run`의 하한은 `--min-free-gib` 또는 환경 변수 `UGRP_MIN_FREE_GIB`로 바꾼다. GitHub Actions에서는 기본으로 끈다.
