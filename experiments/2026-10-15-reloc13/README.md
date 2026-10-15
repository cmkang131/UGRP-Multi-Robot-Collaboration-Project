# reloc13 — 전달 경로 수정, 운용 승격 NOT_READY

확대 공분산의 실행 유입과 명령/ORB 좌표계 혼용을 기본 off 토글로 수정했다. **최종 R3는 첫 등록4/4·첫 오등록0/4지만, 등록 후 제어 자세 오류282/626프레임(기존10cm/5°), 물리 배송0/2**다. 후속 selfmap8·carry22 큐는 모두 **BLOCKED·미제출**이다. 새 관문/학습/추가 탐색은 제출하지 않았다.

시작 SHA `1db2c4a18ad3698656c29091af0afd558cbc5d4e`, 최종 물리 소스 `fc11a303b5e5b6afb4d2b1a858f3da50dd609d96`. [요약](summary.json), [관문표](rejection-table.md), [원본·해시·재현 명령 JSON](rejection-table.json), [실제 제출 명령](gcp-commands.json).

## 수정 전 원본과 HOST_ERROR

GCP 원본892프레임의 누적 관문은 등록446 → 유한 실행 자세446(신선한 정적 보정 수용65) → 지도 삽입0 → 주행0이다. 등록 후 삽입446건 전부 pose_uncertain이었다. R7 모호성 검사154·유일121·PF일치75프레임, 첫 등록4회·오등록0회다. 기존 기록과 겹치는 원본 해시10/10 일치([검증](baseline-integrity.json)).

147개 오류는 xy만37·yaw만86·둘 다24다. 오류 프레임의 xy 중앙9.31cm·p95 10.67cm·최대10.89cm, yaw 중앙8.73°·p95 57.53°·최대57.73°다. ORB 전역 재등록2건과 이후 전파, 정적 PF 오차, 명령 전파를 소스별로 나눴다. 이 분류는 기록된 발생 경로이며 모든 프레임의 독립적인 물리 원인을 확정했다는 뜻은 아니다([147개 상세](baseline-funnel.json)).

HOST_ERROR4건은 모두 **코드의 복구 시도 상한 소진**이다. 원본 이벤트에서 attempt1→2→3, 복구 시작 뒤20.8–24초에 종료됐다. 기존 RECOVERY_ATTEMPTS=2를 넘은 것이며 VM 장애나80초 deadline이 아니다. 원본 HOST_ERROR 라벨은 보존했다([원본 이벤트](baseline-host-errors.json)).

## 변경과 3라운드

- `reloc13_execution_cov_v1`: 실행 자세에 원 PF 공분산을 반환한다. 선 NIS·RANSAC 탐색의 확대 공분산은 유지한다. 수용된 절대 정적 보정에는 bootstrap의 이전 명령 공분산을 다시 더하지 않는다. ORB/명령 유래 보정의 누적 모델은 유지한다.
- `reloc13_execution_frame_v1`: R7 증거는 명령 오도메트리에서 검사하고, 등록 시 world_pose와 동시 실행 예측 자세로 ORB 실행 프레임의 변환을 따로 고정한다. 최초 local 보정의 innovation은0이며 correction_gate를 우회하지 않는다. 실제 전달 수용 전에는 삽입을 막는다. R1에서 확인한11–13° 좌표계 차이가 근거다.
- `reloc13_live_r7_v1`: 새 PF 갱신에서 기존 R7 기하·유일성·PF일치·3뷰 확인을 잃으면 registered_r7_unconfirmed로 삽입·주행을 막고 기존 재관측으로 돌아간다. stale 프레임은 확인을 늘리거나 무효화하지 않는다. R2의 최대xy오차76.2cm와 작은σ의 동시 발생이 근거다. 새 수치 상수 없음.
- 세 토글 모두 기본off다. σ가 정확도를 분류한다는 주장은 하지 않는다. 감사의 geo_n/geo_eig1 AUC 최대.69와 기존 인라이어 수만으로 새 정확도 한계값을 정하지 않았다. 원본의 R7·ORB matches/inliers와 운반 뷰 residual/특징 수/정보 고유값을 남겼다.

|후보|소스|물리 실행|첫 등록/첫 오등록|등록→삽입→주행 프레임|기존10cm/5° 오류|종료|
|---|---|---:|---|---|---|---|
|R1 질감, 공분산|aa1f4661|2|2/0|149→146→52|149/149|좌표계 결함 확인 후 감독 중지2|
|R1 smooth 기준|aa1f4661|1|0/0|0→0→0|해당 없음|같은 결함으로 감독 중지1|
|R2 질감, 실행 프레임|6abd9527|4|4/0|1262→1233→360|644/1262|cap_end3·복구소진1|
|R3 질감, live R7|fc11a303|4|4/0|626→302→36|282/626|cap_end2·복구소진2|

R1에서 결함을 확인하자 소유 PID3개에 SIGINT를 보냈다([영수증](stop-r1-selfmap.json)). R2 후반 drift는 원본 재집계 때 확인했고 해당4회는 이미 종료돼 있었다. R3의 삽입 오류115/302·주행 자세 오류28/36도 남았다. R7이 재확인돼도 정확한 자세를 보증하지 못한다. 등록 후 R7 미확인 삽입 거부316프레임을 분리했다. **차단 증가를 정확도나 운용 성공으로 해석하지 않는다.** 궤적·상한·후보가 달라 세 라운드와 reloc12를 합산하지 않는다. 감사 기준15cm/5°,30cm/10°는 각 run JSON의 alternate_tolerances에 별도 보존했다.

첫30 SIM초 wall/SIM 중앙값: R1 texture4.195, R2 4.335, R3 4.410, carry2회2.456. 3.5 초과 경고이며6.0 미만이다. smooth는 감독 중지로 첫30초 측정 미완료다. 모두 gcp1/n4-highcpu-64. 물리 라운드는5/4/4회로 총13회, 질감12·smooth1이다. 운반 명령의 불필요한 --execute 때문에 파서에서 끝난2회는 CLI_ERROR·물리0으로 별도 기록했다. 로컬 dirty-source precheck1건도 VM 물리 실행으로 세지 않았다.

## 운반 예산과 물리 결과

기본off `carry_pose_budget_recal_v1`은 회전 계수.29와41° 예산 트리거를 적용한다. .29는 감사5894틱 구간 최대 포락이고,41°는 GCP의 고유8시드7620틱·부분 epoch를 반영한 고정 궤적 재생에서 실제yaw≥20°인578틱의 최소 새예산41.3635°를 내림한 값이다([재생](budget-fit.json), [설정](../../configs/calibration/reloc13_carry_budget_v1.json)). 원래 공식의60°를 .29와 그대로 혼합하지 않았다. `carry_pose_budget_xy_reserve0_v1`은 .25m/m 포락을 유지하고 이중 여유 .40→.50만 제거한다. 실제 과제 허용 오차를 키운 값이 아니다.

그러나 **새 물리에서는 재보정 검증에 실패했다.** 93266의 실제yaw≥20°인835틱 중708틱만 트리거(84.8%)했고, 재탐색 중127틱을 놓쳤다. 트리거가 없는 구간의 최대 실제yaw오차52.6°다. 같은 자료 재생578/578을 폐루프 일반화로 취급할 수 없다. holdout93315에는 실제yaw≥20°가0틱이어서 고오차 재현율을 검증하지 못했다. 토글은 기본off를 유지하고 큐 차단 사유에 이를 넣었다.

|seed|접근·정렬|평가 들기|carry_to_zone|zone_place_view|놓기/배송|종료|
|---|---:|---:|---:|---:|---:|---|
|93266 실패 재현|1|1|0|0|0|300 SIM초 cap_end, carry_reobserve|
|93315 새 시드|1|1|1|0|0|95.2초 carry_recovery_setdown_envelope_blocked|

93266의265.4초 carry_reacquire→carry_reobserve 전환은 실제로 확인했다. 그 중단 뒤 동일 탐색 객체로 재개·완료하는 것은 cap_end 때문에 물리 검증이 남으며 단위 회귀만 통과했다. 93315는 운반→내려놓기/재관측→재파지→운반 재진입까지 갔다. 마지막 후진 여유는 자기 RGB 장애물 원장의 **own_rgb:heavy_crate:4와 −0.07273m**였고 기존 segment_free의 margin-escape 규칙으로 재현했다([재집계](carry-blockers.json)). 이는 인지된 여유 중첩이며 실제 물체 충돌을 확정한 값은 아니다.

재관측20뷰 중4수용·16거부. 누적 관문은20→residual20→특징군17→rank15→inlier9→innovation8→gain8→최종수용4다. 수용 직후 yaw오차는0.086–2.91°, xy는0.008–0.226m여서 수용4/4를 정확도 성공으로 세지 않는다. residual·그룹·rank·인라이어·NIS·정보 고유값·허용 관측 prior/candidate를 보존했다([원장](round1-carry.json)).

## 검증·대기열·보존

관련 오프라인82개 통과, 제외0, Mac 물리/렌더0. 무작위가 아닌 실제 좌표계 차이 재현, 공분산 용도 분리, 정적 보정 거부, live R7 상실/stale 처리, 운반 예산, 같은 기하의 막힘 원장, rejection_table 필수·대기열 차단을 확인했다([로그](pytest.txt), [검증](validation.json)).

후속 [selfmap8](queues/20261015-reloc13-selfmap-fc11a303.json)·[carry22](queues/20261015-reloc13-carry-texture-fc11a303.json)는 전체 source_sha40자리·실패 시드 우선·max_parallel16/전체40·실재하는 rejection_table 절대경로와 해시를 갖는다. 모두 BLOCKED/승인·실행·제출false다. 같은 파일을 기본 프로젝트 outputs/e2e18-admin/vm3-queue에 저장했다. 고정 소스는 작업 디렉터리 outputs/reloc13/source-fc11a303이며, carry 물리 소스aa1f4661와 차이는 실패 문맥 기록뿐임을 AST/파일 해시로 분리 검증했다([범위](carry-runtime-equivalence.json)). 새 물리 재검증을 뜻하지 않는다.

원본 manifest15/15(물리13+CLI2) 검증, 몽타주13개·선택 자기RGB78장 직접 검토 및 다운로드 해시 확인([원본](integrity.json), [회수](local-review-verification.json)). 자기 입력 감사 invisible_measurements/held_world_reads 모두0/0, 모델·학습0, weld OFF다. TOP 제어는 사용하지 않았다. Mac에는 요약·몽타주·실패 실행 선택 프레임만 회수했다. 전체 raw는 GCP 영속 디스크에 있고 별도 전체 백업 완료는 아니다.

자기 PID·임대·예약0으로 종료 확인, 다른 작업은 유지했다([상태](final-state.json)). 전체 동시 입장 상한 추정 최대20/40, VM24h STOP·유휴20분·budget-stop은 변경하지 않았다([호스트](host-safety.json)). 남은 문제는 R7 이후 자세 정확도, carry 재탐색 예산 누락·복구 수렴, 목적지 관측·놓기 미도달이다. 승인된3라운드를 모두 사용했으므로 추가 실행은 하지 않는다.

GCP 저장 원본 재현은 고정 source cwd에서 PYTHONPATH=.로 scripts/analyze_reloc13.py 및 scripts/analyze_reloc13_carry.py를 /tmp에 복사해 관문표의 명령을 실행한다. 회전 예산/막힘/영상/원본 검증 재현 도구는 [tools](tools/)에 보존했다. 평가 정답은 이 오프라인 채점에만 쓴다.
