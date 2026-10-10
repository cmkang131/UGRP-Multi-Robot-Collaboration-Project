# egomap68: 자기 RGB 장소 확인·귀환 보정 (DEV 사전등록)

- 63001–63006 × 기준/궤적/궤적+homing/궤적+homing+loop=24회,100입자·270+270초·.20m/5현재프레임 불변([등록](prereg.json)); 새 seed 확증·LLM 운반 E2E 아님.
- 원인: eg67 궤적 귀환2/6이나 거짓3/6(.359/1.535/.232m),기존 CSM VTR3/164. 벽 검출·모션·문턱은 동결하고 자기 영상 재인식을 분리한다.
- 참고 자료: [ORB-SLAM2 Tracking L1244–1389](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Tracking.cc), [LocalMapping L279–401](https://github.com/raulmur/ORB_SLAM2/blob/master/src/LocalMapping.cc) 원 코드 확인; GPL3 코드를 vendoring하지 않은 OpenCV 독립 구현,전체 ORB-SLAM 이식 아님.
- ORB ratio .75·초기15·RANSAC .99/300·최종50점; 삼각측량 cos<.9998·양의 깊이·5.991σ² 재투영/스케일 검사. [OpenCV PnP/LM](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html), [H/E의 척도 한계](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html) 확인.
- 단안 척도는 자기 과거 추정 이동으로만 공급; GT/정적 좌표/바닥 평면0. DBoW2 대신 유한 자기 bank 직접 정합,기존 VT&R 키프레임·시간순20이웃/top5 후보·손목 FK 재사용; 상관된 자세 분산은 줄이지 않음. 변경·한계는 등록에 명시.
- visual_homing=orb_pnp_v1(기본 off): 출발 snapshot 정합+시각 상대거리≤.20m인 현재5프레임만 선언; 실패 시 저장 방향으로만 재관측. visual_loop=orb_pnp_v1(기본 off): 귀환10초 주기·수락 PnP만 RBPF 자세 보정.
- Zeil 2003 원문 전문 미확인(초록 확인); 파노라마 차영상 방식은 좁은 고정 FOV에 그대로 적용할 수 없어 미선택. 출발 bank는 체크포인트 이전 RGB/자기 pose만,귀환 중 bank 갱신0.
- 관련1–3파일 시험·첫 프레임 경로 표식 확인 후 커밋/push→x86 전체 묶음;180wall초 초기점검,원본 ARM 해시·Mac fetch-lite. 결과는 summary.json에 전24분모/거짓/정합/위치오차/원본SHA,실패 후 재튜닝0.
