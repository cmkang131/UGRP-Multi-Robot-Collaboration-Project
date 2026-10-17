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

## 실행 완료한 조건부 MC20

조정자 운영 정의는 coordinator-mc-directive.md에 보존했다. 실제 운영자가 준
구역 파일을 기다리는 대신, 기존 영상은 평가 전용 하네스가 GT를 상자 안 무작위
위치로 두는 합성 사전을 생성했다. 필터에는 상자/대략 방향 범위만 제공한다.
이 절은 위 직접 RGB --initial-prior 어댑터와 구분한 실제 실행 경로다.

고정 source9fa2aad39에서 아래4단계를 순서대로 실행했다(host=gcp5 또는 gcp3).

```sh
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python scripts/mapbuild10_mc.py \
  --stage prepare-own --host gcp5 --work /home/ugrp/ugrp-sim/runs/mapbuild10-mc20 \
  --trials 20 --workers 4
```

다음 prepare-priors → predict → score도 같은 work/host/trials/workers에
--calibration /home/ugrp/ugrp-sim/ops-reviews/mapbuild9/own-noise-command-r1-r2.json,
--requirements experiments/2026-10-17-mapbuild8/requirements.json,
--queue /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/mc20-queue.json,
--stack-check /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/mc20-stack.json을 전달했다.
사전 생성 RNG46820261017은 평가 단계에만 있고 입자 RNG2026101700+trial과 다르다.
기존 출력 폴더는 덮어쓰지 않는다. 재현할 때 새 work 경로를 사용한다.

prepare-own은 원래 자기 OFF 궤적/scan/servo에서만 입력을 만들고 RGB 해시를
검증한다. prepare-priors는 GT를 읽는 별도 평가 프로세스다. 그 결과 범위만 든
priors.json을 predict가 읽고, 정확한 상대 위치를 가진 prior-generation-eval-only는
읽지 않는다. 전체 예측을 봉인한 뒤 score가 GT로 채점한다. 평가용 범위를 GT에서
만들었다는 사실을 숨기지 않으며 실제 공개 시작 구역에서 새로 출발한 결과가 아니다.

coarse/global 각각20회다. R1–R3 각40=120조건, gcp3 28스트림 각40=1120조건이며
호스트를 합산한 정확도/성공률은 보고하지 않는다. 기존 OFF는 시작 SE2만 GT 정렬,
척도1인 상대 drift이고 새 AMCL은 전역 절대 오차다.

봉인 후 scripts/mapbuild10_mc_finalize.py(44a29092a)를 --host/--work와
--source /home/ugrp/ugrp-sim/src/mapbuild10-9fa2aad39로 실행했다. 상대 입력 경로는
그 동결 소스 기준으로 해석한다. 압축본을 읽을 때는 zstd -qdc 후 원래 SHA를
검증한다. final-integrity.json이 모든 input/prediction/GT/사전 생성 연결과
Mac에 회수한 요약의 SHA를 기록한다. 알고리즘/예측은 후처리에서 바꾸지 않는다.

초기 MC20 단계는 모든 조건의 OFF 개선 관문이 실패했으므로 당시 새 물리는0이다. 공개 시작 상자에서
실제 spawn을 균일 샘플링하는 장면 경로는 이 라운드에서 구현/실행하지 않았다.
현재 API는 runtime_qualified=false/adopted_pose=null을 유지한다.


## 공개 시작 상자 장경로 진단(조정자 별도 승인)

MC20의 OFF 미개선 관문은 유지한다. 원문 승인과 원인 표는 coordinator-mc-directive.md와 bias-review.md. long-route-config.json은물리 시작전에공개상자를정의하고실제시작은setup RNG에서균일샘플; 정확한값은setup-eval-only만저장한다. mapper는공개상자만받고입자RNG는별개다. 자기RGB/발행명령융합→StaticAMCL static likelihood→별도own-map 기록. DiagnosticCorrection은생산자격을부여하지않으며승인된장경로진단에서만수렴한제안의상대좌표를공유v145 heading/펄스/코스트정책에제공한다. 분포가풀리면LOCALIZATION_UNRESOLVED로멈춘다. 실제성공/접촉/평가자세는들어가지않는다.

실행원본 /home/ugrp/ugrp-sim/runs/mapbuild10-long-round1, 큐/명령/SHA/최신스택확인은 /home/ugrp/ugrp-sim/ops-reviews/mapbuild10/long-round1-v2. 원본f3a91cb85는실행전commit/push했고서버사본은git-shared.git에직접reference clone했다. 소스와큐는실행중수정하지않는다. 초기5f18d4938의52프레임은예전속도차단코드발견으로감독중단·제외, 교체본의속도는current_stack 최신record_only다. 1라운드중2녹화(1제외+1교체)이며추가실행은없다.

후처리는 scripts/mapbuild10_long_score.py --source <frozen-source> --input <unloaded-v2> --output <new-score-dir> --requirements <frozen requirements>. 자기입력/온라인제안봉인과RGB해시를먼저확인한뒤GT를연다. OFF에는초기SE2정렬한번만주며척도피팅하지않고AMCL은절대오차를채점한다. .5m구간표는보고용이고계산/행동관문이아니다. 실제3m와설계반전turn π에서기존방향요구오차를뺀회전량, 끝/최대오차·전체경로요구표를분리해낸다. 오프라인비교통과를ACT/LLM/임무물리성공으로보고하지않는다.


## 수정된 거리장/센서 어댑터

명시 `--amcl-profile nav2_rgb_field_v1`만 authored wall extent+기존max_occ_dist2m 지지영역과actual RGB range4m를사용한다. 기본profile/기존기록/허용free-pose배열은바꾸지않는다. σ/α/입자/수렴/요구관문불변. `field-run.py`는host별기존Python을선택하고sealed입력을hardlink로재사용한다(zstd는symlink를거부). gcp5의legacy/public-baseline/public-fixed는v2경로, gcp3legacy는v3경로다. 운영오류n0은operations별JSON에남긴다.

최종원본은각실행VM의runs/mapbuild10-*와ops-reviews/mapbuild10/field-7f2f1baae-v2(gcp5)/v3(gcp3), long-round1-v2에보존했다. 큰JSON은SHA검증후zstd로무손실보존했다. read_text를쓰는후처리재현전 `zstd -dk <file.json.zst>`로원래경로에복원하고raw-archive.json의원본SHA와대조한다. 원본은삭제된것이아니며같은bytes를압축보관했다. MC의raw()는압축본을직접읽는다. 원래실행소스f3/평가5d1/카메라진단c5/후속필터7f를구분한다.

operations/final-gcp5와final-gcp3는회수요약(각48/11파일), 자체SHA256SUMS와retrieval-manifest가원본/회수SHA를연결한다. 큰summary가회수용축약이면export_projection으로표시하고원본SHA도보존한다. final-local-retrieval.json은회수전체해시검증이다. 공개녹화baseline재생과온라인제안의차는XY4.44e-16m/yaw8.88e-16rad(381프레임,존재불일치0), 플롯추가전후frame-errors SHA동일이다.
