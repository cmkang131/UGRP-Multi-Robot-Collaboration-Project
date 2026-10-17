# mapbuild10 후보 API·재현

## 순수 입력 API

```python
StaticAMCL(static_map, own_noise_calibration, requirements,
    option='selfmap_map_correction_v1', profile='nav2_defaults_v1',
    initial_prior_option='start_zone_prior_v1', initial_prior=coarse_prior)
```

두 토글 기본은 off다. 새 프로필은 가산 likelihood_field·공식 σ=.2m와
입자500–2000·recovery alpha0/0을 사용한다. 원래4개 프로필 설정은 유지한다.
직접 Python API의 사전은 schema/zone_id/map_id/bounds_m/heading_center_rad/
heading_half_width_rad/source_kind/source_evidence만 허용한다.

운영 사전 JSON 형식(값은 운영자가 공급):

```text
{static_map_sha256: <원본 static-map.json SHA256>,
 prior: {schema: ugrp.coarse_start_zone.v1, zone_id: <운영 구역 이름>,
         map_id: <정적 지도 ID>, bounds_m: [xmin,xmax,ymin,ymax],
         heading_center_rad: <대략 방향>, heading_half_width_rad: <반폭>,
         source_kind: operator_coarse 또는 authored_static_zone,
         source_evidence: <운영자 진술/실제 정적 구역 출처>}}
```

이는 JSON 예시 값이 아닌 형식 설명이다. 실제 좌표를 넣은 사전은 아직 없다.
운영 상자는 각 변 최소.5m, 방향 반폭은30° 이상이며 정확한 점·빈 출처는 거부한다.
기존 정적 지도의 literal start_zones 항목은 더 작은 실제 구역을 허용한다.
평가 좌표/spawn·그 반올림 값은 출처로 사용할 수 없다.

## gcp5 R1–R3 (사전이 제공된 뒤)

고정 source checkout에서 실행하고 queue의 rejection_table 파일과
check_current_stack의 역사 재생 검사를 먼저 확인한다. SOURCE는 후보를 commit/push한
새 고정 SHA의 clone이며, clone은 해당 VM git-shared.git을 직접 reference한다.

```sh
/home/ugrp/ugrp-rl1b-act-env/bin/python scripts/mapbuild10_replay.py \
  --input /home/ugrp/ugrp-sim/runs/mapbuild8/recording-r3 \
  --saved /home/ugrp/ugrp-sim/runs/mapbuild8/executed-r3 \
  --calibration /home/ugrp/ugrp-sim/ops-reviews/mapbuild9/own-noise-command-r1-r2.json \
  --requirements experiments/2026-10-17-mapbuild8/requirements.json \
  --command-model experiments/2026-10-17-mapbuild8/calibration/own-command-calibration-r2.json \
  --queue /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/queue-r3.json \
  --stack-check /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/stack-r3.json \
  --initial-prior /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/start-zone-r3.json \
  --output /home/ugrp/ugrp-sim/runs/mapbuild10/r3-coarse-nav2-v1
```

이 명령은 **아직 실행하지 않았다**. queue/stack/실제 사전도 운영 입력 후 동결한다.
R1은 --scan-source runs/mapbuild8/replay-r1-v2/scans.json 절대경로를 명시한다.
R2/R3는 원본 scans.json을 쓴다. 예측을 봉인한 다음 별도 프로세스로
scripts/mapbuild9_evaluate.py의 --input/--prediction/--output/--requirements를 실행한다.
평가의 OFF는 같은 자기 LK+명령 융합에서 지도 보정만 끈 것이며 시작 SE2만 정렬,
척도1이다. AMCL은 정적 좌표계 절대 오차를 평가한다. 미수렴 평균은 채택하지 않는다.

## gcp3 별도418뷰

scripts/mapbuild10_sparse.py --stage predict/score는 mapbuild9_sparse의 기존
입력/영상 추출/예측 봉인/별도 평가를 재사용한다. --initial-prior는
{streams: {"<world>:<rid>": <위 사전 JSON>}} 형식이며28개 스트림 각각 필요하다.
--input은 /home/ugrp/ugrp-sim/runs/warp8/selfmap-open-r1,
--owner는 /home/ugrp/ugrp-sim/src/warp8f-selfmap-0ace43f25다.
미제공 사전으로 새 후보를 돌린 결과는 없다.

실행한 감사의 argv는 operations/gcp3-measurement-summary.json에 있고,
전체 표는 gcp3 /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/measurement-418/frame-table.json.zst다.
측정 감사는 필터 재생이나 실제 release/운반 성공이 아니다.

## 봉인한 진단

- 0dc8523e6: scripts/mapbuild10_measurement_audit.py 최초 측정 감사.
- 1ea902107: scripts/mapbuild10_support_audit.py, 기존 첫6회 입자 snapshot 재가중치 진단.
- 0df021e73: 자기 FK 후보·동일24개 비물리 시험·1044프레임 저장 카메라 기구학 감사.
- eae94efe1: gcp3 418뷰 측정 감사·시작 구역 인벤토리·sparse 입력 어댑터.

카메라 감사는 원래 renderer cwd drivecheck-renderer-5974a181과 .venv-warp를
사용해야 한다. mj_forward만 하고 적분·렌더하지 않는다. 진단 입력/예측의
해시 검증은 추정기 예측을 바꾸지 않는다. 대형 표는 zstd -qdc로 해제하며
operations/audit-integrity.json 및 gcp3-integrity.json의 전체 SHA를 확인한다.
