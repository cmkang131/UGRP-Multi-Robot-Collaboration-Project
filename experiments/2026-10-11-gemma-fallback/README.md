# 2026-10-11 DEV Gemma 예비 프록시

사용자 결정: DEV 순서는 Gemini 구독 → Google AI Studio Gemma 4 31B. 기본 OFF.
본 연구 `main_study_gemini_v1`과 기존 admitted 목록은 바꾸지 않는다.

## 구현

- Mac `scripts/gemma_fallback_proxy.py`는 OpenAI 형식의 텍스트·inline RGB를 `generateContent`로 변환한다. 키는 `security find-generic-password -s ugrp-gemma-aistudio -w`의 메모리 결과로만 읽고 `x-goog-api-key` 헤더에만 쓴다. 키 환경변수·파일·CLI·서버 전송·redirect는 지원하지 않는다.
- `scripts/s4_proxy_relay.py --gemma-fallback`은 명시적 HTTP 429/할당량 초과/5xx 뒤 같은 요청 본문·논리 ID로 Gemma에 1회만 전달한다. 원본 사용자 프록시는 수정하지 않는다. 네트워크·PID·소스 확인 실패는 전환하지 않는다. 영속 journal이 진행 중·완료 응답을 보존하고, fallback 429도 같은 ID에서 재발행하지 않는다.
- `dev_gemini_gemma_fallback_v1` 및 S4 `--gemma-fallback`을 추가했다. 별도 DEV 번들/워크플로 `zone-s4-pair-live-v183-gemma-dev-v1`이 프로필·소스 해시를 기록한다. 기존 own-map E2E 차단은 유지한다.
- 실제 제공자·모델·전환 시도의 상태/usage를 원장과 응답에 넣고 `by_model`, `upstream_by_model`로 집계한다. 실패한 기본 모델의 usage 미제공은 unknown으로 유지한다.
- RPM/RPD는 헤더·429 QuotaFailure의 확인값만 쓰며 모르면 null이다. Mac의 영속 quota 파일·프로세스 잠금으로 분당/일일 예약 및 Retry-After를 공유한다. 일일 소진은 Pacific 자정까지, reset 미확인 429도 자정까지 보류한다. 다른 클라이언트의 사용량은 API 429로만 알 수 있다.

## 실행 절차

Mac 저장 로봇 RGB 1장으로 `PYTHONPATH=. python3 -m scripts.gemma_fallback_proxy --check --image <own-RGB.jpg> --output /Users/changmin/projects/ugrp/outputs/gemma-fallback`를 한 번 실행한다. `models.list`의 유일한 Gemma 4 31B와 실제 이미지 응답이 확인되어야 `--enable` 또는 relay `--gemma-fallback --gemma-state <동일 출력>`이 열린다. `--enable`은 127.0.0.1:8393, relay는 기존 18392를 쓰며 기본 1시간·최대4시간이다. `ugrp_session.py run`으로 시작하고 해당 세션만 종료한다.

서버에는 키 대신 relay identity를 전달하고 기존 역방향 SSH와 S4 러너 `--gemma-fallback`을 함께 선택한다. profile 선택과 relay identity가 다르면 거부한다. 이번 작업에서는 시뮬레이션·상시 서비스·서버 배포를 하지 않는다.

## 검증 결과

`models.list` 실제 조회에서 `models/gemma-4-31b-it`(version 001)을 확인했다. 키체인 키는 읽을 수 있었고 키 필요 없음이다. 커밋 `8e5f678c`에서 저장된 로봇 자기 RGB `tests/fixtures/owncam_pair_v2/grip_613_r1_00059.jpg`를 1회 전달해 HTTP 200·STOP·이미지에 관한 텍스트 응답을 받았다. 모델이 장면을 정확히 이해했는지와 행동 정확도는 미검증이다. 실제 모델1회·물리0·렌더0. 원본·SHA와 응답은 [summary.json](summary.json), [image-probe-response.json](image-probe-response.json)에 연결했다.

실제 응답의 quota 관련 헤더는 없었다. RPM/RPD는 null(미확인)이며 한도를 알아내려고 추가 429를 유도하지 않았다. 기본 off 상태에서 서비스/서버 실행은 시작하지 않았다. 원장·요약은 로컬에 보존하며 DEV이므로 TensorBoard 단계는 생략했다. 후속 안정 idempotency-key 연결은 오프라인 시험으로 별도 검증했다.

## 참고 자료

- [Google Gemma on Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api): REST generateContent, 이미지, systemInstruction, minimal thinking. 공식 문서 열람, 로봇 성능 증거 아님.
- [models.list](https://ai.google.dev/api/models): 페이지 전체 목록과 generateContent 지원을 확인한 뒤 이름을 선택한다.
- [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits): RPM/RPD/TPM, 프로젝트 단위 한도, Pacific 자정 초기화. 실제 계정 숫자는 AI Studio/응답에서 확인해야 한다.
- 기존 `harness/s4_relay_journal.py`의 durable idempotency 방식을 재사용했다. 무응답을 실패 응답으로 간주해 모델을 다시 호출하지 않는다.

오프라인 최종 관련 시험: **214/214 통과**(36.91초, 파일3개). API 모델 전환·쿼터 보류·동일 논리 키의 다른 wire 시도 ID·실제 원장 metadata와 모델별 집계·기존 own-map 차단을 검사했다. 원본 pytest XML은 summary의 절대 경로·SHA로 기록했다. 새 CI 전체 결과는 이 로컬 검사와 구분한다.
