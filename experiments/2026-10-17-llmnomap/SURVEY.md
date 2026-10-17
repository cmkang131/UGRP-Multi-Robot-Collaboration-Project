# 판단 LLM 요청의 정적 지도 유입 경로 (2026-10-17 llmnomap)

조사 범위: main과 열린 planner 브랜치 `claude/e2e18-gemma-planner`(PR #473)의 판단 LLM 요청 조립부.
읽기만 했고 다른 작업자 worktree/브랜치는 수정하지 않았다. 토큰은 저장소의 고정 토크나이저
`harness.zone_study_prompts_ko.count_tokens`로 셌고, 이미지 청구는
`harness.pair_llm_billing.IMAGE_TOKENS_PER_IMAGE=1490`이다. 이 숫자는 청구 토큰이지 실제
비전 인코더 토큰의 독립 측정이 아니다.

## 표: 지도가 들어가는 곳

| # | 경로 | 파일:줄 | 지도가 들어가는 방식 | 블록 크기(토큰) | 40개 재생에 포함 |
|---|---|---|---|---|---|
| P1 | planner 번들 문맥 | `harness/task_planner.py:223-231` (특히 227 `static_map=`) | `static_map`가 user JSON의 최상위 키로 복사됨 | **207** (473 chars, 저장 요청 실측) | 예 40/40 |
| P2 | planner e2e 실행기 문맥 | `harness/e2e_task_planner.py:147-149` (148 `static_map=dict(source='none...')`) | 실제 지도 대신 1문장 stub | **18** | 아니오(별도 e2e 경로) |
| P3 | planner 요청 조립 | `harness/e2e_task_planner.py:305-316` (311 user, 312 system) | `ordered_context` 결과를 user로, `SYSTEM`을 system으로 | P1/P2에 포함 | 예(저장 원장 생성 경로) |
| P4 | planner 평가기 | `scripts/evaluate_task_planner.py:80-83` | `view['public_context']['static_map']`를 `p.context`에 전달 | P1에 포함 | 예(원장 생성) |
| P5 | planner 캐시 순서 | `harness/task_planner_model.py:57-58,61-82` | `static_first_v2`가 `static_map`을 4번째 고정 키로 둠 | - | 원장은 `off`(정렬) |
| B1 | pair/beam payload | `harness/pair_llm_inputs.py:134-145` (144 `static_map`) | user JSON 최상위 `static_map`(map_id, hash, public_map, schematic_ref) | **1582** (3676 chars) | 아니오 |
| B2 | pair/beam 지도 그림 | `harness/pair_llm_inputs.py:349-358` (357 `IMAGE_MAP`) | `STATIC MAP FIGURE` PNG를 두 번째 이미지로 첨부 | **1490** | 아니오 |
| B3 | pair/beam 요청 조립 | `harness/pair_llm_inputs.py:361-367,376-424` (411 images/manifest) | system + user JSON + own image + map image | B1+B2 | 아니오 |
| B4 | beam dispatch | `harness/pair_llm_dispatch.py:403-409` (405 `static_map=self.static_map`) | 실행기의 map을 payload로 전달 | B1+B2 | 아니오 |
| S1 | S4/zone payload | `harness/zone_study_inputs.py:383-386` (385 `static_map`) | user JSON 최상위 `static_map` | **1582** | 아니오 |
| S2 | S4 요청 재조립 | `harness/s4_llm_inputs.py:115-133` (121 `body.update(inputs.payload_dict())`) | base 요청을 다시 payload로 덮어써 지도가 최종 user에 남음 | B1과 동일 | 아니오 |
| S3 | zone/S4 지도 그림 | `harness/zone_study_prompts_ko.py:649-657,779-792` (657/789 `IMAGE_MAP`) | `STATIC MAP FIGURE` 이미지를 첨부·manifest에 기록 | **1490** | 아니오 |
| S4 | zone static map 원천 | `harness/zone_study_inputs.py:513-515` | `static_map_section(map_bundle)`가 매 호출 동일 bytes | B1과 동일 | 아니오 |
| E1 | e2e own-input | `harness/e2e_own_inputs.py:22-26` (23 `FORBIDDEN`에 `static_map`) | **금지**. own_map(자기 관측 벽/pose)만 허용 | **0** | 아니오 |
| C1 | S4 compact opt-in | `harness/s4_compact_prompt.py:92-100,122-128` | opt-in일 때만 `static_map`/지도 그림 제거 | 0 (opt-in) | 아니오 |

## 시스템 프롬프트의 지도 언급

| 경로 | 파일:줄 | 문구 | 처리 |
|---|---|---|---|
| planner | `harness/task_planner.py:30-48` (33) | "Use only the order sheet, static map, your camera/command pose estimate..." | 변형에서 기억 요약으로 교체 |
| pair | `harness/pair_llm_prompts_ko.py` system 5번째 줄 | "매 호출 제공되는 static_map, 정적 지도 그림 1장, order_sheet는..." | 교체 |
| zone | `harness/zone_study_prompts_ko.py` system 6번째 줄, `KO_SOURCES` | "static_map과 order_sheet", decision_sources `static_map` | 교체 |
| S4 | `harness/s4_llm_inputs.py:27-34` | "정적 지도·주문", "정적 지도 그림은 현재 상황이 아닙니다." | 교체 |
| e2e own | `harness/e2e_own_inputs.py:339-353` | 지도 언급 없음(own_map만) | 추가 지시만 |

## 현재 캐시 순서와 변형 순서

- 현재 planner: system → `ordered_context`(static_first_v2면 `schema,public_rules,task,static_map,order_sheet,condition,can_send_to,robot_id`) → dynamic(`now_s,own,own_act_results,received_messages,events,evidence_gate,evidence_assessment,candidates`) → 이미지.
- 현재 pair/S4: system → user JSON(`sort_keys=True`라 `static_map`이 중간에 섞임) → own RGB → STATIC MAP FIGURE.
- 현재 e2e own: system → user JSON(`own_map` 포함) → own RGB.
- 변형 `planner_egocentric_memory_v1`: system(지도 없음, 기억 지시 포함) → 고정(`schema,robot_id,condition,task,order_sheet,public_rules,can_send_to,channel,reply_contract,action_message_contract,input_profile_id`) → 변동(`request_id,now_s/sim_time_s,own/self state,egocentric_memory,received_messages/inbox,peer_reports,candidates,evidence_window`) → 이미지(own RGB 마지막). 지도 그림은 제거.

## 재생 표본

`outputs/task-planner-ling-vl-main-20261013/off-calls.jsonl.zst` 앞 40행(no_comm 20, peer_en 20)을
`experiments/2026-10-17-llmnomap/replay_inputs.jsonl`로 고정했다. 40/40에 `audit[0].request`가 있고
40/40에 `static_map`이 있다. `own.observed_facts`는 32/40에 1개, 8/40은 빈 기억이다. 저장 요청은
text-only(`own.rgb.source='synthetic format sample; no image supplied'`)라, 현재 입력 프로필의
own RGB 1장을 맞추기 위해 같은 번들의 저장 프레임 1장을 **원/변형 양쪽에 동일하게** 첨부했다.
새 이미지를 만들지는 않았다. 따라서 이 배치의 이미지 효과는 짝지어 상쇄되지만, 프레임이
요청별 실제 관측과 일치하지 않는다는 한계가 있다.

## 참고

- Generative Agents, arXiv:2304.03442 — recency 기반 기억 검색.
- Inner Monologue, arXiv:2207.05608 — 텍스트 관측 기억을 LLM에 되먹임.
- ROVIO, doi:10.1109/LRA.2017.2718635; 로보트 중심 상대 지도(Castellanos et al., RAS 2007,
  doi:10.1016/j.robot.2006.12.001).
- OpenRouter prompt caching, https://openrouter.ai/docs/features/prompt-caching — 고정 prefix 우선,
  `usage.prompt_tokens_details.cached_tokens`.
