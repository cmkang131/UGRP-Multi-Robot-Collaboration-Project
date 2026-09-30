# outputs 보존 2차 — D1–D5 실행안, 실제 삭제 없음

**고정 재고 77.39 GiB → 53.65 GiB: 23.74 GiB, 파일 1,022,553개를 삭제 후보로 확정했다.**
동시 작업을 포함해 같은 작업 중 다시 잰 `du`는 **78.13 GiB**이며, 같은 목록을 적용하면
**54.39 GiB**다. 이는 예상값이며 실제 공간을 확보한 결과가 아니다. 40 GiB보다 약 14.39 GiB 크다.
1차의 3.48 GiB보다 후보가 약 20.26 GiB 늘었다. 두 배치를 합산해서 실행하면 안 된다.

사용자가 전달한 코디네이터 결정 D1–D5를 적용했다. 7일 미만·미병합 분석·test라는 이유만으로
폴더 전체를 보류하던 1차 기준은 이번 배치에 적용하지 않았다. 재생 가능성은 코디네이터가
제공한 판단 근거이며, 이 작업에서 새 물리 재생을 실행하지 않았다.

`/Users/changmin/projects/ugrp/outputs/`는 **읽기만 했다**. 이 에이전트는 삭제·이동·수정·압축·
새 TensorBoard 변환·Drive 접근을 하지 않았다. 실제 실행 담당자는 코디네이터다.
삭제·재개 테스트는 `/private/tmp/outputs-retention-r2/`의 가짜 outputs 트리에서만 했다.

## 용량과 삭제 기준

단위는 GiB, `du` 방식 **할당 바이트**다. JPEG/JSON의 논리 크기와 다르고, APFS 공유 블록 때문에
실제 `df` 확보 공간과도 같다고 보장하지 않는다. 하드 링크는 재고에서 한 번만 계산했고,
여러 경로로 연결된 파일은 전부 유지했다. 디렉터리는 지우지 않아 그 할당량도 예상 잔량에 포함된다.

| 규칙 | 삭제 후보 | 내용 |
|---|---:|---|
| D1 | 18.94 GiB | 모델 요청이 아닌 렌더 프레임을 SIM 약 1 Hz로 솎기. 시각 불명은 번호 순서 10% 이하 + 필수 처음·끝 |
| D2 | 3.60 GiB | 퇴역 realtime/sim-speed의 큰 캡처·큰 상세 로그·기타 bulk. 실행별 작은 기록 ≤5 MiB + 대표 영상 1개 보존 |
| D3 | 0.57 GiB | 1차 목록의 재설치 가능한 캐시만 적용 |
| D4 | 0 | 체크포인트 45개 모두 유지(Release 목록 불일치 39개), 09-07 유일 ZIP 유지 |
| D5 | 0.64 GiB | 남길 JSON과 전체 바이트 SHA-256이 같은 사본. 남긴 파일을 그대로 복사하면 복원됨 |
| **합계** | **23.74 GiB** | **1,022,553개 파일. 실제 삭제 0개** |

서로 겹치지 않는 파일 형식별 합계는 다음과 같다. 작은 디렉터리·링크 할당량은 별도이며,
전체 합계·폴더별 수치는 [summary.json](summary.json), [manifest.csv](manifest.csv)를 따른다.
[잔량이 큰 40개 폴더](remaining-largest.csv)도 별도로 정렬했다.

| 파일 종류 | 재고 | 삭제 | 예상 잔량 |
|---|---:|---:|---:|
| JPG/PNG 등 이미지 | 51.41 | 22.24 | 29.17 |
| JSON | 11.52 | 0.90 | 10.62 |
| JSONL | 3.38 | 0.04 | 3.34 |
| ZIP | 3.57 | 0 | 3.57 |
| 체크포인트 | 1.64 | 0 | 1.64 |
| NPZ | 1.37 | 0 | 1.37 |
| MJB | 1.02 | 0 | 1.02 |
| MP4 | 0.89 | 0 | 0.89 |
| 기타 파일 | 2.59 | 0.57 | 2.02 |

## 반드시 남기는 자료와 불확실성

- **최근 24시간 변경 14.72 GiB**는 보존한다. 조사 기준 시각·cutoff는 summary에 고정했다.
  실행기도 삭제 직전에 24시간을 다시 검사한다. `agent_lock`에는 출력 경로가 없어 살아 있는
  잠금 하나라도 있으면 배치 전체 실행을 차단한다. 조사 중 다른 작업의 잠금은 건드리지 않았다.
- 모델 요청 payload에서 이미지 해시 41,242개와 파일 경로 3,204개를 추출했다.
  요청·응답·텍스트와 실제 이미지 해시가 일치하는 사본을 모두 보존한다. 동일 픽셀 사본 중
  어느 경로가 실제 요청 원본인지 불명확하면 그 사본들도 남기는 보수적인 처리다.
- 모델 입력/학습 자료 연결이 완전하지 않은 이미지 **3.20 GiB**는 유지한다.
  여기에는 Jev/ACT 과거 입력과 위치 추정 학습·평가 자료가 있다. 단순히 `teacher`라는 단어가
  붙은 단계 probe는 학습 자료로 간주하지 않았고 D1을 적용했다.
- 추적 기록·문서·TensorBoard가 이름으로 참조한 이미지 **4.21 GiB**를 유지한다.
  main과 조사 당시 열린 PR들의 서로 다른 텍스트 blob 4,660개를 확인했다. 상대 경로만 적힌
  이미지 참조가 여러 실행과 대응되면 일치하는 사본을 모두 남겼다.
- 체크포인트 전체 파일 해시 45개 중 Release registry 일치 6개, 불일치 39개다.
  [checkpoint-audit.json](checkpoint-audit.json)에 모두 나열했다. 미등록 모델과 09-07 ZIP은
  코디네이터가 전달한 D4대로 후속 사용자 판단 전까지 유지한다. 새 Release 다운로드·로딩 검증은 하지 않았다.
- 순서·시각을 판단할 수 없는 단일 이미지 약 **0.12 GiB**, 하드 링크 자료,
  완전한 복원 방법을 입증하지 못한 기록·NPZ·MJB 등은 남겼다. 경로별 불확실성은 [uncertain.csv](uncertain.csv)에 있다.
- 큰 JSON의 대부분은 개별 프레임 사본 파일이 아니라 `robots.json`, `result.json`, `host.json`,
  요청 payload다. JSON 129,153개를 전체 바이트 해시로 대조했다. robots의 보고·발행 서보 값,
  host의 평가 배열, result의 소스·localizer 이력은 다른 JSONL 일부만으로 전체 파일을 복원할 수 있다고
  입증되지 않았다. D5는 **내용이 완전히 일치한 경우만** 적용했다([조사](json-audit-r2.json)).

따라서 이번 결정만으로 40 GiB 이하를 달성했다고 보고하지 않는다. 현재 보호분을 후보로
바꾸거나 시간이 지났다는 이유만으로 예약 삭제하지 않는다.

## 봉인·보고 코호트

최종 지도에서 네 통신 조건을 비교하는 **본 확증 코호트의 봉인·보고 완료 자료는 찾지 못했다**.
현재 후보·stage probe와 완료된 본 실험을 혼동하지 않았다. 추가로 다음 **이미 동결·보고된
구성요소 코호트 8개 경로, 합계 1.97 GiB**를 통째로 남겼다. 성공·실패·HOST_ERROR를 모두 포함한다.

- `m1-owncam-20260926/test` — 동결 SHA `ca2fdb8`, test 101–106.
- `owncam-memory-20260926/test-a1` — OFF/memory_v2 test 161–166.
- `zone-m2-pair-20260926/{stage1-3fdf011,stage2-fa682a6,stage2b-ed15489,stage3-5f74873}`.
- `zone-m2-pair-kiro-20260926/{stage2b-ed15489-completion,stage2c-ca44f66}`.

정확한 근거 파일은 [sealed-cohorts.json](sealed-cohorts.json)에 있다. 옛 태그 환경의 이 코호트를
현재 최종 지도 성공 증거로 승격하지 않는다. 그 밖의 test/cohort raw도 D1의 일반 대상에 포함했다.

## 솎기와 기록 구조

- [manifest.json](manifest.json): 실행용 v3 manifest. 삭제 목록과 보존 목록 파일의 SHA-256,
  수량·바이트 및 근거 파일을 고정한다. **1차 manifest를 대체하는 하나의 배치**다.
- [manifest.csv](manifest.csv) / [inventory.csv](inventory.csv): 최상위 폴더·은퇴 worktree별
  가산 합계. `folder-details/*.csv`에는 모든 개별 디렉터리의 before/after 바이트,
  삭제/보존 파일 수, 규칙과 솎기 설명을 넣었다. 각 shard 해시도 manifest에 묶었다.
- [thinning.csv](thinning.csv)는 `thinning/*.csv` 색인이다. 각 shard에 카메라 스트림·에피소드/leg/단계별 실제 규칙, 프레임 수,
  처음·끝 이름, 기록으로 측정한 SIM 간격. `robots.json`, `inputs/frames.jsonl`,
  `skill-inputs.jsonl`, 결정 기록의 SIM 시각을 우선했다. `tick-00001.0-*.jpg`는
  생성 코드 `scripts/eval_zone_rgb_outcome.py`의 SIM 시각임을 확인했다.
  구형 `robots/<rid>/inputs/frames.jsonl`에서도 frame 번호와 robot_id로 실제 경로를 연결해
  247,863건의 SIM 시각을 복원했다. 작업·leg·phase 전환 시각 앞뒤의 프레임을 추가 보존했다
  ([경계 조사](boundary-audit.json)). 경계 후보 15,045개 중 퇴역 D2 자료 1,047개는
  D2의 작은 기록·대표 영상 보존 규칙을 따라 삭제 후보에 남겼다. D1 경계 프레임과 삭제 목록의 겹침은 0개다.
- 시각이 불명확하면 파일 번호 순서로 간격 N을 정해 **10% 이하**만 표본으로 남긴다.
  단, 처음·끝 2장이 필요한 20장 미만 스트림과 별도 보호 이미지 때문에 최종 비율은 더 높을 수 있다.
  이미 1 Hz 이하인 스트림은 더 줄이지 않는다. wall 시간을 SIM 시간으로 대신 쓰지 않았다.
- `round2-delete/*.jsonl`, `round2-keep/*.jsonl`: 최대 512파일의 작은 묶음이다.
  이름 목록은 **명시적 파일명 JSON을 zlib+base64로 압축한 메타데이터**이며 원본 이미지 압축이 아니다.
  각 묶음의 `content_sha256`은 파일명·크기·mtime_ns·각 파일 전체 SHA-256을 이름 순서로
  canonical JSON 배열 `[name,bytes,mtime_ns,sha256]` + LF로 이어 SHA-256한 값이다.
  보존 목록에는 오래된 안정 파일 766,309개가 들어 있다. 최근/실행 중·인프라 파일은 삭제 대상에서도
  보존 해시 동결에서도 제외해 동시 기록을 방해하지 않는다.
- [json-reconstruction.csv](json-reconstruction.csv)는 `json-reconstruction/*.csv` 색인이다.
  각 행은 삭제 파일 → 보존 원본 → 전체 SHA-256 → 바이트 복사 복원 규칙이다. 모든 원본은 보존 목록에 있다.
- [retired-records.json](retired-records.json): 퇴역 실행별 ≤5 MiB 기록과 대표 영상 선택.
  모델 요청·기존 참조·최근 파일 등 보호 예외는 별도로 기록했다. 원래 영상이 없는 실행은
  `video: null`로 표시했고 새 영상을 만들지 않았다.

1차의 `inventory/*.json`, `keep/*.json`, `selections/*.json`, `*-audit.json.gz` 등은 **1차 조사 이력**이다.
현재 실행 대상은 v3 manifest가 참조하는 `round2-*` 목록뿐이다. 이전 초안은 Git `55df84d`에도 남는다.

## 대량 실행·중단 재개·검증

```sh
# 실제 원본에서 수행한 동작: 읽기 전용 검사
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json

# 실제 원본에서는 실행하지 않았음. 코디네이터가 위와 같은 manifest를 검토한 뒤 실행
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json --execute

# 중단 시: 동일한 manifest와 그 실행의 영수증만 사용
python3 scripts/outputs_prune.py experiments/2026-09-30-outputs-retention/manifest.json \
  --execute --resume /Users/changmin/projects/ugrp/outputs/prune-receipts/<receipt>.json
```

파일을 한꺼번에 메모리에 올리지 않고, 512개 이하 묶음을 스트리밍한다. 먼저 전체 삭제·보존 파일을
검증하고, 실제 삭제에서는 해당 묶음을 다시 검증한다. `--progress-every` 간격으로 stderr에 진행 수를
찍는다. 삭제는 열린 디렉터리 fd와 `O_NOFOLLOW`를 통해 정확한 파일명에만 수행한다.
새로 생긴 파일·목록 밖 파일·디렉터리는 삭제하지 않는다. 동시에 두 pruner가 실행되지 않게 파일 잠금을 쓴다.

묶음을 지우기 **전에** 각 파일의 해시와 inode/mtime을 담은 pending 기록을 fsync한다.
완료 묶음은 append journal에 fsync한다. 강제 종료 후에는 같은 manifest와 receipt만 허용한다.
완료 경로가 다시 생겼거나, pending 밖에서 파일이 사라졌거나, 남은 파일 내용이 바뀌면 거부한다.
중단 순간 지워졌지만 완료 기록을 못 쓴 파일은 `recovered_absent`로 구분해 합산한다.

영수증에는 폴더별 삭제 파일 수·바이트·현재 보존 파일 수, 삭제/부재 확인 경로 목록의 SHA-256
(`UTF-8 상대 경로 + LF`, manifest 순서), 중단된 묶음의 미완료 수가 남는다.
목록·보존 파일·24시간·활성 잠금 검사는 재개할 때도 생략하지 않는다.

임시 자료 테스트 **60건 통과**: 1 Hz·알 수 없는 시각의 10% 솎기·처음/끝 보존,
부분 묶음 중단·journal이 잘린 강제 종료·완료 재실행, manifest/내용 변경·재생성 경로 거부,
symlink 교체·동시 pruner·활성 잠금·새 파일 보존 등이다. 실제 원본 dry-run 결과는
[dry-run.json](dry-run.json), 최종 소스·검증 범위는 [verification.json](verification.json)에 기록한다.
[별도 목록 대조](plan-consistency.json)에서 21,238개 스트림, JSON 복원 연결 17,523개,
봉인 경로 8개와 모델 입력/삭제 목록의 겹침 0건을 확인했다.
GitHub CI 결과와 로컬 테스트, 실제 삭제는 별개다.

TensorBoard는 이벤트 **1,282,403개**, 이미지 항목 **1,386개**를 읽었고 읽기 오류는 0개였다.
이미지 원본 해시·파일명 참조와 기존 스냅샷/동영상은 보존했다([감사](reference-audit-r2.json)).
새 실험 결과가 생긴 작업이 아니므로 변환·뷰어 재시작·재등록은 하지 않았다.

재조사 도구는 `audit/round2_collect.py` → `round2_evidence.py` → `round2_tensorboard.py`
→ `round2_boundaries.py` → `round2_plan.py` → `round2_finalize.py` → `round2_check.py` 순서다. 임시 SQLite는 `/private/tmp/`에만 만들며,
raw 안에는 어떤 조사 파일도 쓰지 않는다. 실행기 자체는 이 후보 발견 코드를 실행하지 않는다.
