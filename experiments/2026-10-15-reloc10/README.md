# reloc10 — 실행 전 기록

기준 carry05e3e61f(PR505), selfmap a18b1f84(PR506). 새 토글은 기본 off, 이전 결과와 합산하지 않는다. 현재 실제 검증은 진행 전이다. GCP 직접 확인은 gcp1/n4-highcpu-64에서 최대3라운드, 라운드당 회전4방향+93571 최대60SIM초+93261 최대60SIM초다. 동시 자기실행≤4/전체≤40, 모델0/학습0, 정답은 평가와 오프라인 계수 계산 전용, 자기 RGB만 사용한다.

## 원본 원장 진단

reloc9 회전 원장411행의 보고값과 재계산은 일치한다. 90L1.01953/180R1.14499. 기존27구간 방향별 최소제곱 계수는 좌0.64078/우0.55299, 별도15구간 좌0.53777/우0.62978로 방향 효과가 코호트 사이에서 뒤집힌다. 이전 경로의 방향·회전각·장소 효과는 혼입돼 있으며 좌우 비대칭만으로 전부 설명할 수 없다. 새 보정은 원래 reloc9 진단90L/180R만 보정 자료로 사용한 좌0.586523/우0.658696 계수이며 새4방향을 검증 전용으로 둔다. 양방향180도는 누적 평가 yaw로 계산해 wrap 경계 오류를 막는다. 구간 경계/정지 꼬리 수치는 후속 분석에 기록한다.

93571 등록0/978: 센서 미갱신935, PF미해결732, xy공분산기각940, yaw공분산기각948, 독립축없음620(중복 집계). 자연 특징928/978회 insufficient_matches, visual_update42. 정적 특징2개679회(False update 기준; 전체 히스토그램 original-diagnosis.json), PF해결246이지만 전체 신뢰조건을 만족하지 못했다. 원본벽가드off라 등록실패를 reloc9 가드 탓으로 돌릴 수 없다. 자기RGB6장(19.2–35.3SIM초) 직접 확인: 단색벽/큰체커, 같은 모서리 반복. 현재 정적관문을 낮추지 않고 30초 뒤 종료되는 버퍼를 최근30초 rolling buffer로 바꾸며 기각사유·특징종류·벽열을 보존한다.

최소 정착효과는 좌0.103543/우0.103581rad. 2도 허용은 절반보다 작았다. 공통 `sim/settle_pulse.py`를 release20 **e897b0c2c96ad99cb0a3f5eb3cc255d2686bba09**에서 바이트 그대로 복사했다. `harness/reloc10_settle.py`는 잔차비례 요청을 기존 보정 펄스 격자에 양자화하고 0.6 quantum deadband/연속반전3회 제한을 쓴다. 실제 발행된 안전펄스만 반전 누적한다.

벽가드는 변경하지 않았다. 기존 진짜벽3,237→2,849(-388/-12.0%), 체커근접621→606(-15/-2.4%)를 그대로 보존하고 손실 감소를 주장하지 않는다.

## 변경·경계

carry `reloc10_rotation_calibration_v1`, selfmap `reloc10_settle_v1`/`reloc10_registration_v1` 기본false. carry의 reloc9 계수와 reloc10계수는 상호배타. XY/혼합회전은 그대로다. `UGRP_REMOTE_LOCAL_ROOT` 선택 환경변수는 원격 runner의 로컬 회수위치만 허용 worktree로 지정하며 기본경로는 그대로다. GCP원본은 VM 영속디스크에 보존한다.

## 참고 자료

- [Borenstein & Feng1996, Measurement and Correction of Systematic Odometry Errors](https://ieeexplore.ieee.org/document/544770): UMBmark의 양방향 계수 식별 원칙을 참고. 이 실험은 사각경로 UMBmark 전체 수행이 아니며 메카넘에 차동구동 수식을 그대로 적용하지 않는다.
- [Probabilistic Robotics, motion model chapter](https://robots.stanford.edu/probabilistic-robotics/corrections1/pg122-139.pdf): 발행명령 이동모형과 관측보정·불확실성 구분.
- [Quantized feedback limit-cycle analysis](https://arxiv.org/abs/1701.07482), [MathWorks quantization](https://www.mathworks.com/help/fixedpoint/quantization.html): 양자화/주기진동과 deadband. 0.6/3회는 공통모듈 설계값이며 일반 안정성 정리가 아니다.

## 첫 GCP 라운드(실패 포함)

carry 실행소스0fb980e6, selfmap442f94eb(미push). 회전 4/4 통과: 90L1.02098/90R0.94950/180L1.04208/180R0.94614. 좌0.586523/우0.658696 계수는 이4구간에 재맞춤하지 않았다. 원장/manifest 재계산·자기RGB6장 직접 확인. 원래2구간 정지꼬리는 좌0.00741rad(0.424°)/우0.00113rad(0.065°)이며 내부회전비 좌1.062–1.068/우1.121–1.218로 경계만으로는 설명되지 않는다.

selfmap은 새 정착이벤트의 reason 키 충돌을 소스에서 발견해18.8SIM초에 감독정지(HOST_ERROR). 원본189행/정적등록0/189/자연보정27/자기RGB6장 직접 확인. 키 충돌 수정과 실제 executor→dwell 회귀시험을 추가했다. carry에서는 이전 실행기의 평가TOP 검토촬영을 발견해 즉시 감독정지했다(제어입력으로는 사용하지 않음). 다음 소스의 기본off `reloc10_own_review_only_v1`을 새 계획에서 켜 TOP 촬영 자체를 없앴다. 이 두 중단을 완료 성공으로 세지 않는다.

두 번째 라운드에서는 원래 smooth와 별도 texture를 같은93571로 비교한다. PR511 병합SHA db0a6858f6387e9048d4a37e78bc8eefd2ead484의 natural_scene_texture.py/152개 자산을 그대로 복사했다. 원래 render_profile API는 이 이름을 지원하지 않아, 기존 own-map 장면 인스턴스의 XML 변환 뒤에만 질감을 적용하는 어댑터를 붙였다. 자산해시/컴파일된 픽셀 검증은 GCP에서 수행하고 물리/카메라/FOV는 바꾸지 않는다. smooth와합산금지. 로컬회귀 carry9/selfmap12 통과(전부 비물리).

## 두 번째 라운드와 마지막 수정

회전4/4 재현. smooth93571은 정착6회·시점관측6회를 마쳤다. 마지막20SIM초 회전51/인접부호반전3(기존100/99)이며 목표별정착반전은 이벤트 원장에서 별도검증한다. 등록0/456, 45.5SIM초에 selfmap4_relocalization_exhausted로HOST_ERROR. 공분산가드를 낮추지 않는다. 평가전용 궤적과 비교하면 PF resolved341회 중10cm/5도 안0회, xy오차중앙1.030m/yaw2.510도다. PF의해결표시가 위치정답이아님을 확인했다.

등록 버퍼가 현재 SLAM보정 전후의 좌표를 섞는 위험을 없애기 위해 reloc10토글에서만 별도 자기명령 오도메트리로 각 프레임을 고정한다. PF·현재SLAM·정답과 별도이며 정답은위오차집계에만 썼다. 교정없는 하나의명령좌표계를 유지하는 경계시험을 추가했다. 자연특징·등록공분산·방향기하의관문은유지한다. ambiguity기각횟수는상류관문미통과로미평가인경우와실제다중해를분리해기록한다.

질감은0프레임HOST_ERROR(하위render_profile API거부)였다. 생성기에base floor_light_v1을전달하고그뒤원래PR511 질감을입히도록수정했다. 프레임이생성되지않은이실행의6장검토는불가능함을명시한다. carry는60SIM초정상종료/들기성공/낙하0/통제된내려놓기1/목적지배치실패(sim_cap). 자기RGB6장직접확인. 평가TOP촬영0. carry첫30wall/SIM의기존필드가없어마지막후보에측정·원장JSON을추가했다.

기존42구간의마지막발행펄스를포함하도록경계를넓혀재계산했을때비율변화중앙-0.235%, 절대변화p90 0.583%/최대1.443%다. reloc9우회전14.5%초과의주원인은경계가아니다. 새좌우계수로기존15검증은10/15(이전8/15), 여전히5개범위밖이다. 새4방향통과를모든하중/장소/각도의성공으로확대하지않는다.
