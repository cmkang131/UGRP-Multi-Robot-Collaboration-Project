# s4live11 DEV (`research_result=false`) — 4완료·4호스트 확인 대기
BAND_CLIPPED 556/556은 자기 RGB의 파지 표식이 유효 영상 경계에 걸려 재파지 거리 판정을 거부한 횟수다(34.1mm/4124점); 파일 손상이 아니다.
소스 `4316bdd5`, v182/workflow7.75.0; 기본off 429 재시도·응답 예시·기존 clipped_backoff, S3 제어130파일 유지; 관련 오프라인47/47.
[고정 8명령](plan.json): 4조건×601/602를 4개씩, 900SIM/10800wall; 초기 점검8/8, 중간 소스 변경 없음.
완료 seed601: 목표B착지0/4, 8구간운반3/4, 누적4.20–5.86m·낙하0/4; 목표오차0.446–0.526m 또는 재파지잘림828/828.
완료분 모델1203POST·11,033,579보고토큰·형식유효1201/1203; 429/재시도0, 실제 과금unknown; 물리정지 재시도는 오프라인 주입만 검증.
seed602는54–55SIM에 SSH가 끊겼다(전원RUNNING); 최종상태·원본 미확인4건, 로봇실패로 합산하지 않음. 복구 뒤 원본 확인·같은SHA로 영향분만 재제출.
완료 원본140,031파일 ARM전체SHA 일치, Mac fetch-lite1523파일 일치; 미완료 x86원본 삭제·덮어쓰기 없음. [판정·원본·해시](summary.json).
429는 지수백오프+jitter·Retry-After·동일요청/단일행동; 기존 프록시는 native schema 미지원이라 짧은 예시+엄격 검증. PR425초안 유지.
참고: [Google 재시도](https://docs.cloud.google.com/storage/docs/retry-strategy), [RFC9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after), [Gemini 출력제약](https://ai.google.dev/gemini-api/docs/structured-output), [ROS2 행동](https://design.ros2.org/articles/actions.html).
