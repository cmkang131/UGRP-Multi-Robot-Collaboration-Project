# s4live9 DEV (`research_result=false`)
S3 ca3d51b7을 그대로 사용: 기존 inspect+canonical pan, 같은 epoch 무효 GO/ACK 1회 재요청, 명령 없는 종료 검열(각 기본 off).
원인 raw: 이전 자세 807/1897/2187/1544 오류7/8·ACK 통지 누락1/8·미마무리15호출; s3fix23과 같은 재관측 문제.
등록 inspect는 코드값508/2432/1320/1500(지시의507과1pulse 차이); 기존 보정 그대로, 이동→0.85초정착→새 자기RGB.
[고정 8개 이름·명령·seed](plan.json): no_comm/peer_ko/leader_ko/structured×601/602, v176/7.69.0, LP4·OSMesa·persistent runs.
판정: 재관측·재파지·새GO/ACK·둘째운반≥20mm 각각n/8·추가거리; 최종목표 완료는 별도, 낙하·실패 모두 포함.
둘째운반에서 끝내지 않음: 기존8구간5.45m 완료/실패 또는600SIM·3000wall 상한(미완료); 300call/robot·900/run·18Mtoken/run.
부하<51·여유≥6GiB, 180–300wall 건강 점검·완료 즉시회수; 모델키는Mac 감사프록시/SSH loopback에만.
참고: [Weiss1987 p407](https://www.cs.cmu.edu/~lew/PUBLICATION%20PDFs/VISUAL%20SERVOING/JRA%201987.pdf), [RFC9110§9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2), [Python finally](https://docs.python.org/3/library/asyncio-task.html#task-cancellation).
결과·원본·sha256은 summary.json; 아직 실행 전.
