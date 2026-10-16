# s4grip3 — r3 cyan 감지 DEV 비교
기준: 첫5프레임 양측접촉·연속3 zero onset; 조기경보 TP 제외, unknown·재관측 유발 낙하 포함(`research_result=false`).
후보: 기존 + `edge_roi` + 소실5프레임 `absence_vote` + unknown 때1회 팔 `active_reobserve`; 기본·r1/r2 빔 소스 동결.
seed 탐색32200/32201→새 확증52200/52201, 각 유지/외란; 8작업32사례 동시·LP4·job65.4 SIM초·[명령](plan.json), 실행SHA177222d5(v165/7.58.0).
원인: 기존 unknown178 중170은 ROI cyan0/상단 잡음뿐·8은 anchor 획득; 보이는 상자25,190~53,785px. 확증 전경0~2px/회청색면93.2%; 가림과 시야 밖 구분 불가.
결과: 32/32회수, 초기점검8/8; 네 방식 확증 정탐0/2·유지오경보0/2·유발낙하0/2, held unknown168/168·이탈 unknown64/64(지연 산출 불가). 탐색 각1/2, vote 지연0.2초·기존0초.
[summary.json](summary.json)에 n/N·원본·SHA; raw=/Users/changmin/projects/ugrp/outputs/oracle-runs/s4grip3-* (2016 RGB/75.3MB). HOST_ERROR8개 보존 후 동일 묶음 재제출; 다음 후보=팔 고정·자기 카메라 pan 재관측(제안만).
근거: [Marx2023](https://doi.org/10.3390/app13158620), [active vision](https://proceedings.mlr.press/v87/cheng18a.html); 정답은 평가만·모델0·Mac 물리/렌더0·weld OFF·DEV TensorBoard 생략(#426)·PR425 초안.
