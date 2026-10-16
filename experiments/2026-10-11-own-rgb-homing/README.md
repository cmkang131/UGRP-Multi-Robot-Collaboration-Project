# egomap68: 자기 RGB 귀환 확인·보정 — 미채택

- 사전등록 a90e17e2,63001–63006 × 기준/궤적/homing/loop=24회,100입자·270+270초·.20m/5현재프레임 불변([등록](prereg.json)); 같은 DEV 자료이며 독립 확증·LLM 운반 E2E 아님.
- 위 순서로 B=2/2/2/2,귀환=0/2/0/0,거짓귀환=0/3/0/0(각 /6); 벽접촉 각1/6·로봇접촉0. 종료오차 중앙=.505/.215/.330/.330m. 정상20·벽실패4,HOST/제외/재실행0.
- homing 정합0/3171,loop2/3180(출발점 수락 모두0); 보정2회 XY오차 .575→.343/.354→.348m. 거짓 선언을 막았지만 실제 귀환도 거부해 미채택,결과 후 튜닝0([수치·원본 SHA](summary.json)).
- 주원인: homing의 2476/3171은 유효3D대응 부족. 63003은 실제 시작점 .122m·yaw차12.1°에도 623회 거부; 첫 참조의 유효3D점44<수락50. 다음 후보는 출발뷰의 시차·겹침을 확보하는 능동 teach이며 추가 실행0.
- visual_homing=orb_pnp_v1 / visual_loop=orb_pnp_v1(기본 off): 자기 RGB·기억 pose·명령 FK만; 출발 재확인 또는 귀환10초 주기 PnP 보정. H/E의 단위 translation을 m로 쓰지 않으며 GT는 채점만,상관된 분산 축소0.
- 참고 자료: [ORB-SLAM2 Tracking L1244–1389](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Tracking.cc),[LocalMapping L279–401](https://github.com/raulmur/ORB_SLAM2/blob/master/src/LocalMapping.cc),[OpenCV PnP](https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html) 원문 확인. ratio .75·초기15·최종50·양의 깊이/5.991σ²; 자세·점 공동 최적화를 포함한 전체 ORB-SLAM의 성능 판정이 아님.
- 적용 차이: DBoW2 대신 유한 bank 양방향 BF,시간순20이웃·top5,척도는 자기 추정 이동·기존 VT&R keyframe/CAD 마스크 재사용(GPL 소스 복사0). Zeil 2003 전문 미확인(초록만 확인),파노라마 전제는 좁은 FOV에 미적용.
- 관련27시험·초기24/24·표식51924/51924·off/궤적 72/72파일 bytes 동일. 원본52836파일 ARM 해시검증,Mac은 요약 약650KB+진단JPEG3장42KB만; 경로/해시는 summary.json. PR405 DRAFT,CI 대기·병합0.
