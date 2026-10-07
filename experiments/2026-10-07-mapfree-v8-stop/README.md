# explore12 — v8 정지/관측 대기 어댑터 버그 수정 사전 등록

2026-10-07 사용자 요청, PR #409. v8 안에서 정지 경로만 수정한다. 기본 off와 v1–v7,
v8의 frontier/monitor/문/B/예산/채점 설정은 보존한다. MuJoCo·렌더·모델 호출 금지.
결과는 [RESULTS.md](RESULTS.md)에 추가하며 기존 v8 결과를 덮어쓰지 않는다.

## 수정 전 코드 진단

기존 `code/integer_episode.py:37–42`는 관측 전 `stop`을 발행하지만 2초를 한 번에 진행한다.
`GridWorld.advance:191–193` → V7CommandOdometry → `OwnCamLocalizer.command:193–196`은
target만0으로 만들고 이전 `vel`은 보존한다. `predict_to:290–300`은 τ=.3s로 이전 속도를
계속 감쇠 적분한다. `ApproachMonitor.filter`의0출력도 같은 하위 경로를 탄다.
따라서 **0 명령 발행은 이미 있었고, 2D 어댑터에서 정지 출력 뒤 잔류 속도를 적용하는 경로**가 문제다.
2초 대기에 monitor/접촉 콜백도 없어 관측1초 만료 이후에도 이 잔류 이동이 계속된다.

원 Nav2는 최종 cmd_vel에서 STOP/invalid source를0으로 내며, 다음 입력마다 현재 source와
polygon을 다시 검사해 안전할 때만 새 요청 속도를 통과시킨다. timeout 뒤0출력 발행을
멈추는 것은 이전 양의 속도 재개가 아니다. 대조·라이선스는 [REFERENCES.md](REFERENCES.md).

**적용 경계:** 이번2D oracle의 cmd_vel 정지 계약을 구현한다. stop/hold/세 축이 정확히0인
최종 명령이면 자기 명령 예측기와 평가용 이동 적분기의 이전 속도를0으로 정리한다.
다음 비영 명령에서 정상 M1 적분을 재개한다. 이동 중 gain/τ/잡음/좌표/접촉/센서 식은 바꾸지 않는다.
실제 로봇의 관성·감속 거리가0이라는 Nav2 보장이 아니다. 공식 문서도 실측 감속을 요구한다.
현실 잡음/실물에 대한 정지거리 검증으로 이 결과를 승계하지 않는다.

관측 대기는 기존10Hz 정수 tick에서 zero twist를 monitor에 보내고 접촉 콜백을 서비스한다.
대기 종료2초와 새 RGB 뒤에만 원 controller 명령을 재개한다. 관측/B 주기3초·예산900s/40m/300관측,
monitor1.2s/.1s/6점/timeout1s, frontier3/1/.75/.33Hz, replan1Hz는 그대로다.
평가용 정답을 stop 판단/제어에 넣지 않는다. 기존 oracle pose 포트 외 추가 GT 입력0.

## 검증·진행 순서 고정

1. 위0명령→잔류 이동의 작은 해석적 반례, stop/hold/monitor0/timeout0/재개 경로 시험.
   off golden·기존 v7 121파일 hash 보존. 실제 world/actor의 정지 배선 시험도 포함한다.
2. 수정 전 v8 **거짓 후보 통로10건·행동 중 접촉2건**은 저장 로그로 건별 원인 표만 만든다.
   이 원인에 대한 문·지도·footprint·monitor 문턱 수정은 금지한다. 관측 대기 접촉14건도 보존한다.
3. 시험 후 수정 코드·소스 freeze 커밋/push → 기존 M/N×s1–s8×7701/7702 **32쌍 개발**
   static/own 각1회. 원본 confirmation 센서 draw split을 유지하고 evidence만 development로 표시한다.
4. 기존 다섯 관문 그대로: 완전성/경계/off, 참 B≥26/32·거짓0, 공통 성공 거리·시간비 각각≤2,
   직접 관측 coverage 중앙≥40%, 충돌/잘못된 문/거짓 후보0·문 시도≥1.
   별도로 모든 관측 대기의 실제 적분 이동량/속도0 및 대기 중 새 접촉0을 검증한다.
5. **개발5/5일 때만** 기존 모든 시작쌍과 중복 없는 새32쌍을 사전 등록·커밋하고1회.
   실패면 여기서 트랙 종료, 새32쌍·잡음 실행 없이 v5–v8 표와 원인을 남긴다. 재튜닝 금지.

raw `/Users/changmin/projects/ugrp/outputs/mapfree-v8-stop/development`; 원본 보존,
ENOSPC=HOST_ERROR. `ugrp_session` 유한 순수2D 실행, wall-time 성능 비교/배타 물리 잠금 없음.
관련1–3 시험 파일만 실행한 뒤 커밋, Co-Authored-By: Codex. PR DRAFT·병합/force/reset 금지.
미추적4파일 보존, 다른 worktree 수정0. TensorBoard는 이전 사용자 생략 지시 유지.
