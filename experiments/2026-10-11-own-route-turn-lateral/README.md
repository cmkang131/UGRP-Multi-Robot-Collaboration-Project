# egomap70 — 회전 횡이동 독립 보정·B 구역 도착 (DEV)
사전등록: [prereg.json](prereg.json); 평가 63001–63006 × baseline/calib/calib+traversed/calib+traversed+zone+색 =24회, B270+귀환270초; prefix 재계산0.
보정 70001–70005: 앞3 적합/뒤2 확인, 좌우 단발·연속 회전과 양방향 사각 주행; Y만 적합, X/yaw/잡음 불변. 확인 방향×기동별 횡오차 RMSE 악화없음일 때만 평가.
옵션 기본off: motion_model_turn_lateral_v2, arrival_zone=remembered_cells_v1, B_color_confirmation=material_hue_size_v1; 마지막 조건 두 효과는 분리 주장 불가.
B 새 판정=자기가 확인한 바닥 칸 안5프레임; 기존 .20m·현재영상·5프레임도 별도 기록. GT는 사후 도착/오차 평가·독립 모델보정 측정에만.
원인: eg69 좌/우 횡이동 예측 −2.818/−1.805mm 대 실제 −.292/+.294mm; 63004 pickup hue110 vs B112로 색 단독 미분리(실행 전 진단); B 규격 .6×1.4m와 기존1.2 허용폭의 전체 크기 확인 추가, 부분조각 보류.
참고 자료: [Borenstein–Feng 1996](https://doi.org/10.1109/70.544770), [원문](https://web.cecs.pdx.edu/~mperkows/CLASS_479/S2006/Paper-correction-odometry-error.pdf): 양방향 기동·반복으로 체계/산포 분리. 차동차륜 공식 대신 메카넘 명령별 Y 평균곡선, 공간 제약상 .26m 사각으로 변경. [Nav2 footprint](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_costmap_2d/src/footprint.cpp#L40-L66) 최대반경 팽창으로 보정 fixture 검사(.02m는 기존 레포값).
참고 자료: [OpenCV HSV](https://docs.opencv.org/4.x/df/d9d/tutorial_py_colorspaces.html): 기존 HSV+연결성/형상 유지, 알려진 B/pickup 재질의 hue 최근접 분류(동일 사전확률); 기존 v3 minAreaRect 규격 확인, 위치/정답 마스크 입력0; 부분시야 recall 비용.
Mac 물리/재생0, x86 영속 raw·3분 초기 표식 확인·ARM SHA 보관·Mac 가벼운 회수; 새 물리 전 관련 시험과 커밋, 결과 후 재튜닝0.
결과: 보정5/5·보류관문6/6(횡 RMSE 2.15–2.59→.37–.53mm), 앞선HOST5·벽실패5도 보존. 18시험·8SIM초 스모크41/41표식 정상; 평가0/24(용량대기), E2E 미검증. [summary.json](summary.json), PR405 DRAFT.
