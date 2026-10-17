# R3 62 mm 편향 원인 표 — 장경로 진단 전

확정된 단일 원인은 없다. 20개 예측의 끝 오차 평균 (+55.31,+27.37) mm,
표준편차 (9.82,6.53) mm는 단순 독립 표본 잡음보다 같은 방향 편향이 남음을
보인다. 평가 정답보다 후보 우도가 높은 갱신은110/880뿐이다. 나머지는 같거나
낮으므로 “벽 인식 오차가62 mm라서” 또는 “정답보다 잘 맞는 잘못된 최적점”으로
전체를 설명할 수 없다. GT는 이 진단의 평가 열에만 쓰였다.

|항목|MC20 적용·근거|Nav2 기준과 차이|현재 판정|
|---|---|---|---|
|카메라 외부 파라미터|R3 자기 명령 FK 위치/각 P95=1.013 mm/.268°, 갱신별 벽잔차 P95 최대171.66 mm. 실제 카메라 평가 재투영은37.32 mm까지 감소|고정 laser TF 대신 자기 명령 FK로 매 RGB 접점을 투영|먼 바닥 접점 투영에서 작은 각도 오차 확대가 확인됨. 정확히 끝62 mm를 만드는 인과 분해는 확인 안 됨|
|입자 수|최소500/최대2000, R3 전20개 수렴·오수렴0|공식 기본값과 같음; 초기전역10만과 별도|입자 증량으로 해결된다는 근거 없음. 동일 시드 재현의 실제 수/ESS는 별도 bias 계수|
|리샘플|측정 갱신마다 KLD 다항 재표본, interval1; recovery slow/fast=0|기본 주기·회복 기본값과 같음|반복 재표본의 샘플 빈곤 가능성은 남음; 수를 임의로 튜닝하지 않음|
|측정 갱신|자기 누적 x/y .25 m 또는 yaw .2 rad, 자기 발행 servo 자세 변화에도 새로운 뷰로 갱신|운동 문턱은 기본값, servo 변화 강제 갱신은 RGB 어댑터 차이|10 Hz 프레임이10 Hz 독립 측정은 아님. 실제 간격을 재생 계수|
|이동 노이즈 α1–4|자기 영상/명령 R1–R2 동결 [.075572,.000112716,.081227,.014194], 정답 피팅0|Nav2 기본 α는각 .2; 포트는 DifferentialMotionModel. MasterPi는 holonomic이므로 OmniMotionModel과 별도 비교 필요|회전 중 작은 lateral delta가 두 큰 반대 회전으로 분해되면 확산할 수 있음. 원본 누적 delta/모델 표준편차를 계수하며 GT에 맞춰 α를 재조정하지 않음|
|측정 무작위 항의 range_max|포트는100 m를 고정, RGB 투영은기존4 m guard|Nav2 노드는 실제 LaserScan.range_max와 설정 상한 중 작은 값 사용|공식 노드와 어댑터 차이 확인. 현재 MC20의100 m를 사후 변경하지 않으며 이번 비교 녹화도 같은 프로필을 동결. 별도 수정 후보가 필요|
|대표 자세|전체 입자 가중 평균/원형 yaw, 전체분포 P95·측정전 ESS 관문|Nav2는 최대질량 cluster 평균을 발표하고 전체 covariance를 표시|다중 모드 평균 차이가 존재할 수 있음. 군집을 구현/채택한 결과로 과장하지 않음|
|벽 점·자기 지도|정적 벽 거리장만 우도에 사용, 자기 지도는별도기록|likelihood_field의 cubic sum·σ.2·z_hit/z_rand .5/.5·거리상한2m 유지|초기15 mm 잔차는 한 프레임이며 꼬리/이동분포와 같지 않음. 자기 서브맵 오차 강화는 차단|

장경로는 MC20의 미개선 기록을 통과로 바꾸지 않는다. 조정자가 별도로 승인한
실제 공개 시작 상자·native v7 진단1라운드다. 실제 ≥3 m/회전을 평가한 뒤 동일
프레임의 OFF와 AMCL 구간·끝·최대 오차를 비교하며, 적재 구간은 실제 발생한
경우에만 표시한다. 분포가 미수렴하면 주행을 시작하지 않으며 교사·학생·LLM
성공과 위치추정 진단을 합산하지 않는다.

참고 자료(2026-10-17 확인):

- [Nav2 AMCL 설정 기본값](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/)
- [Nav2 range_max와 대표 cluster 구현](https://api.nav2.org/nav2-rolling/html/amcl__node_8cpp_source.html) 원본 소스725–730, 803–817, 843–853행.
- [Nav2 OmniMotionModel](https://api.nav2.org/nav2-rolling/html/omni__motion__model_8cpp_source.html)
- 현재 vendor는 `harness/mapbuild_amcl_vendor/NOTICE.md`의 고정 소스/라이선스와 함께 보존.
- 계수: `operations/r3-likelihood-summary.json`, `operations/camera-summary.json`, `wall-observations.md`.

동일 R3 coarse trial0의 동결 예측 재현 차이는0. 44갱신 모두501입자(원문 `count>limit` 종료 때문에 최소500에서1개 더), 갱신 간격 중앙.8/p90 1.0/최대1.5 SIM초. 측정 전 ESS 최소365.06/중앙439.61. 이동 모델이 넣는 1회 전진 잡음 SD는 중앙24.84/p90 26.18/최대27.28 mm이며, 회전 SD 최대3.606°. 최대 전진 SD 갱신 t21.5에는 실제 입력 delta translation1.267 mm/yaw.228956 rad, rot1=0이었다. 따라서 이 자료에서 큰 rot1 역회전 분해가 주원인이라는 가설은 지지되지 않는다. 회전 자체의 alpha4 항이 전진 확산을 넣는 표준 differential 모델의 성질은 확인된다. 이것이62 mm 편향 전부를 설명하는 인과 검증은 아니다. 근거 operations/bias-r3.json, scripts/mapbuild10_bias.py; 물리/렌더0.
