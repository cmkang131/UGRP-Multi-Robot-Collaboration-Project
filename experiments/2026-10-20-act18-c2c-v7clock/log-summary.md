# 실행·로그 요약 — ACT18 C2c v7 clock (2026-10-20)

원 보고서 `outputs/reports/2026-10-20-act18-c2c-v7clock.md`와 회수본 `outputs/runs/act18-c2c-v7clock-20261019T2315Z/`의 실행 상태·로그 요약이다. raw JSONL·JPEG·영상·대용량 로그는 repo에 넣지 않았다.

## 실행 상태

- 9 runs 전부 `status=DONE`, group exit 0, HOST_ERROR 0.
- 체크포인트 `model.safetensors` sha256 `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`가 실행 전·후·9 runs 전부 동일하다(`runs.json`의 `checkpoint_sha256_before/after`).
- root log `root.log` sha256 `ca52729ab45c8590f92310ce8fb5d43be8f5c58abd97e29b2022f14bb6f79cb5`.
- run root 구조: `<run>/R8-{diag,train}/group-00{0,1,2}` (HO4 3 groups, TRAIN4 2 groups). run별 회수 파일 수는 969–1214다.

## run별 상태

| run | arm | queue | rep | status | group exit | wall s | finished (UTC) |
|---|---|---|---:|---|---:|---:|---|
| C2c-ho4-rep1 | C2c | HO4 | 1 | DONE | 0/0/0 | 915.3 | 2026-10-19 23:18:45 |
| B0-ho4-rep1 | B0 | HO4 | 1 | DONE | 0/0/0 | 1079.9 | 2026-10-19 23:36:46 |
| C2c-train4-rep1 | C2c | TRAIN4 | 1 | DONE | 0/0 | 843.6 | 2026-10-19 23:50:50 |
| C2c-ho4-rep2 | C2c | HO4 | 2 | DONE | 0/0/0 | 836.4 | 2026-10-20 00:04:47 |
| B0-ho4-rep2 | B0 | HO4 | 2 | DONE | 0/0/0 | 1056.8 | 2026-10-20 00:22:25 |
| C2c-train4-rep2 | C2c | TRAIN4 | 2 | DONE | 0/0 | 834.7 | 2026-10-20 00:36:20 |
| C2c-ho4-rep3 | C2c | HO4 | 3 | DONE | 0/0/0 | 889.1 | 2026-10-20 00:51:10 |
| B0-ho4-rep3 | B0 | HO4 | 3 | DONE | 0/0/0 | 1053.2 | 2026-10-20 01:08:43 |
| C2c-train4-rep3 | C2c | TRAIN4 | 3 | DONE | 0/0 | 814.5 | 2026-10-20 01:22:19 |

- group exit는 group 순서(0/1/2 또는 0/1)의 exit code다.
- 9 runs wall 합 8,323.5 s = 138.7 min.
- 실행 창 23:03:30Z–01:22Z. 오프피크 창 끝(01:00Z)을 약 22분 초과했다(원 보고서 리스크).

## 회수·무결성

- 원격 run root: 41,354 files/734 MB. `remote-full-sha256.txt`(41,354 lines)와 `remote-sha-<run>.txt` 9개를 보존했다.
- 로컬 회수본: 335 MB(원 보고서). run별 선택 파일 sha256 검증 **9/9 runs OK**.
- run별 파일 수: 1027/1214/1090/969/1214/992/1021/1214/1192.
- JPEG 원본은 VM 디스크 `/home/ugrp/ugrp-sim/runs/act18/c2c-v7clock-20261019T2315Z/`에 유지했고 회수하지 않았다.

## 분석 파일 해시

- 결과 요약 JSON 기재: `raw_runs_sha256` `def6a8634efcc96fdd19345dc8d04975384c98a0846c75f50cb67150393d6359`, `raw_analysis_sha256` `4594c33f2cf2cedb85428626cc04814ea0b102b3c23ced2e844118d565a1e757`.
- 회수본에서 직접 계산: `runs.json` `4594c33f…e757`, `analysis.json` `def6a863…6359`. **원 보고서·요약 JSON의 파일명↔해시 표기가 회수본과 서로 바뀌어 있다**(해시 값 자체는 일치). VM이 종료돼 원격 원본의 파일명을 확인할 수 없으므로, 이 문서는 해시만 인용하고 파일명 매핑을 단정하지 않는다.
- `analysis.json`은 `aggregate`·`worlds`(36 world-run)를, `runs.json`은 9 runs의 실행 메타데이터를 담는다.

## 중단된 root (판정·합산 미사용)

| root | 중단 이유 | 모델 추론 |
|---|---|---|
| `c2c-v7clock-20261019T2258Z` | physics venv symlink resolve로 owner import 실패 | 0 |
| `c2c-v7clock-20261019T2300Z` | prereg 상대경로를 child cwd에서 찾지 못해 HOST_ERROR | 0 |
| `c2c-v7clock-20261019T2301Z` | 등록 HO4 g000 {88668,88669} model scalar 불일치 | 일부(88669) |
| `c2c-v7clock-20261019T2307Z` | 4-single 그룹 시험, 처리량 이유로 중단 | ~10 SIM s |

## 로그 범위

원 보고서는 summary·rejection table·actor-inputs·owner truth·done-prob를 분석했고, 정책 행동 영상은 회수·검토하지 않았다. 이 문서는 실행 상태·해시·중단 root만 요약하며, raw JSONL·JPEG·영상은 포함하지 않는다.
