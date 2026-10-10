# egomap69: 회전 횡축 오차와 시각 위치 추정 설계
- 방법 사전 고정500f3144,분석수정cdacbec1/추가진단dad60c70; 기존63001–63006 6/6(정상5·벽실패1,제외0),물리·모델·제어/문턱 변경0. 독립 확증/E2E 성공 아님; [전체 수치·설계·원본 SHA](summary.json),[시간별 오차](error-budget.png).
- 명령13605구간: 전진 예상/실제50.416/50.459m; 좌/우 회전각 배율 .9996/1.0004. 회전당 옆 이동 예상/실제는 좌−2.818/−.292mm,우−1.805/+.294mm로 횡축 모델이 문제(전진 때도−.402/+.016mm). GT는 사후 평가만,미끄러짐/보정표 결함의 물리 원인은 아직 분리 불가.
- checkpoint GT 1회 초기화 DR 경로RMSE 중앙 .888m; GT yaw만 대체 .817m,회전 XY만 대체 .154m,횡축만 대체 .102m. 이는 같은 명령의 평가용 오차 분해이며 채택·구현 성능 아님. 실제 RBPF .420m,국소 정합27/243·proposal 이후 순간 XY개선638/1340,악화702/1340(입자 선택·Manhattan 포함).
- B2/6 유지:63001 위치/경로 표류(최근접1.660m),63002 실제B217프레임이나 근접701 중 패치없음691·미확인10/hold618,63004 pickup 바닥 오확인(기억B가 실제B 밖5.004m),63005 경계 .066m까지 왔지만 기억 중심 .20m 미진입. 정확한 위치만으로 네 실패가 모두 해결되지는 않는다.
- RGB 고정549/13611표본: ORB 중앙213,50미만1/549; 인접543쌍 대응81/E인라이어74 중앙. 2D특징 부재보다 metric 3D지원·지속 추적 문제. 실물 경기장 사진 없음→sim/real 질감 차이 미측정,환경 변경0.
- 주 설계: 원본 ORB-SLAM3 연속 추적/local BA를 재사용,자기 명령은 약한 SE(2) prior·척도로 두고 독립 시각 이동에서 횡축까지 추정; B·경로도 keyframe과 함께 보정. 명령융합은 원본 기본 기능이 아닌 명시적 어댑터다. 5.5m에서 .20m 이내의 단독 yaw/scale 예산≈2.08°/3.64%; .888→.154m은 개선 여지만 제시,성공률 예측 없음.
- 대안: 구조적 점·선 SLAM+자기 초음파 거리. 현재10719유효 중10571(98.6%)이≤.10m(중앙.054–.055m)여서 자기 가림 확인 전 적용 부적합; 긴 판독도 outlier일 수 있음. SIM 거리σ(1m=.013m)는 제조사 실측 정밀도가 아니다.
- 참고 자료: [ORB-SLAM3 원문](https://arxiv.org/pdf/2007.11898)·[공개 코드](https://github.com/UZ-SLAMLab/ORB_SLAM3),[단안 PL-SLAM 원문](https://alexandervakhitov.github.io/scripts/publications/files/pl-slam-2017.pdf),[UMBmark 원문](https://www.johnloomis.org/ece445/topics/odometry/borenstein/paper59.pdf),[Censi 보정 코드](https://github.com/AndreaCensi/calibration)(전문 미확인),[Hiwonder 규격](https://www.hiwonder.com/products/glowing-ultrasonic-sensor). 적합성/원본과의 차이는 summary.references.
- 변경 평가기4시험 통과,생산 모듈 바이트 변경0; 원본manifest54파일+추가원장6 ARM사본60/60 SHA일치. Mac은 fetch-lite JSON·선택JPEG2장만,PR405 DRAFT·CI대기0. 새 실행 없이 설계까지만 완료.
