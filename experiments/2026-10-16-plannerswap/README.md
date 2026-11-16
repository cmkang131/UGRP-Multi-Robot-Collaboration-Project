# plannerswap — CoreWeave fp4로 새 판단 호출 전환 (2026-10-16)

사용자 결정: DeepInfra +50% 경보 뒤 **"대안 찾아줘" → 추천 "CoreWeave fp4" → "ㄱㄱ"**. 모델 `google/gemma-4-31b-it`과 fp4는 유지하고 공급자만 변경한다. 비교 측정과 원본은 [PR #552](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/552)의 `experiments/2026-10-16-llmalt/`에 그대로 둔다.

## 변경 전 근거와 범위

| #552 저장 요청 40건 | DeepInfra fp4 | CoreWeave fp4 |
|---|---:|---:|
| 정상 JSON act / 요청 | 40/40 | 40/40 |
| 429 | 0 | 0 |
| 응답 8초 초과 / 정상 응답 | 5/40 | 0/40 |
| 응답 중앙값 | 5.18 s | 2.60 s |
| 프로브 호출당 비용 | $0.000607 | $0.000461 (−24%) |

이 표는 공급 지연·가격 변경의 근거이며 로봇 실패 원인 분석이 아니다. CoreWeave의 act 일치 36/40은 DeepInfra와의 선택 일치율로, 과제 정확도·물리 성공률이 아니다. API 점검에는 막은 물체·최소 틈이 적용되지 않아 원장에 `not_applicable_api` / `not_measured_not_applicable_api`로 명시했다. 시뮬레이션·실물·모델 학습·실행 대기열 제출은 0회다.

## 구현과 재생 경계

- 새 `openrouter_v1` 기본 요청은 `order=["CoreWeave"]`, `allow_fallbacks=false`, `quantizations=["fp4"]`. 2026-10-16 공식 API의 태그 `coreweave/fp4`와 공급자 이름 `CoreWeave`를 확인했다.
- `config()`·릴레이 `identity.json`·응답 원장에 공급자/프로필/fp4/태그를 기록한다. 새 S4/E2E 실행은 검증된 릴레이 설정을 `bundle.json.llm_upstream`에 넣고 기존 예산의 번들 해시에도 포함한다. 이전에 기록한 번들·실행 config·#552 파일은 변경하지 않았다. 실행기의 변경은 이 설정 기록 연결뿐이며 제어·물리·관측·시간 상한·실패 영상 기록에는 변화가 없다.
- `--openrouter-providers DeepInfra`는 `deepinfra_fp4_replay_v1`, `deepinfra/turbo`, fp4를 명시적으로 선택하는 재생/비교 프로필이다. 과거 소스에는 요청 양자화 필터가 없었으므로 **과거 바이트 단위 재생은 원래 소스 SHA와 저장 번들**을 쓴다. 새 프로필은 과거 결과를 소급 재분류하지 않는다.
- 릴레이 저널은 `.../openrouter/<profile>/`로 분리한다. 과거 공용 저널과 다른 공급자의 응답을 새 CoreWeave 요청에 재사용하지 않는다. CoreWeave·DeepInfra·AI Studio 결과를 합산하지 않는다.
- `configs/model_endpoints.json` 기준은 현재 API의 입력/출력/캐시 읽기 **$0.10/$0.34/$0.10 per 1M tokens**, recorded `2026-10-16`. DeepInfra는 인상 전 기준을 보존한 채 `retired_endpoints`로 이동했다. 감시는 태그·가격·상태 외에 fp4가 바뀌거나 누락돼도 경보한다.

남겨 둔 DeepInfra 하드코딩(현행 판단 기본값과 분리):

| 위치 | 용도 |
|---|---|
| `harness/jev_decider_eval.py:4,161,287` | 저장 장면 JEV/Gemma 비교 요청과 공급자 집계 |
| `scripts/evaluate_e2e8.py:37` | 과거 E2E8 DeepInfra 응답 판정 |
| `tests/test_jev_decider_offline.py:86`, `tests/test_e2e_jev_decider.py:130` | 위 비교/과거 판정 fixture |
| `tests/test_model_endpoint_watch.py:32,34` | 일반 공급 종료 경보용 합성 fixture |
| `scripts/openrouter_upstream.py`·관련 테스트 | 명시적 DeepInfra 재생 프로필 및 오공급자 거부 확인 |

## 검증

실행 소스 `3968d416f13d320a151d7c523b15c042c6d82dab`를 커밋한 뒤 수행했다.

- 관련 시험 파일 3개: `test_openrouter_upstream.py`, `test_model_endpoint_watch.py` **23 passed**(1.88 s), `test_s4_live_stage.py` **11 passed**(0.95 s). 물리/렌더/네트워크 시험 없음.
- Keychain 키를 프로세스 메모리에서만 읽어 **chat POST 정확히 3회, 재시도 0회**. #552와 같은 자기 RGB(13,858 B, sha256 `15673f61873991c84cfe449747efa858b4986e36d8f48c5874f483574ec0cfc3`)와 첫 3개 저장 요청을 사용했다. HTTP 200 **3/3**, 응답 본문 `provider=CoreWeave` **3/3**, JSON act **3/3**, 429 **0**, 응답 **1.527/1.803/1.279 s**, 중앙 **1.527 s**, 합계 비용 **$0.0013634**. 캐시 토큰 448/13,056(3.43%), 이미지 1장씩 전송했다.
- **양자화 확인 한계:** `quantizations=["fp4"]` 요청 필터와 공식 엔드포인트 `coreweave/fp4`의 `quantization=fp4`를 함께 확인했다. 응답 헤더/usage에는 양자화 필드가 없다. 응답 ID의 generation GET도 즉시·후속 조회 모두 404였다(`call-*-generation.json`). 따라서 fp4는 API 라우팅 제약과 엔드포인트 명세로 확인한 것이며, 공급자 내부 양자화를 독립 측정한 결과로 보고하지 않는다. 추가 chat 호출은 하지 않았다.
- 최초 로컬 준비 1회는 저장 요청의 `system/input` 형식을 `messages`로 오인해 전송 전에 종료됐다(**chat 0회**). probe를 고치고 커밋한 뒤 위 3회만 호출했다. 이 준비 실패도 `summary.json.preflight_failure`에 남겼다.
- 설치기 재실행 성공(plist 정상, LaunchAgent 로드), 설치본/소스 config sha256 일치. 감시 1회 `{"ok":true,"alerts":[]}`. 기존 `last-alerts.json`은 감시기의 정상 no-alert 분기로 해제됐고 수동 삭제하지 않았다. 전후 상태와 기존 +50% 경보는 `watch-*.json`·`watch-install.txt`에 보존했다.

`summary.json`은 모든 호출·준비 실패와 원본 경로, `funnel.json`은 누적 통과/거부와 재현 명령을 담는다. 요청 텍스트·응답·usage·응답 헤더를 `call-*.json`에 보존하고 이미지 데이터는 sha256으로 대체했다. 원본은 `outputs/plannerswap-smoke-20261016-b/`; 작은 텍스트 증거를 이 PR에 복사했다. 파일별 해시는 `SHA256SUMS.tsv`다. #552의 자료는 복사하지 않았다.

**TODO — 조정자:** 다음 E2E 첫 LLM 배치 첫 30 SIM초에서 형식 오류 수·응답 시간·429 수·캐시 비율·실제 자기 RGB 전달을 점검한다. 이번 3회 순차 점검은 동시 배치 부하·MJWarp·E2E/실물 성공 관문을 대신하지 않는다. 다음 대기열은 해당 탐색의 funnel 절대경로를 `rejection_table`에 연결해야 한다.

## 재현 명령과 출처

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_openrouter_upstream.py tests/test_model_endpoint_watch.py tests/test_s4_live_stage.py
python3 scripts/install_model_endpoint_watch.py
python3 scripts/model_endpoint_watch.py
# 유료 호출: 이 작업에서는 이미 3회를 수행했으므로 다시 실행하지 않는다.
PYTHONPATH=. python3 experiments/2026-10-16-plannerswap/probe.py --execute --output outputs/plannerswap-smoke-NEW-ID
```

- [OpenRouter 공식 endpoints API](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints), 2026-10-16 조회(`endpoint.json`).
- [OpenRouter 공식 provider selection](https://openrouter.ai/docs/guides/routing/provider-selection): `order`, `allow_fallbacks`, `quantizations` 명세 확인.
- [llmalt PR #552](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/552): 이전 40회 비교 자료와 추천 근거.
