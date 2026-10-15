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
