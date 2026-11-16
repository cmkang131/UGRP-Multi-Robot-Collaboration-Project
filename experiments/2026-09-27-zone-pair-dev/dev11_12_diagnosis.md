# dev11/dev12 정지 대기 P1 진단 — v5h

기준 실행 소스: `c38f94e6c551d8c0fa9993945ff4df087754672e`. 원본 위치: `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5g-c38f94e6c551d8c0fa9993945ff4df087754672e`.
입력 진단 문서: `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-dev11-12-diag.md`.
진단 문서 SHA-256: `2cad49a79e3973c4bab74c028426fd4c492f768df1ef04ef63d2055d9a06a603`.

## 원인과 재현

host `_apply`/`_hold`의 소수 4자리 명령 시각이 `motion_until`에 저장됐지만, `align_look_started_at`은 원시 SIM 시각이었다. `stopped_at >= motion_until`의 고정된 거짓 조건은 기다려도 바뀌지 않는다.

| 실행 | raw stopped_at (s) | rounded motion_until (s) | 부족분 | 저장 보고 재현 |
|---|---:|---:|---:|---:|
| dev11 | 184.3999999973675 | 184.4 | 2.63250 ns | 79개 중 기존 0, 수정 79 통과 |
| dev12 | 168.69999999773876 | 168.7 | 2.26123 ns | 79개 중 기존 0, 수정 79 통과 |

기존 host 메서드의 정확한 최소 발췌를 `tests/fixtures/zone_pair_v5h/host_v5g.py`에 보존했다. 두 방식 모두 실제 `PairCommandGuard`를 사용하며, 마지막 저장 drive는 그대로 입력하고 hold만 원본 state 이벤트의 raw 시작 시각으로 host에 전달한다. 기존 host는 다시 반올림해 실패하고, 수정 host는 원시 시각을 보존해 통과한다. 각 79개 입력은 시작 직후부터 8초 제한 직전까지의 **모든** r2 보고다. 원본 보고의 raw `last_fix_t`는 재구성하거나 반올림하지 않았다.

이 통과는 **정지 확인 단계만** 뜻한다. 해당 보고는 시작 전 fix를 유지하므로 새 fix나 align 복귀 성공으로 세지 않는다. 새로운 파지·운반·문 통과·표식 없는 위치 추정 성능을 검증하지 않았다.

## 유지한 판단

- 진단 문서의 loaded align 게이트·PF 재초기화·blockage 분석은 후속 범위다. 이번에는 게이트 임계값/dwell, relook 횟수·개별/총 시간, blockage 판정을 바꾸지 않았다.
- σ가 낮다는 것과 새 관측 fix 수용은 별도 조건이다. 표식 없는 fake provider에서도 같은 정지 및 raw fix 경계를 적용한다.
- raw 파일은 읽기만 했다. JPEG·평가 정답·대량 명령 로그는 fixture로 복사하지 않았다. fixture에는 158개 보고의 필요한 필드, raw input 시각, 원본 파일 해시와 명령 4줄만 포함한다.

## 출처와 해시

`tests/fixtures/zone_pair_v5h/reports.json`: 70619 bytes; SHA-256 `f507bba798f68d3a90af5709eb8af191c1df13afdc28fdbc9eb15ac407e3d750`.
`host_v5g.py`: SHA-256 `0a256e35f7ea3e3b3d1bd72aca7610b11f2749b4cf868e8339e00d17c7430f72`; 전체 원본 host 파일 SHA-256 `8d64d20f8e21e00f7ca4baef275ef1dbcd9eafd04fb9c7bdb32ae204cea16e4e`.

각 frame의 `inputs/r2/<frame:05d>.json` SHA-256은 fixture의 `input_sha256`에 있으며, 선택 기준과 원본 경로도 함께 저장했다. 아래 해시는 원본 전체 파일의 값이다.

| 실행 / 파일 | SHA-256 |
|---|---|
| dev11/commands.jsonl | `93cc64b3d391ceaa30f55a26ecf442ec1f451e2c169113d25fdf4adc9e4ee5c3` |
| dev11/robots.json | `16932a8515d257aef8bdfa006fd88a8cfae0fedee01d89830ffee0db211890d9` |
| dev11/pair_records.json | `7dcf9b3d8c23a0a4dc9034812f9fd7be50a38e9c0a37c3a1a514a2f80f1e1f7e` |
| dev11/manifest.json | `89503994bd94c67d8e52e3970363c6b9a206c80eaccb727b6200c79783783d4d` |
| dev11/prereg.json | `9d7032b0bbf6d73c075301e136b7bcd6c6b1d9a7532f43e912ac4eddf703145b` |
| dev11/result.json | `79541c627742073b589d865ce4fac080e8c27873a660c67b823eefd97b83643c` |
| dev12/commands.jsonl | `3dd9c35cb0e3bd16037c74f7510f67f6f74ba093248dc0b2597eedc9ff0a64a5` |
| dev12/robots.json | `896d8e7a894693cbaed958e214dbe9a7ac4e47605098135dcc8457eed5159850` |
| dev12/pair_records.json | `cee679a52d012c32f30b04ad079726718e372594c288d9a0108b55f97dbdf0eb` |
| dev12/manifest.json | `fb19cd0e33390543eb1081229d053e8b61380d459784bbd343189eca163f8791` |
| dev12/prereg.json | `6d9707ca5b940e81ed55e01d3151d5067717ee5a31583c21b1b42ee03857fdf0` |
| dev12/result.json | `fdaab709a6586313fca5045daab57daf0c1433cc11bc2ef6f717690fcb219486` |

최종 원본 재대조·전수 조사 파일 목록·테스트 로그는 [v5h_validation/](v5h_validation/), 변경과 검증 범위는 [changes_v5h.md](changes_v5h.md)에 기록한다.
