# 기존 상수의 근거 점검

새 상수·문턱 변경 없음. 아래는 조사 당시 코드값이며 정당성을 승인했다는 뜻이 아니다.

|위치·값|근거 상태|역할과 미확인 부분|
|---|---|---|
|selfmap5_registration SIGMA_SCALE=6, floor .02m/.5°|**원본 보정 근거 없음**: 주석 자체가 fitted calibration 아님|residual search covariance ×36. reloc12 raw_cov_gate를 켜면 pose 수용 covariance는 별도 raw P. R3 PF resolved 0의 직접 원인으로 볼 수 없음.|
|own_map_amcl_vendor motion converged_distance=.5m|Nav2 pf.c dist_threshold 관례; 우리 적합성 미확인|모든 입자 기준 xy convergence. 우리 resolved는 이것과 full posterior yaw σ≤5°를 AND.|
|augmented belief_report yaw σ≤5°|기존 과제 목표, 통계적 보정 아님|전역 분포 조건. R3 yaw σ 최솟값 6.719°/9.114°로 모든 프레임 탈락.|
|field sigma_hit=.2m, z_hit=.5/z_rand=.5, max_occ_dist=2m, max_beams=60|Nav2 공개 기본값; RGB 원본 잔차 근거 없음|레이저 likelihood field를 RGB ground endpoint에 사용.|
|StaticRegistration raw xy σ≤.15m, yaw σ≤5°, cluster mass≥.9|기존 정책값, 원본 coverage calibration 미확인|R3 두 시드의 raw xy σ 최소 .1474/.8389m. 값만 풀어 해결하지 않는다.|
|MultiFrameEvidence hue12, angle 3×sqrt(Paa+(5°/3)²), NIS≤9, line noise .05/3m|기존 구현/과제 잔차; 센서 분포 적합성 미확인|NIS9는 3σ 반지름이지 2/3자유도 99.73% 주장이 아님. inflate P로 대응 허용 범위도 커진다.|
|independent axes eigenvalue≥.5, 3 distinct views, view bin10°, anchor .1m/5°|기존 기하·정책, 원본 독립성·분포 보정 미확인|parallel line 모호성 억제 의도. 서로 다른 view를 독립 표본으로 세지 않는다.|
|PF vs unique geometry .15m/10°|기존 일관성 정책, 분포 근거 미확인|unique 자체와 agreement를 따로 센다.|
|robust_segment ≥6, support≥.6, residual .025m, length≥.12m, range<4m|기존 floor/SE2 정책; 분포 적합성 미확인|이 실험에서는 변경하지 않음.|
|reloc15 update .05m/2.5°|10cm/5° 과제 목표의 절반이라는 관측기회 가설|논문 최적값·실측 정확도 보증 아님.|
|selfmap cap60·carry150 SIM초, search40000 nodes|기존 제한된 DEV 예산|수용 정확도 상수와 구분. cap_end를 실패·완주와 분리.|

관측 노이즈를 바꿀 경우 원본 픽셀/metric 잔차 분포·시드 분리와 출처를 코드 주석에도 남겨야 한다.
