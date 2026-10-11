# s4live11 DEV (`research_result=false`)
BAND_CLIPPED 556/556은 r2 집기 표식이 유효 영상 경계에 걸려 재파지 거리 판정이 거부된 횟수이며, 다섯째 운반을 막았다(34.1mm/4124점; inspect508 보정 정상).
v182/workflow7.75.0: 기본off 후보는 429 재시도·응답 계약 예시·기존 S3 clipped_backoff; S3 제어 130파일 유지.
[고정 명령·seed601/602](plan.json): 4조건씩 2wave, 900SIM/10800wall; 이전 v181은 관측 기준선이며 같은 seed 재탐색.
429는 동기 호출 안에서 물리/SIM 정지, 지수 백오프+jitter·Retry-After 존중, 최대6재시도/300wall; 같은 요청·단일 최종행동·각POST 원장.
프록시가 native schema를 전달하지 않아 네 필수 키와 현재 request_id 예시를 매번 제공; 의미 검증·lease·GO/ACK는 그대로.
판정: 전체8운반구간·목표B 20mm·최종바닥0.5s 안정, 누적 지지거리/순환/낙하·호출/대기/토큰; 중간 성공 없음.
초기180–300wall 각 실행 점검; API 보류는 별도 분류, 예외·정체는 소유 실행만 중단. 서버 평가·전체SHA, Mac fetch-lite.
결과·원본·해시는 [summary.json](summary.json); 실제 과금/프록시 내부 시도 수 미공개는 unknown으로 기록.
참고: [Google 지수 백오프](https://docs.cloud.google.com/storage/docs/retry-strategy), [RFC9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after), [Gemini 출력 제약](https://ai.google.dev/gemini-api/docs/structured-output), [ROS2 행동/취소](https://design.ros2.org/articles/actions.html).
