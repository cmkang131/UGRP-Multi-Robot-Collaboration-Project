# egomap67: receive 연결 + 지나온 차체 영역 귀환 (DEV 결과)

- 사전등록/실행 `45bdb756`: 같은 63001–63006 × 기준/lookahead/own-free+궤적/조합=24회,100입자·접근270+귀환270초·.20m/5프레임 고정([등록](prereg.json)); 새 seed 확증·LLM 운반 E2E 아님.
- 가속 receive 연결 수정·기본 off 유지: 관련3파일33시험,6조건 실제 receive probe 통과; 첫 프레임/180wall초 점검24/24·전체 표식46988/46988·off 기존6파일×6seed bytes36/36 동일.
- 위 조건 순서 B 도착=2/2/2/2(각/6),귀환=0/0/2/0(각/6),거짓 귀환 선언=0/0/3/2,벽 접촉=1/1/1/3; 정상종료18+물리실패6,HOST/제외/재시도0. 회전60.0/52.2/57.7/21.4%,반전1271/762/1548/396.
- >3σ 프레임9353/13611·6272/13484·5118/10591·3140/9302; 종료 위치 오차 중앙 .505/.278/.215/.304m. 궤적 단독의 유효 B+귀환2/6(63003·63006),미채택: 거짓 귀환3/6 실제 시작점 거리 .359/1.535/.232m.
- 궤적 단독 귀환 경로3821/3821프레임 확보; 조합은1350/2572 경로 없음(63002의 자기 자세 점프 .738m,footprint 4성분·간격 .361m). 자세 점프 보간0; 다음 후보=기억 궤적에 수락된 자세 보정 일관 적용·시작점 자기 관측 재확인,문턱 완화0.
- VTR 제외: 이전3/164승인,모호82(gap 중앙−.0635<.5)·잔차27(.171>.15m)·중첩22(.545<.60); 기준 변경0([진단](diagnosis.json)). FSM도 이번 물리 off,실제 fallback 연결은 probe로 검증.
- 참고 자료: [Nav2 footprint clearing L494–525](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/plugins/obstacle_layer.cpp#L494), [convexFillCells L374–478](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/src/costmap_2d.cpp#L374),BSD; 기존 포트로 자기 과거 차체 .28×.24m만 귀환 costmap에 보존,벽 지도/관측 덮음 불변·GT 제어0.
- [summary.json](summary.json)에 판정·원본·SHA: oracle-x86/기존 ARM `~/ugrp-sim/arm/egomap67-batch` 24회47900파일 검증. Mac `outputs/oracle-runs/egomap67-batch`는 비미디어22회+2회부분(ENOSPC),집계/표식은 회수; 원본 손실·삭제0,PR #405 DRAFT.
