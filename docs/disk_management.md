# UGRP 영상·증거 저장 규칙

2026-10-11 사용자 결정: 저장 공간을 다 쓴 뒤 회수·정리하지 말고, 배치 제출 전에 공간을 확보한다. 10/10 x86 tmpfs 원본 소실과 10/11 egomap66/67 전체 회수로 Mac 디스크가 찬 사고를 반영한다. egomap 36실행 약 15 GB 중 94%가 프레임별 비압축 JSON/JSONL이었다(사고 배치 관측치이며 모든 실행의 고정 예산은 아니다).

이력: 2026-10-04의 이미지 원본 보존·최근 3일 규칙은 10/11의 PR 수명·dev/milestone/study 규칙으로 대체·통합했다. 이전 측정과 규칙 원문은 Git 이력에 남아 있다.

## 1. 위치: 실행 → ARM 보관 → Mac fetch-lite

- 원본은 **실행 호스트의 영속 디스크**에만 쓴다. tmpfs·ramfs·`/dev/shm`·`/tmp`·`/run`은 금지한다. 임시 x86 서버 종료 전에 회수·해시 검증을 완료한다. 영속 디스크 하나는 독립 백업 두 벌을 뜻하지 않는다.
- x86 기본 실행 경로는 `~/ugrp-sim/runs/<batch-or-run>/`. 평가 결과와 해시 목록을 남긴 후 ARM `~/ugrp-archive/runs/`에 자동 아카이브한다. 기존 SSHFS 마운트 `~/ugrp-sim/arm`을 재사용한다. 로컬 사본 제거는 전체 복사·검증 뒤에만 하며 원래 경로에는 링크를 남긴다.
- ARM은 stock-bot 호스트다. **복사 후 여유 25 GiB**를 지킨다. `~/stock-bot`·crontab은 건드리지 않는다. 아카이브는 실패 시 x86 사본을 남긴다. `.incoming-*` 미완료 복사는 재시도 전에 확인하며 자동 덮어쓰기·삭제하지 않는다.
- Mac은 **fetch-lite만** 회수한다: summary/판정, 가벼운 원장, LLM 요청·응답 텍스트, 명령 궤적, 모든 파일 해시 목록, 압축 매니페스트, 버전별 대표 영상 1개와 그 데이터. 원본 전체 `rsync`·tar 회수는 금지한다. 진단에 꼭 필요한 파일만 해시와 함께 개별 회수한다.
- fetch-lite는 경로 목록 `FETCH_LITE.txt`를 실행 담당자가 명시적으로 만든다. 큰 trace를 와일드카드 `*.json*`로 포함하지 않는다. 먼저 총 크기로 Mac 예산을 검사하고 `rsync -a --files-from=FETCH_LITE.txt oracle:ugrp-archive/runs/<run>/ <local>/`로 회수한다. 회수 목록·출처·전체 해시를 실험 기록에 연결한다. 대표 데이터의 범위는 아래 `keep`에 기록한다.
- Git에는 `experiments/<ID>/`의 작은 요약·판정·검증 기록만 둔다(미디어 파일당 1 MiB, 실험당 5 MiB). raw 위치·해시·미회수 상태를 적으며 로컬 보관을 원격 백업으로 표현하지 않는다. Google Drive는 사용하지 않는다.

## 2. 등급과 영구 보존

| class | 용도 | 무거운 원본의 보존 |
|---|---|---|
| `dev` (기본) | 탐색·튜닝·개발·진단 | 해당 PR 병합 또는 종료 때 정리. 날짜로 판단하지 않음 |
| `milestone` | 새 단계 첫 성공·버전별 대표 증거 | 원본 전부 보존, 자동 prune 제외 |
| `study` | 정식 E2E·사전 등록 본 연구 | 원본 전부 보존, 자동 prune 제외 |

모든 등급에서 영구 보존: summary/판정, LLM 요청·응답 **텍스트**, 자기 발행 명령 궤적, 가벼운 결과·trace 원장, **모든 파일의 SHA-256 목록**, 버전별 대표 영상 1개와 그 데이터. 프레임·이미지·npz·일반 영상·큰 trace는 dev의 무거운 원본이다. 알 수 없는 이름의 파일은 삭제 대상으로 추측하지 않는다. 모델 가중치는 기존 [모델 배포](model_artifacts.md) 규칙대로 보존한다.

각 실행 디렉터리에 다음 `RUN_META.json`을 쓴다. PR 번호는 정수, 미정은 `null`이다. 2026-10-11 자동화 요청에 따라 누락 메타데이터는 이름·PR 본문·연결된 experiments 기록으로 소급한다. 불명확하면 class=dev/pr=null/note를 기록한다. PR 없는 DEV는 7일 지난 완료 자료를 압박의 마지막 단계에서 정리하며, 명시적 1회 정리도 가능하다. 기존 study/milestone을 낮추지 않는다.

```json
{"schema":"ugrp.run-meta.v1","class":"dev","pr":435,"branch":"codex/example","sha":"<full-source-SHA>","batch":"example-wave1","keep":["representative.mp4","representative-data","commands.jsonl","llm"]}
```

- `keep`은 실행 폴더 기준 파일 또는 디렉터리 목록이다. 대표 영상의 입력·구성·재생에 필요한 데이터를 빠짐없이 넣는다. `representative*` 파일·디렉터리도 항상 보존한다. 실제 등급은 결과 수집 전에 정하며 첫 성공은 milestone로 승격한 새 기록을 남긴다. 불리한 study 실패를 dev로 낮추지 않는다.
- 열린 PR·진행 중 작업·테스트가 쓰는 자료는 보존한다. 사용 중인 자료에 `.IN_USE` 또는 `.TEST_IN_USE`를 두고, RUN_META의 `in_use=true`와 `keep`도 사용할 수 있다. 실제 실행은 `.evidence.lock`을 잡는다. 완료 표시는 `EXIT`다(0뿐 아니라 실패·HOST_ERROR도 포함). EXIT 없는 실행을 압축·아카이브·prune하지 않는다.
- 부모가 study/milestone면 자식 dev도 정리하지 않는다. 중첩 RUN_META가 있는 부모는 통째로 prune하지 않고 자식별로 검토한다. 다른 열린 PR·테스트의 입력으로 재사용하면 해당 자료에 사용 표시를 먼저 남긴다.

## 3. 배치 제출 전 예산

`실행 수 × 예상 실행당 크기 + 이미 제출한 작업이 앞으로 쓸 크기`를 각 호스트 여유에서 뺀다. x86은 **비압축 peak raw**, ARM은 압축 효과가 불확실하면 **비압축 전체 크기**, Mac은 **fetch-lite 크기**를 쓴다. 압축 임시 파일·아카이브 중복·영상 생성 작업의 peak도 예상 크기 또는 예약량에 더한다.

| 호스트 | 제출 후 바닥 | 여유 공간 경보 |
|---|---|---|
| x86 (`oracle-x86`) | 8 GiB | 8 GiB |
| ARM (`oracle`) | 25 GiB | 25 GiB |
| Mac | 20 GiB | 15 GiB |

```sh
# 세 호스트 중 하나라도 실패하면 && 뒤의 제출 명령은 실행되지 않는다.
python3 scripts/storage_budget.py --all-hosts --runs 36 --per-run-mb 512 \
  --mac-per-run-mb 5 --reserved-mb 1024 && <배치 제출 명령>
# 지정 호스트의 실제 저장 파일시스템 확인 (원격 df에 해당하는 disk_usage)
python3 scripts/storage_budget.py --host arm --ssh oracle \
  --path '~/ugrp-archive/runs' --runs 36 --per-run-mb 512
# 과거 완료 배치에서 추정: RUN_META가 있으면 가장 큰 완료 실행 + 25% 여유
python3 scripts/storage_budget.py --host x86 --past-batch <과거 배치> --runs 36
# 구형 배치는 실패/HOST_ERROR 포함 정확한 실행 수를 지정: 평균 + 25% 여유
python3 scripts/storage_budget.py --host x86 --past-batch <과거 배치> --past-runs 36 --runs 36
```

`--per-run-mb`, `--reserved-mb`의 단위는 MiB다. JSON 출력·종료 코드 0/1을 제출 기록에 저장한다. SSH/df 실패·빈 표본·실행 수 미확인·잘못된 크기는 제출 거부다. 여러 에이전트가 동시에 제출할 때는 조정자가 제출 순서와 이미 승인한 배치의 예약량을 합산하고 직전 다시 검사한다. 이 도구는 원자적 전역 예약 큐가 아니므로, 동시에 같은 여유를 각각 예약하지 않는다.

압축된 과거 배치는 `COMPRESSED.jsonl`의 원본 크기로 peak를 계산한다. 원본 크기 매니페스트가 없는 구형 `.json.zst`/`.jsonl.zst`는 작아진 파일 크기로 예산을 낮추지 않고 추정을 거부한다. 이때 비압축 실행 기록에서 확인한 `--per-run-mb`를 명시한다.

감시는 `storage_budget.py --host <host> --path <저장 경로> --alert-only`를 5분마다 실행한다. Mac은 `--notify`로 알림도 보낸다. x86·ARM은 systemd journal에 경보와 종료 코드 1을 남긴다. 자동 삭제나 다른 작업 중지는 하지 않는다. 서버 전원 OFF·Mac 절전 중에는 경보가 실행되지 않으므로 제출 검사를 반드시 별도로 한다.

설치 구성은 `configs/storage_watch/`다. 서버는 도구를 `~/ugrp-storage-tools/scripts/`에 두고 user systemd service/timer를 사용한다(x86만 `x86.conf` drop-in). Mac은 `~/Library/Application Support/ugrp-storage-tools/`의 도구와 `com.ugrp.storage-watch` LaunchAgent를 사용한다. worktree 은퇴와 관계없이 감시 도구가 남는다. 설치·실행·파일 해시 확인은 [10/11 적용 기록](../experiments/2026-10-11-storage-rules/README.md)에 있다.

## 4. 큰 JSON/JSONL의 무손실 압축

```sh
python3 scripts/compress_json_traces.py <완료 실행>             # 계획만
python3 scripts/compress_json_traces.py <완료 실행> --execute   # 검증 압축
```

- 64 KiB보다 큰 JSON/JSONL에 `zstd -3 -T1`을 적용한다. RUN_META는 읽을 수 있도록 그대로 둔다. 진행 중·사용 중·중첩 미완료 실행은 거부한다. 심볼릭 링크는 따라가지 않는다.
- 압축 전 원본 SHA-256 → 임시 `.zst` → 스트리밍 압축 해제 SHA-256 일치와 원본 불변 확인 → `.zst` 게시 → `COMPRESSED.jsonl` fsync → 원본 제거 순서다. 기존 `.zst`를 덮어쓰지 않는다. 불일치·압축 실패 시 원본을 남긴다.
- `ALL-hashes.tsv`에는 압축 전 전체 파일 목록을, `SHA256SUMS.tsv`에는 현재 보관 파일 목록을 남긴다. 매니페스트는 원본/압축 경로·바이트·SHA-256·코덱·검증 방식을 기록한다. TSV의 경로는 탭·개행을 안전하게 나타내도록 JSON 문자열이다.
- 압축은 study/milestone에도 바이트를 복원할 수 있는 보관 방식이다. 해시는 원본 해시와 `.zst` 해시를 구별한다. 과거 평가자가 `trace.jsonl`을 직접 읽으면 필요한 파일만 별도 영속 작업 경로에 해제하고 원본 해시를 검증한다. 봉인된 실행 폴더에 파일을 덮어쓰지 않는다.
- x86 자동 아카이브는 기존 10분 timer에서 EXIT·20분 idle·평가 결과(`summary.json`, `result.json`, verdict 또는 평가자가 남긴 `EVALUATED`)를 확인한 뒤 위 압축을 실행한다. 이후 ARM **복사 후** 25 GiB 검사, 임시 목적지 rsync, `rsync -anc` 차이 없음, 전체 파일 SHA-256 대조와 원본 불변·사용 중 재확인 후 게시한다. 오류·이미 존재하는 목적지는 원본을 남기고 기록한다. 20분은 실행 중 파일을 피하기 위한 idle 조건이며 dev 보존 기간이 아니다.

## 5. PR 수명에 따른 dev 정리

```sh
python3 scripts/evidence_prune.py --pr <번호> <경로1> <경로2>   # 기본 dry-run
# 10/11 후속 자동화에서 dry-run 검토 후 execute를 승인받음
python3 scripts/evidence_prune.py --pr <번호> <경로들> --execute \
  --records <프로젝트>/outputs/cleanup-records
```

- `gh`가 실제 PR의 MERGED/CLOSED 상태와 같은 브랜치의 열린 PR 부재를 확인한다. RUN_META의 정수 pr이 일치하고 class=dev, EXIT 완료인 실행만 대상으로 한다. API·인증·프로세스 조회 실패는 정리를 거부한다. 원격에서 실행할 때 gh 접근을 따로 준비하며 Mac의 인증정보를 복사하지 않는다.
- 이미지·프레임·배열·일반 영상과 >64 KiB JSON/JSONL을 찾되, 영구 보존 이름·`keep`·`representative*`는 제외한다. 압축된 trace는 `COMPRESSED.jsonl`의 **원본 크기**로 분류한다. 이름을 모르는 기타 파일은 보존한다. 가벼운 trace(≤64 KiB)는 남긴다.
- dry-run은 후보 경로·현재 바이트·SHA-256을 stdout JSON으로 보고하고 실행 자료를 쓰거나 삭제하지 않는다. 중복 경로는 한 번만 계산한다. RUN_META가 없는 폴더는 후보 0으로 보존하며 이는 원본이 없다는 뜻이 아니다.
- execute는 배타 잠금·실제 cwd/열린 파일/실행 명령 검사를 재사용한다. 전체 파일 목록 `ALL-hashes.tsv`, 후보 `PRUNED-hashes.tsv`, `outputs/cleanup-records/`의 계획 영수증을 먼저 저장한다. 그 뒤 파일 불변·완료 상태를 다시 확인하고 처리한 파일을 영수증에 남긴다. 이전 목록·영수증은 보존한다.
- Mac은 `~/.Trash/ugrp-pr-<번호>-<시각>/`으로 이동한다. 사용자가 휴지통을 비운다. 서버는 해시·기록을 저장한 뒤 후보 파일만 삭제한다. milestone/study·대표 증거·가벼운 파일은 삭제 대상이 아니다. 2026-10-11 사용자 승인 범위의 PR 없는 7일 지난 DEV도 해시·기록 뒤 같은 방식으로 정리한다. raw 등급 변경·그 밖의 삭제는 별도 결정이 필요하다.

## 6. 공용 실행 경로의 RUN_META 옵션

`ugrp_session.py`의 저장 옵션은 **기본 OFF**다. 기존 명령·기본 10 GiB 실행 검사·세션 수명 관리는 그대로다. 새 배치는 세 호스트 예산을 통과한 뒤 다음 토글을 사용한다(옵션은 세션 이름 앞).

```sh
python3 scripts/ugrp_session.py run \
  --evidence-dir "$HOME/ugrp-sim/runs/example-NEW" \
  --evidence-class dev --pr <번호> --batch example-wave1 \
  --storage-host x86 --expected-mb 512 \
  --keep representative.mp4 --keep representative-data \
  example -- <표준 sim_cli 또는 연구 어댑터> --output "$HOME/ugrp-sim/runs/example-NEW/data"
```

새/빈 폴더만 사용한다. RUN_META에 class/pr/branch/전체 SHA/batch·keep·활성 상태·예산을 기록하고 실행 동안 잠금을 유지한다. 종료 후 `active=false`와 EXIT를 쓴다. 래퍼 예외·미완료에는 EXIT가 없어 자동 정리를 막는다. 소스 변경 여부 `source_dirty`를 기록하며 실제 실험 전에 실행 소스를 커밋·push하고 코호트 중 고정하는 기존 규칙을 지킨다. class=study를 명시해야 정식 E2E 원본 보호를 보장할 수 있다. 임의 scratchpad 래퍼를 공용 기본 경로로 만들지 않는다.

## 7. 기존 도구와 원본 무결성

- `disk_report.py`: 프로젝트·worktree·환경·outputs 크기를 읽기 전용으로 측정한다. 파일명으로 추정한 기존 retention 표시를 실제 삭제 허가로 쓰지 않는다. 저장 예산 제출 검사는 새 도구가 맡는다.
- `agent_worktree.py new`: sparse checkout, 에이전트당 등록 8개. 은퇴는 `retire`만 쓴다. 무시 raw를 옮기고 전체 파일 수·바이트·SHA-256 대조 후 제거한다. 사용 중/60분 안 변경 worktree는 거부한다. 미병합 HEAD는 원격 보관 SHA가 같은 경우만 은퇴한다. 직접 `git worktree remove`, force, reset, clean을 쓰지 않는다.
- `harness/frame_storage.py`·`FrameSink`: 기존 캡처 프로필과 쓰기 상한은 실행 번들의 일부다. 이번 저장 변경이 입력 프레임 빈도·물리·제어기를 바꾸지 않는다. study는 원본 전부를 남기는 프로필과 사전 등록 크기를 사용한다. 개발 캡처·모델 요청 텍스트·원본 이미지 해시를 구별한다.
- `write_cap_guard.py`: 설정된 증가분 상한을 넘으면 자기 프로세스 그룹만 정리한다. 쓰기 상한 초과는 설정 중단이며 ENOSPC와 구분한다. `pack_frames.py`의 옛 날짜 검사·손실 영상 전환을 PR 기반 prune의 대체로 쓰지 않는다.
- 실행 중 ENOSPC/EDQUOT는 **HOST_ERROR**다. 실패 시도의 요약·원장·해시·원본 위치도 기록하며 실행 중·미회수 자료를 완료로 표시하지 않는다. 본 연구의 분모·재실행 규칙은 사전 등록에 둔다. 과거 판정은 소급 변경하지 않는다.

## 참고 자료

- [Zstandard 공식 CLI](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md): 무손실 압축, 원본 기본 보존, `-d`/`-t`. 자체 압축 해제 SHA-256 비교를 추가했다.
- [rsync 공식 매뉴얼](https://www.samba.org/ftp/rsync/generated-files/rsync.1.html): `-c`는 복사 필요 여부를 내용 체크섬으로 결정한다. 전송 중 체크섬 검증과 별개이며, 이번 아카이브는 `-anc` 재비교와 전체 SHA-256도 확인한다.
- [DCC: Five steps to decide what data to keep](https://dcc.ac.uk/guidance/how-guides/five-steps-decide-what-data-keep): 재사용 가치와 재현 필요에 따라 보존 자료를 선택한다. dev/milestone/study의 구체적 수명·숫자 바닥은 논문 표준값이 아닌 10/11 사용자 결정이다.

## 8. 사용자 승인 자동 정리 (2026-10-11 후속)

`storage_automation.py`는 기존 압축·prune·배타 잠금·실제 사용 검사를 재사용한다.
Mac `com.ugrp.storage-auto` 사용자 LaunchAgent는 매일 04:15와 5분 간격에 호출된다.
5분 호출은 여유 검사만 하고, 하루가 지났거나 Mac <30 GiB / ARM <35 GiB일 때만
실제 작업한다. 압박 재시도는 시간당 한 번으로 제한한다. 동시에 실행되면 공용
maintenance 잠금으로 하나만 진행한다. KeepAlive·무한 로그 파일은 만들지 않는다.
절전/로그아웃 중에는 실행되지 않으므로 제출 전 예산 검사는 계속 필요하다.

- Mac에서 인증된 GitHub API로 **모든 PR**을 페이지 끝까지 조회한다. ARM에는 비밀·토큰을
  복사하지 않고 SSH 표준 입력으로 5분 유효 PR 목록만 전달한다. 잘못된 저장소·만료·빈 목록,
  열린 PR·같은 브랜치 다른 열린 PR은 정리를 거부한다. API/SSH 실패는 기록하고 다음에 재시도한다.
- 소급 RUN_META는 최상위 배치와 EXIT 있는 자식에 붙인다. 기존 메타데이터는 보존하고
  자식은 부모 PR·study/milestone을 상속한다. 미완료 EXIT는 만들어내지 않는다.
  `egomap→405`, `s4live/s4grip→425`, `s3fix숫자→416`, `s3view→427`,
  `s3view3→432`, `e2e1–4→433`이며 보기 전용 이름과 PR 본문의 정확한 실행 이름이 우선한다.
  연결된 experiments의 정확한 경로도 참고한다. 모호한 자료는 dev/null/note이며 영구 제외하지 않는다.
- 최근 **24시간** 바뀐 증거·실행 중·테스트 사용·보호 등급·대표 영상과 데이터는 보존한다.
  RUN_META·hash 목록·압축 매니페스트 등의 정리 작업은 증거 나이를 초기화하지 않는다.
  압축 결과 파일은 원본 mtime을 보존한다. 메타데이터 없는 기존 폴더도 dry-run에서 가상
  메타데이터로 계획하며, dry-run은 원본 폴더를 변경하지 않는다(별도 cleanup 기록만 저장).
- 여유가 바닥+10 GiB 미만이면 (a) 종료한 eligible DEV의 큰 JSON을 zstd로 무손실 압축하고
  (b) MERGED/CLOSED DEV를 정리하며, 여전히 압박이면 (c) PR 없는 7일 지난 DEV를 정리한다.
  평상시에도 (b)는 매일 수행한다. `--include-orphans`는 승인된 1회 (c)를 명시적으로 수행한다.
  압축·삭제마다 기존 전체 해시·복원 SHA·삭제 영수증과 단계별 여유를 기록한다.
- Mac은 휴지통으로 이동하므로 그 단계로 실제 여유가 늘어나지 않을 수 있다. 자동 비우기는
  하지 않는다. 휴지통 >10 GiB는 `outputs/cleanup-records/TRASH-OVER-10GiB.txt`,
  접근 실패와 바닥 미달도 별도 알림 파일에 남긴다. 서버는 해시 뒤 실제 삭제한다.
- opt-in `ugrp_session.py --evidence-dir` 경로는 종료 시 `RUN_STORAGE.json`에 크기를 기록하고
  300 MiB 초과를 경고하며 큰 JSON을 즉시 검증 압축한다. 압축 오류가 원래 실행의 종료 코드나
  HOST_ERROR를 덮어쓰지 않는다. 직접 호출된 옛 실행기의 자동 연결·캡처 토글은 별도 작업 범위다.

```sh
python3 scripts/install_storage_automation.py --install-arm
python3 scripts/storage_automation.py --host mac --root ~/projects/ugrp/outputs --remote-arm
# 계획 검토 뒤 실행(10/11 1회는 PR 없는 7일 지난 DEV도 명시적으로 포함)
python3 scripts/storage_automation.py --host mac --root ~/projects/ugrp/outputs \
  --remote-arm --include-orphans --execute
```

설치 후 자체 worktree를 지워도 도구는 Mac `~/Library/Application Support/ugrp-storage-tools/`와
ARM `~/ugrp-storage-tools/`에 남는다. 이전 도구는 버전별 backups에 보존하고 설치 파일의
전체 SHA-256을 확인한다. ARM stock-bot·crontab·기존 timer는 변경하지 않는다.
Azure는 `--host azure`/`configs/storage_auto/azure-command.txt`의 적용 명령만 준비했다.
준비 작업 종료 뒤 서버가 이미 켜져 있을 때 dry-run/검토/설치를 수행해야 한다.
자동화는 Azure·oracle-x86에 접속하거나 VM을 시작하지 않는다.

참고: [Apple launchd 주기 실행](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)의
StartInterval/StartCalendarInterval을 그대로 사용한다. 삭제 조건·7일·용량 문턱은 사용자 결정이다.
[Zstandard 공식 CLI](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md)의 무손실 압축과
해제 방법을 따르며, 기존 도구의 독립 SHA-256 복원 검증을 유지한다.
