# S4 호출·문맥 축소 DEV 후보

기본 OFF `event_coalesce_v1`은 `event_driven_llm` 위에서 동작한다. 자기
진행 단계 재확인을 생략하고 inbox는 다음 자기 결정 창/GO/ACK/이상 관측에
함께 읽는다. 최대 60 SIM초 뒤에는 메시지만으로도 호출한다. 수신·원본·메시지
ID는 보존하고 새 요청에서 모든 미독 메시지를 유지한다. 공통 scheduler의
예산·재시도·영속 수신 lane을 사용하며 네 조건에 같은 규칙을 적용한다.
열려 있는 자기 결정 창에서 명령이 거절되면 창당 1회 수정 기회를 보존한다.
같은 로봇의 common/message lane은 앞 응답이 끝날 때까지 묶는다.
명령/GO/held 응답을 재생하거나 성공 판정을 만들지 않는다. 통신 지연과 입력이
바뀌므로 과거 cohort와 합산하지 않는다.

`context_trim_v1`은 마지막 실제 명령+최신 명령/거절, 모든 미독 메시지와
발신자별 최근 읽은 메시지, 발화 잔여량을 보존한다. 이미 읽은 이력의 수만
요약하고 본문은 생성 요약하지 않는다. `map_as_image_v1`은 기존 지도 그림의
바이트를 유지하며 `static_map` 텍스트를 제거하는 **과거 지도 진단** 토글이다.
자기 입력 `compact_prompt_v1`과 함께 쓰면 authored 지도 그림도 계속 제거한다.
기존 그림은 B 위치를 포함하므로 자기 지도/B 입력으로 승격하지 않는다.
자기 관측으로 만든 지도 그림은 이번 기록에 없으며 만들거나 대체하지 않았다.
2,034토큰 기준 입력은 이미 지도 글·그림 모두 없는 compact 영어 입력이다.

다중 키 5xx는 키 쿨다운 없이 1/2초+jitter 후 다른 키로 최대 2회 재시도한다.
Retry-After가 5초를 넘거나 재시도 소진/다른 키 부재이면 HOST_ERROR로 종료한다.
403/429 쿨다운·공유 예약은 유지하고 모호한 timeout은 재발행하지 않는다.
최초 실패 수, upstream 시도/응답 지연, 재시도 수·대기, 최종 실패를 journal과
원장에 보존한다. 실제 서비스 재시작·실행 receipt 변경은 포함하지 않는다.

## 검증 계획

- s4live11 8건(seed602 HOST_ERROR 포함)의 모든 저장 요청·누락 wire 보충분을
  재생하고 사건별 수, 생략 사유, 과거 행동의 문자 그대로 일치/continue·held
  비중, 변경된 비연속 행동을 기록한다. 바뀐 입력의 모델 결정은 추정하지 않는다.
- 로컬 regex 토큰 추정은 이미지 제외임을 표시하고 실제 countTokens를 별도로
  쓴다. 5개 저장 입력×기존/축소 2개, 생성 최대 30회(재시도 포함), countTokens와
  models.list는 별도 집계한다. 실패한 쌍은 일치로 세지 않는다.
- 물리/렌더 0. v184 준비 adapter의 실행 차단과 기존 입력 경계를 유지한다.
  신규 runnable ID는 만들지 않고 옵션·cohort key·소스 해시를 기록한다.

## 참고 자료

- [ROS2 Actions](https://design.ros2.org/articles/actions.html): 실행 중 feedback과
  목표/결과를 분리하는 표준 방식. 이를 자기 실행 상태/결정 창 구분에 적용한다.
- [LLMLingua-2](https://arxiv.org/abs/2403.12968): 추출식 문맥 압축 연구(초록 확인).
  모델 기반 compressor는 도입하지 않고 명시적 필드/이미 읽은 이력만 줄인다.
- [Google retry](https://ai.google.dev/gemini-api/docs/troubleshooting): 짧은
  exponential backoff+jitter·횟수 제한. 5xx를 quota cooldown과 분리한다.
- [Google tokens](https://ai.google.dev/gemini-api/docs/tokens): 이미지까지 포함한
  countTokens와 실제 usage를 regex 추정과 구분한다.

결과와 원본 위치·SHA는 후속 summary.json에 기록한다. 이 자료는 개발 탐색이며
다른 로봇의 결과·물리 완료·새 조건 일반화의 근거가 아니다.

- [2026 ECIR compression evaluation](https://arxiv.org/abs/2604.02985): 초록의
  압축 비용/디코딩 지연/품질 분리 측정 방법을 참고했다. 로봇 결과 근거로 사용하지 않는다.
- [LLMLingua 공개 코드](https://github.com/microsoft/LLMLingua/blob/main/llmlingua/prompt_compressor.py):
  구조화된 필드 보존/압축 인터페이스를 확인했다. 추가 압축 모델을 실행하지 않는다.
