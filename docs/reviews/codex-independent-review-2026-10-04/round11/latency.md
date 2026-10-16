# R11 — 선택적 Gemini 보고서가 일부 실패 호출의 latency를 두 번 집계한다

**P3, 선택적 visual-team 보고 경로.** 응답을 받았으나 completion JSON이 깨졌거나 본문이 빈 호출은 writer가 동일한 wall latency를 두 필드에 보존한다. 보고서는 그 별칭들을 별개 표본으로 합쳐, 이 실패 유형을 정상 호출이나 timeout보다 두 배 가중한다. 소스 검토와 합성 HTTP 응답만으로 재현했으며 실제 실행의 오류 빈도·평균 지연·통신 조건 차이는 측정하지 않았다.

검토 source는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`다. 이 보고서는 `evaluate_gemini_cohort`의 선택적 독립 RGB visual-team 실행 경로다. 현재 camera-pair pilot, P06 primary PAR2, 과거 실제 성능 비교, SIM 청구식의 결함으로 확대하지 않는다. R10의 시도/lifecycle 보고 누락과 원인이 다른 수치 집계 경계다.

## 실제 writer에서 발생하는 이유

1. [`GeminiProxyCompleter.complete`:153–184](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/gemini_proxy.py#L153-L184)는 HTTP response를 읽은 뒤 `last_latency_ms`를 설정한다. 그 뒤 JSON/choice 파싱 실패나 빈 본문이면 같은 값을 `GeminiProxyError.latency_ms`에 넣는다. 반대로 [HTTP/timeout/connection 오류:120–152](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/gemini_proxy.py#L120-L152)는 error latency만 만들며, 매 호출 초기화된 `last_latency_ms`는 None이다.
2. [planner:200–217](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/gemini_transport_policy.py#L200-L217)는 typed error를 `PlanningError`의 cause로 보존한다. [실행기 failure handler:240–270](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/evaluate_gemini_team.py#L240-L270)는 `audit.wall_latency_ms`와 `inference_error.latency_ms`를 **같은 call_id의 단일 llm_result 행**에 쓴다. 이것은 fixture가 임의로 모순된 JSON을 주입한 경우가 아니다.
3. [`summarize_run`:180–190](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/render_visual_team_report.py#L180-L190)는 top-level, inference_error, audit의 latency 후보를 모두 `extend`한다. 두 필드에 같은 값이 있으면 두 표본이 된다. [mode aggregate와 HTML:378–396](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/render_visual_team_report.py#L378-L396)가 이 배열의 산술평균을 `기록된 평균 wall latency (ms)`로 표시한다.
4. [cohort CLI:96–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/evaluate_gemini_cohort.py#L96-L105)는 실행 orchestration 뒤 이 renderer를 호출한다. 따라서 standalone private helper에만 존재하는 동작은 아니다.

현재 visual-team CLI의 completer는 `require_normal_completion` 기본 False를 사용한다. 이 원고는 opt-in non-normal-completion 오류에 의존하지 않고 기본 설정에서도 도달 가능한 malformed/empty response 두 경우를 사용했다.

## 최소 재현과 음성 대조

`evaluation-latency-repro.py` (Mac 전달본 증거)는 실제 completer에 fake HTTP와 고정 clock을 주고, 원본 실행기의 exception handler 전체 AST 및 정상 audit/행 쓰기 statement를 변경 없이 실행한다. 실제 renderer가 임시 파일을 읽어 summary와 HTML을 생성한다. planner의 이미지 전처리·모델 판단·물리 실행은 실행하지 않았으며, typed cause를 감싸는 원본 `PlanningError`와 source상 같은 연결을 공급했다. 실제 latency benchmark가 아니다.

모든 경우에 호출은 두 번이고 call_id도 두 개다. 첫 호출 latency는100ms, 두 번째는300ms로 고정했다.

| 두 번째 호출 | writer의 audit / error latency | 보고서 표본 | HTML 평균 | call당 한 표본의 평균 |
|---|---|---|---:|---:|
| 정상 응답 | 300 / 없음 | 100, 300 | 200.0ms | 200.0ms |
| timeout | 없음 / 300 | 100, 300 | 200.0ms | 200.0ms |
| completion JSON에 choices 누락 | 300 / 300 | 100, 300, 300 | 233.3ms | 200.0ms |
| completion 본문이 빈 문자열 | 300 / 300 | 100, 300, 300 | 233.3ms | 200.0ms |

결과는 `evaluation-latency-result.json` (Mac 전달본 증거)에 보존했다. 동일 raw 행을 두 번 생성한 현상이 아니라 한 행의 중첩 alias를 두 번 세는 현상이다. 통신 mode의 `llm_calls`는2로 유지된다. 오류 호출이 항상 느리다고 보장되지 않으므로 실제 편향 방향/크기는 이 증인에서 일반화하지 않는다.

별도 검토자가 재실행해 보존 JSON과 완전 일치를 확인했고,11개 source를 pinned Git object와 대조한 뒤 actual planner→writer→report 연결을 다시 읽어 P3 범위로 수용했다. 자세한 범위는 [독립 검증](validation.md)에 있다.

읽은 기존 [`tests/test_visual_team_report.py`:14–47](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_visual_team_report.py#L14-L47)는 top-level latency 하나를 집계하는 정상 형태를 검사하며 이 실제 dual-field error row는 다루지 않는다.

## 수정 방향과 인수 조건

보고 단위를 terminal provider call로 정하고, 한 call의 latency alias 중 정해진 우선순위로 하나만 선택한다. 둘 다 존재할 때 불일치를 진단으로 남길 수 있지만 독립 측정치로 평균내지 않는다. 서로 다른 호출이 우연히 같은 latency를 가질 수 있으므로 **숫자값 자체를 set으로 deduplicate해서는 안 된다**. 과거 schema를 지원하려면 alias fallback은 유지하되 행당/호출당 선택이라는 계약을 명시한다.

인수 조건은 위4경우 모두 call2개→latency2개·평균200ms, call2개의 latency가 둘 다300ms인 경우에도 표본2개 유지, latency가 없는 호출은 측정 부재로 따로 세는 것이다. 이 제안은 reviewer fixture 밖의 구현을 수정하거나 기존 실제 보고서를 다시 계산한 결과가 아니다.

## 재현 범위

`python evaluation-latency-repro.py --repo /path/to/pinned/UGRP`를 실행한다. script는 import 전11개 source의 SHA256을 확인하고 network connect를 차단한다. 표준 라이브러리만 필요하며 생성되는 run/HTML은 임시 폴더 안에 있다. 원본 저장소의 실행 artifact를 읽지 않는다. 정확한 소스는 위 pinned commit에서 복원해야 하며 standalone source bundle을 포함한 파일이라는 뜻은 아니다. 정상 수행 시 stdout을 별도 JSON으로 저장해 보존 결과와 비교할 수 있다.
