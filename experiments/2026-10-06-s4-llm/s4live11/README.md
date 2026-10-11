# s4live11 DEV (`research_result=false`)
BAND_CLIPPED 556/556은 자기 RGB 파지 표식이 유효 영상 경계에 걸려 거리 판정을 거부한 횟수다(34.1mm/4124점); 파일 손상이 아니다.
실행 `4316bdd5`, v182/workflow7.75.0; 기본off 429 재시도·짧은 응답예시·기존 clipped_backoff, S3 제어130파일 유지; 관련시험47/47.
[명령·seed](plan.json): 4조건×601/602, 4개씩·900SIM/10800wall; 재부팅 중단4건은 보존하고 동일SHA/명령으로 재실행, 초기점검12/12.
최종 목표B착지0/8·낙하0/8, 8구간운반3/8, 누적0.154–5.858m·운반구간1–8개; 연구/E2E 성공 아님.
원인: 통신시간초과→lease4/8, 완료경로 목표오차0.446–0.526m 3/8, 재파지잘림828/828·후진2회 소진1/8.
최종1264송신시도·11,455,094보고토큰·형식1254/1256; 중단분71저장요청/567,336토큰 별도, 합계12,022,430토큰·사용량unknown9건·과금액unknown.
429/재시도 관측0; 재시도 중 물리정지는 오프라인 주입만 검증. 응답미회수8건은 완전 대조 제외(1256/1264); 종료 뒤 추가행동·메시지0.
원본12시도 ARM전체SHA, Mac fetch-lite만; [summary.json](summary.json)에 판정·원본·해시·통신한계. 원격CI25통과/8실패, PR425초안 유지.
참고: [Google 재시도](https://docs.cloud.google.com/storage/docs/retry-strategy), [RFC9110](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after), [Gemini 출력제약](https://ai.google.dev/gemini-api/docs/structured-output), [ROS2 행동](https://design.ros2.org/articles/actions.html).
