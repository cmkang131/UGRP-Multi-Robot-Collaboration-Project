# s4grip3 — r3 cyan 감지 DEV 비교
기준: 첫5프레임 양측접촉, 연속3 zero의 첫 프레임을 onset; 조기 경보는 TP 제외, unknown·재관측 유발 낙하도 집계(`research_result=false`).
후보: 기존 + 하단 `edge_roi` + 소실5프레임 `absence_vote` + unknown 3회 때1회 `active_reobserve`(같은 명령상 집기점·팔 pitch -55°, .6초 이동+.3초 settle); 기본/빔 소스 동결.
seed: 탐색32200/32201, 새 확증52200/52201; seed당 유지/외란, 8작업32사례 동시·LP_NUM_THREADS=4·job65.4 SIM초; [명령](plan.json).
원인: 기존 held unknown178 중170은 ROI cyan0, 상단 잡음120px; 보이는 상자는25,190~53,785px. 가림/FOV와 그림자는 프레임 숫자로 감사한다.
판정·초기점검·원본·SHA: [summary.json](summary.json); raw=/Users/changmin/projects/ugrp/outputs/oracle-runs/s4grip3-*; 아직 실행 전.
근거: [Marx2023](https://doi.org/10.3390/app13158620) 시간 변화·관측 영역, [active vision](https://proceedings.mlr.press/v87/cheng18a.html) 가림 재관측; depth/정답 제어 입력 없음.
DEV TensorBoard 생략(#426); 모델0·Mac 물리/렌더0·카메라 배치/FOV·weld OFF 유지, PR425 초안.
