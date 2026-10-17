# llmnomap — 자기 중심 기억 요약 프롬프트 변형 (기본 off)

## 목표

판단 LLM 요청에서 정적 지도(좌표계·벽·구역·문 배치 블록)를 빼고, 로봇 기준 기억 요약
(`종류·거리·방향·불확실성·마지막 관측 경과`)으로 바꾸는 프롬프트 변형을
`planner_egocentric_memory_v1` 기본 off 토글로 제공한다.

- 구현: `harness/planner_egocentric_memory.py`
- 테스트: `tests/test_planner_egocentric_memory.py` (13 passed)
- 호출 지점 훅(각 빌더 마지막 줄, 토글 off면 바이트 동일):
  - `harness/zone_study_prompts_ko.py` `build_request`
  - `harness/pair_llm_inputs.py` `build_request`
  - `harness/s4_llm_inputs.py` `build_request`
  - `harness/e2e_own_inputs.py` `build_request`
- 켜기: `UGRP_PLANNER_EGOCENTRIC_MEMORY=1` 또는 `apply_request_if_enabled(request, value=OPTION)`

## 정적 지도 유입 경로

`SURVEY.md` 참조. 요약(파일:줄, 토큰):

| 경로 | 위치 | 정적 지도 크기 |
|---|---|---|
| 계획기 번들 payload | `harness/task_planner.py:223-231` | 207 tok (473자) |
| 계획기 e2e stub | `harness/e2e_task_planner.py:147-149` | 18 tok |
| pair/beam payload | `harness/pair_llm_inputs.py:134-145` | 1582 tok (3676자) |
| pair/beam 지도 그림 | `harness/pair_llm_inputs.py:349-358` | 1490 tok/이미지 |
| beam dispatch | `harness/pair_llm_dispatch.py:403-409` | 405 tok |
| zone/S4 payload | `harness/zone_study_inputs.py:383-386` | 1582 tok |
| zone/S4 지도 그림 | `harness/zone_study_prompts_ko.py:649-657,779-792` | 1490 tok |
| e2e own-input | `harness/e2e_own_inputs.py:22-26` | 0 (금지) |
| compact opt-in | `harness/s4_compact_prompt.py:92-100,122-128` | 0 (제거) |

## 프롬프트 순서

변형은 `system → 고정(작업·주문표·규칙·형식, 지도 없음) → 변동(시각·자기 상태·기억 요약·받은 메시지·후보) → 이미지(own RGB 마지막)`으로 재배열한다.
로봇은 항상 현재 위치가 원점·정면이고, 과거 관측은 현재 ego-frame으로 변환해 거리/방향을 계산한 뒤
세계 좌표·pose·static map을 제거한다.

## 기억 항목 형식 (조정자 통일안 반영)

`egocentric_memory`는 `ugrp.memory_item.v1`의 요약 필드만 담는다:
`kind/signature/range_m/bearing_rad/age_s/radius95_m`. 컨테이너에는
`item_schema:"ugrp.memory_item.v1"`, `frame:"self/current"`를 명시한다.

```json
{
  "schema": "ugrp.egocentric_memory.v1",
  "item_schema": "ugrp.memory_item.v1",
  "frame": "self/current",
  "entries": [
    {"kind": "help_request", "signature": "beam_1=needs_help",
     "range_m": 1.03, "bearing_rad": 2.583, "age_s": 23.8, "radius95_m": 0.52}
  ],
  "count": 1
}
```

`radius95_m = sqrt(chi2_2(0.95) * lambda_max(P_xy))` (P = 관측 시점 own pose 위치 공분산).
`bearing_rad`는 0=정면, +=왼쪽. `age_s`는 현재 시각에서 마지막 관측까지의 경과다.

## 입력 감사

`input_audit.json` (40개 재생 요청):

- `static_map` 키: 80 → 0 (40/40 요청에서 제거)
- world pose 키: 296 → 0
- system 내 지도 언급: 80 → 0
- 지도 그림 이미지: 0 → 0 (저장 원장은 text-only)
- 누출(구조/금지값/제거 좌표 재등장): **0**
- 기억 요약: 32/40 요청 1항목, 8/40 빈 배열
- 텍스트 토큰 절감: 총 16,516, 중앙값 438.5

## 짝지은 LLM 측정

먼저 `python3 scripts/model_endpoint_watch.py` 확인: `ok:true`, alerts `[]`.
모델: `google/gemma-4-31b-it` @ CoreWeave `coreweave/fp4`, fallback off, temperature 0,
max_tokens 300, own RGB 1장(양쪽 동일), 재시도 없음.

원장: `outputs/task-planner-ling-vl-main-20261013/off-calls.jsonl.zst` 앞 40행
(no_comm 20, peer_en 20). 원본 요청 그대로(정적 지도 포함) vs 같은 요청의 변형.

| 항목 | 원본 | 변형 |
|---|---|---|
| 호출/HTTP 200 | 40/40 | 40/40 |
| 429 / 오류 | 0 / 0 | 0 / 0 |
| `act` 형식 성공 | 40/40 | 40/40 |
| 응답 시간 중앙값 | 2.3528 s | 2.2355 s |
| p90 | 3.9416 s | 4.0727 s |
| 8초 초과 | 0 | 0 |
| prompt 토큰 중앙값 | 4016.5 | 3310.0 |
| completion 토큰 중앙값 | 56 | 53 |
| cached_tokens 합 | 2,272 / 177,086 (1.283%) | 2,880 / 141,674 (2.033%) |
| 캐시가 1개 이상인 호출 | 5/40 | 5/40 |
| 보고 비용 합 | $0.01844572 | $0.01489160 |
| 호출당 비용 | $0.00046114 | $0.00037229 |

짝 n=40(양쪽 200): 응답 시간 차 중앙값 **-0.0950 s**, prompt 토큰 차 중앙값 **-812.5**,
호출당 비용 차 중앙값 **-$0.000082**, cached ratio 중앙값 차 **0.0** (가중 차 +0.0075).
최종 배치 80콜, 비용 $0.03333732 (상한 $0.25), 120.99초, 잔액 $6.539640 → $6.511262.

**과제 정확도는 측정하지 않았다** (`task_accuracy_measured: false`). 위 수치는 형식 성공·시간·429·토큰·비용만이다.
40개 표본은 한 원장의 앞부분이라 과제 분포를 대표하지 않는다. cached_tokens는 제공자 보고값이고
`provider.order` 수동 지정 시 sticky routing이 꺼질 수 있어 캐시 중앙값 0.0을 성과로 주장하지 않는다.
저장 원장이 text-only여서 같은 번들의 저장 own-RGB 프레임 1장을 양쪽에 동일 첨부했다(요청별 실제 관측 아님).

## 호출 예산

- 최종 배치 80콜 + 필드 통일 전 폐기 배치 80콜 = **160/200**, 잔여 40.
- 폐기 배치는 `archive/pre_unified_batch/`에 원장·요약 그대로 보관하며 최종 수치로 인용하지 않는다.
- 보고 비용: 최종 $0.03333732 + 폐기 $0.03338296 = $0.06672028.

## 재현

```bash
python3 experiments/2026-10-17-llmnomap/build_replay_inputs.py
python3 experiments/2026-10-17-llmnomap/probe_paired.py --audit-only
python3 experiments/2026-10-17-llmnomap/probe_paired.py --allow-live
python3 experiments/2026-10-17-llmnomap/finalize_results.py
python3 scripts/check_current_stack.py \
  experiments/2026-10-17-llmnomap/manifest.json --flow e2e_llm \
  --output experiments/2026-10-17-llmnomap/stack_check.json
python3 -m pytest -q tests/test_planner_egocentric_memory.py
```

`check_current_stack` 결과: `ok:true`, `admission:pass`, current 38 + approved deviation 3
(GCP host/project/account null; "VM 없음(시뮬 금지)" 증거).
이 실험은 Mac 전용 프롬프트 재생이며 VM·시뮬·물리 측정이 아니다.

## 산출물

| 파일 | sha256 |
|---|---|
| `calls.jsonl` (80행 원장) | `fd149e24c073a6b9c74f220cc8b12d61cc209b69d2555e9f062c2871c2cbb9c7` |
| `summary.json` | `5b3ce4909ec9f91eab196c2822112293f341fc429389deebe3848643648d5a22` |
| `input_audit.json` | `0e8882229170cc6bc100bde71e4f6955aca8d3c9023a97c475458315c08887bb` |
| `rejection_table.json` | `cdb3e5c535c15e140f9e021dd1c5873ee503ba34ff7cce8c21680683e1eb1d56` |
| `replay_inputs.jsonl` | `b306f13a26361dc109ea4c4ce078f45c8e1669c86180182abca212315829d021` |
| `manifest.json` | `8fcea1007c63e14a89e821ce5ffd53fe54526354a07c9ffa72225deef882f2b7` |
| `stack_check.json` | `69f01f628bfd548eae96e43a19eeb334072adcc802c78df82c5b47b44f8466c2` |
| `raw/own_rgb_r80-r1-00000.jpg` | `15673f61873991c84cfe449747efa858b4986e36d8f48c5874f483574ec0cfc3` |

전체 해시는 `SHA256SUMS`.

## 퍼널 / 제외

- 원장 136행 중 40행 사용, 96행 제외(`budget_cap`, 호출 예산 보존).
- 재생 요청 40/40에 `static_map` 존재 → 투영 40/40 성공, 감사 누출 0.
- 호출 80/80 HTTP 200, 429 0, 형식 실패 0.
- 물리 실행이 없으므로 `blocking_object`/`minimum_gap_m`은 null.
- 폐기 배치 80콜은 `reason_category: superseded_schema_change`로 별도 기록(최종 퍼널 밖).

## 참고

- ROVIO/Castellanos relative map: 로봇 중심 상대 지도 표현.
- Generative Agents (Park et al., 2023): recency를 포함한 기억 검색.
- Inner Monologue (Huang et al., 2022): 텍스트 관측 기억을 정책 입력으로 사용.
- OpenRouter usage/prompt caching 문서: `prompt_tokens_details.cached_tokens`.
- 저장소: PR #473 (`claude/e2e18-gemma-planner`) 계획기 번들 요청 형식.
- 조정자 통일안(2026-10-17 19:26): `ugrp.memory_item.v1` (egonav 제안) 요약 필드.
