# 수렴 하락의 직접 관문

같은 R3 MC20 사전·입자 RNG에서 두 방식 각각7,780프레임을 재생했다. 저장된 두 과거 예측과 candidate/ready 불일치 **0**. 새 필터·상수·문턱 변경0. 표는 각880번 측정 갱신 전체에서 얻은 중앙값이며 끝점 통계가 아니다.

|방식|수렴 시드/20|XY P95 mm|yaw P95 °|방향결합 P95 °|사전 ESS/N|최대가중치|XY/방향결합/ESS 거부 갱신 수(중복)|
|---|---:|---:|---:|---:|---:|---:|---:|
|수정 전 nav2_defaults_v1|20|172.21|12.583|27.362|440.35/501|.003052|285/702/8|
|수정 후 nav2_rgb_field_v1|5|184.37|14.260|30.732|480.93/501|.002390|350/870/5|

직접 사유는 방향결합 분포 예산(21.423°) 초과다: ready 갱신178→10. 수정 후 가중치가 더 평평해지고(최대가중치↓·엔트로피6.138→6.193) XY/yaw 분포가 넓어졌다. ESS 부족은8→5로 감소했으므로 ESS 붕괴로 인한 수렴 하락이 아니다. 지도 밖 잔차와 z_rand 센서 범위를 동시에 고친 결합 후보이므로 둘의 독립 기여를 증명한 결과는 아니다. 인위적인 경계 페널티 제거가 분포를 덜 뾰족하게 했다는 해석은 이 수치에 근거한 추론이다. 문턱을 완화하지 않는다.

원본: gcp5 `/home/ugrp/ugrp-sim/ops-reviews/mapbuild11/paired-r3-v2/paired-frames.json`. 입력은 `/home/ugrp/ugrp-sim/runs/mapbuild10-mc20/{own-streams.json.zst,priors.json}`. 비교 원본은 `runs/mapbuild10-mc20/predictions` 및 `runs/mapbuild10-rgb-field-legacy-v2/predictions`다. 재현: source cfdcd8845에서 `PYTHONPATH=. /home/ugrp/ugrp-rl1b-act-env/bin/python scripts/mapbuild11_compare.py --output <새 폴더>`.

[요약](operations/paired-r3/summary.json), [순차 funnel](operations/paired-r3/rejection_table.json). 첫 계측 시 v3 경로를 지정한 운영 오류1건은 원본이 실제 v2임을 확인 후 수정했다. 해당 시도는 예측을 완료하지 못했고 물리/렌더0이며 [실패](operations/audit-exit.json)와 [교체 완료](operations/audit-exit-v2.json)를 보존했다.

## 실제로 수렴이 사라진 같은168갱신

더 직접적인 동일 시점 비교: 수정 전 수렴·수정 후 미수렴인168갱신은 **모두 방향결합 관문 초과**, 이 중 XY 초과4·ESS 초과0이다(중복 집계). 이168개의 XY P95 중앙은109.49→154.56mm, yaw P95는9.108→12.760°, 방향결합17.659→25.423°, ESS488.45→497.20/501이다. 공분산 대각 중앙도 x .002129→.004358m², y .001565→.003675m², yaw .006266→.012794rad²로 커졌다. 각 조건은 동일 입자 RNG로 시작했지만, 측정 뒤 재표본화 분포가 달라진 후의 입자 자체가 동일하다는 뜻은 아니다. [조건부 비교](operations/paired-r3/matched-loss-summary.json).
