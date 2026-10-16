# mapbuild5 — 벽 색 경계 가상 스캔 + 기존 GMapping식 RBPF

**rbpf-ack / ownership-ack / nativecontact-ack. 구현·동일 녹화 비교 완료, 전체 NOT_READY / PR DRAFT다.** 같은 `codex/mapbuild1`, PR #556에 잇는다. 사용자 2026-10-16 원문: “mapbuild4에 벽 색 경계 가상 스캔 + GMapping식 입자 필터를 넣고, MASt3R-SLAM은 같은 녹화 영상으로 비교만 해줘.” 원본·분석은 gcp5(`ugrp-act-l4-gcp5`, `ugrp-sim-e-1016`, `changmin5781@gmail.com`)만 사용한다. 다른 작업자의 코드·결과와 합산하지 않는다.

현재 상태: native v1 MJWarp 녹화 **r2 40 SIM초·401 자기 프레임(10Hz)**와 동일 영상의 LK/RBPF 비교를 완료했다. XY ATE RMSE는 **24.164→20.226mm**지만 종료 오차는 **27.357→35.816mm**로 악화됐다. 같은 벽 복귀 보정은 11회 중 개선5/악화6이다. 넓은 자기 지도·도착·운반·HIGH 인수는 미완료이며 기본 채택하지 않는다. r1/noslip10은 조정자 `SUPERVISOR_STOP`으로 중단한 미완료·결함 아님·합산 제외 자료다. 과거 41프레임 배관 재생과 빈 RGB 검사는 이번 성능 분모에 넣지 않는다.

## 수정 전 거부 원인

[사전 분포표](prior-rejection-table.json): egomap24의 t13.7 이후 거부48회는 search_boundary37, low_overlap10, high_residual1이다. yaw가 국소 ±8° 탐색창을 벗어난 문제와 거부 뒤 과도한 재표본화가 주요 과거 제한이었다. egomap26의 유효 스캔 삽입은7→55로 늘었으나 거부 재표본19회·최종 조상1개가 남았다. egomap27은 삽입+선택적 재표본+Manhattan 결합으로 거부 재표본0을 확인했으나 wide의525/891시각이2σ 밖이었다. 종료 한 점의 개선을 경로 전체 확신도로 해석하지 않는다. 과거 tape/장면/호스트 수치는 이번 결과와 합산하지 않는다.

mapbuild4의 횡60ms 되밀림은 CPU·MJWarp 양쪽에서 남아3라운드 종료했다. 접촉 원인을 더 파거나76배 역이득을 넣지 않는다. 새 녹화는 측정된 전진100ms와 좌/우400ms만 쓴다. warm400ms 약44mm와 cold/warm 전체 응답을 명령 예측 평균·문맥 공분산으로 쓴다. r2는 mapbuild4 native-r3의 cold/warm 원본만 사용한다(동결 JSON SHA `c8400547e9c50e4e6e76291c2a1c5048895ced83c39d43c1c2ac293d1f550b99`). 이 분산은 독립 반복 측정의 신뢰구간이 아니다. 모델 파일에는 원본 NPZ/metrics/summary 경로와 SHA를 보존한다.

## 구현과 비교 경계

- 기본 off `mapbuild_rbpf_v1`: [위치 추정 어댑터](../../harness/mapbuild_rbpf.py). 자기 JPEG를 고정 K/D로 보정하고, 기존 `ColourBoundaryState` v2의 벽–바닥 경계96열을 서보 명령 FK의 바닥 평면으로 투영한다. 거리·방위·이유를 열마다 보존한다. 자기 차체 투영/동료 RGB 열은 제외하고, 미관측은 `range_m=null`인 unknown으로 둔다. 연속해서 관측한 인접 열만 잇고 가림 사이를 채우지 않는다.
- `SelfWallMemory(... own_map_rbpf_v1)` / `self_map_rbpf.py`의 개선 제안·정확한 중요도 비율·입자별 log-odds 격자를 그대로 쓴다. `rbpf_rejection.py`와 `rbpf_composition.py`의 결합은 거부 스캔에 CSM 가중치/재표본을 적용하지 않고 sampled motion 위치에 삽입한다. Manhattan은 첫 자기 관측에서 얻은 잠재 축만 쓴다. 정답 축/정적 지도는 없다.
- 이동 입력은 측정된 LK 바닥 증분·전체3×3 공분산, 그 외에는 고정된 과거 MJWarp 명령 응답·공분산이다. 공분산은 해당 구간에 한 번만 회전·전파한다. 새 녹화 정답으로 평균/분산/상수를 맞추지 않는다.
- ROS의1m/.5rad 이동 관문 설치 구조를 재사용하되 이번 짧은 왕복의 스캔 스케줄은 기존 CSM의1 SIM초다. 실제 wall초를 관문으로 쓰지 않는다. `pf_sensor_proposal.py`의 추가 혼합 제안은 **off**다. 기존 Grisetti Gaussian 제안을 유지하여 추가 가정의 효과를 섞지 않는다.
- [녹화](../../scripts/mapbuild5_capture.py)는 기존 mapbuild4 clean-start/장면/휠 relay/MJWarp graph를 재사용한다.18회 전진100ms 뒤 좌10회/우10회400ms를 각1초 주기로 발행,40 SIM초에 `cap_end`한다. 마지막10 SIM초를 포함한 전체10Hz 자기 카메라·r2·평가용 개요를 남긴다. 프레임 시점을 독립 렌더 세계16개로 묶는 최적화는 **완료된 물리 궤적의 렌더만** 바꾼다. 물리 리셋/GT 보정 주행이 아니다. 장면/공용 backend 수정0이다. 접촉은 warpfit `df5a1f86a`의 byte 동일 모듈(SHA `a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`)로 `warp_native_contact_v1`을 적용한다. noslip0·elliptic·implicitfast·impratio5·Newton/LS80/50, 설치 MJWarp tolerance floor1e-6을 유지한다.
- [재생](../../scripts/mapbuild5_replay.py)은 같은 RGB/명령으로 LK만과 RBPF를 비교한다. 궤적·스캔·지도·입력 SHA를 먼저 봉인한 뒤 evaluator가 ATE·coverage·잘못된 free·벽 정확도·복귀 구간 보정 전/후 오차를 읽는다. 정적 지도와 실제 reset/end 화물 충돌 상자를 따로 채점한다. 최근접 벽 이름/잔차로 같은 벽 재관측을 별도 확인한다. 위치/지도 추정 어댑터와 frontier 주행 인수는 별개이며, 새 frontier/운반/도착 성공을 주장하지 않는다.

## 동결 상수·출처

|항목|값·출처|
|---|---|
|입자/seed|30 /20261006: 기존 `RBPFOptions`, ROS 기본 particles30. 논문 Fig.5도30입자 예시이나 우리 과제의 충분성 보장은 아니다.|
|재표본|기존 엄격한 Neff<N/2: Grisetti2007 Eq.20/§III-D, OpenSLAM 구현. 거부 CSM에서 생략하는 정책은 사용자 요구 결합이며 원본 GMapping과 구분한다.|
|정합/σ|기존 `CSMOptions`/`self_map_prob.sensor_sigma`: ±.5m/±8°, coarse.1m/2°와fine 최대.05m/1°, calibration floor.08m, 격자.05m 양자화/12, pixelσ2·fy622.165488…·height lower bound.15m. overlap.6/거리.2m/residual.15m/min_points6/유효점12 등 모두 기존 동결값, 새 GT fitting0. 원래 [egomap §17–19](../2026-10-05-ego-wall-map-probe/README.md)의 한계도 승계한다.|
|지도|기존 OdomGrid10cm, hit log(.7/.3)·miss log(.4/.6)·기존 clamp. 입자 지도끼리 cells를 공유하지 않는다.|
|입력 범위|기존4m·positive depth, 기존 색 보정 SHA `a37cf965…e24f`, 자기 명령 FK/K/D.|
|동작 잡음|OpenSLAM motionmodel.cpp25–35/ROS 기본 srr.1,srt.2,str.1,stt.2,sxy.03 + 과거 cold/warm endpoint 문맥 공분산. 상관된 문맥 오차를 독립 반복 표준편차로 해석하지 않는다.|
|계산량|30입자·96열·유한 coarse/fine 후보·1 SIM초 스케줄. 실제 후보/색 경계 검사 수를 funnel에 쓴다. 호스트 watchdog과 행동 관문을 구분한다.|

시작 좌표0은 상대 좌표계의 gauge다. 기존 초기.1m world 위치 floor를 새 가상의 시작 위치 오차로 샘플링하지 않는다. 이후 측정/명령 공분산은 그대로 누적한다. LK의 공분산도 바닥 평면/카메라 고정 가정의 전체 오차를 보장하지 않는다.

직접 열람한 원문: [Grisetti et al. 2007](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa13/optreadings/GrisettiStachnissBurgard_gMapping_T-RO2006.pdf), [고정 ROS 기본값](https://github.com/ros-perception/slam_gmapping/blob/eec86068ceb92ebc433b435fe482db14c562f268/gmapping/src/slam_gmapping.cpp). 기존 구현/거부 정책의 상세 원문 대조는 egomap24/26/27 기록에 있다. 논문의 lidar 결과를 색 경계 센서 성능으로 승계하지 않는다.

## 공유·검증·운영

연습 원본은 `/home/ugrp/ugrp-sim/shares/mapbuild3-practice/manifest.json`, SHA `6b01b075aa8786f821a6d63e17268b486ec5c422bc13a4745fd07a98c7d12e0c`이다.89파일 재검증, 자기82프레임이며 HIGH는 미자격이다. mast3rcmp의 ops-alert ACK(13:52:34 UTC)는 gcp4로 RGB82/82 SHA 일치·전송 완료를 확인했다. 본 녹화와 평가 자료는 아래 봉인·ACK 절차로 공유 완료했다.

[시도 원장](attempts.json), [비물리 검증](validation.json), [운영 기록](operations/). 과거 연습 입력을 위한 상대 자산 cwd·보정 closure·RGB 경로 가드 오류는 각각 보존했다. strict SHA/path guard를 약화하지 않았다. 겹치는 두 테스트 묶음36/20 passed를56개 독립 테스트로 합산하지 않는다.

gcp5 실행상한/자체 wall상한 추가0, idle20·budget-stop ACTIVE 확인. gcp2CPU 시작0, 모델/키 전송0·Mac GUI0·Drive0. 최종 프로세스/타 lease/공유 전송 확인과 직접 정지를 마쳤다(아래 종료 영수증). 실제 청구 비용은 별도 미측정이다.

## mapbuild5b native 재개

실행 상한 없음은 wall 제한을 뜻한다. 40 SIM초는 사전에 고정한 유한 왕복 자극의 완료 시각이며 `cap_end`로 기록한다. idle20/budget-stop은 유지한다. 부분 vision closure의 지도/registry 누락은 물리 시작 전 HOST_ERROR2건으로 보존했고, 기존 full renderer와 vision supplement 공통 파일의 SHA 차이0을 확인한 완전 closure로 바꿨다. 장면/원본 소스 파일 수정0이다.

녹화에는 고정 자세 선언에서만 계산한 `fixed-floor-calibration.json`(명목 camera_height_m·floor_normal_camera·차체↔카메라 변환·출처/geometry SHA)을 포함한다. 동적 명령·측정 관절·정답으로 보정하지 않는다.

## mapbuild5c 완료 결과 — 동일 영상, native v1만

물리 소스 `4269ece0550b97ab6e3403d24cee50389e9664ee`, 저장된 물리/RGB의 메타데이터 복구 `f83a57de1e5b996cd6f9d07008230f942bfaaa7e`, 추정도 `f83a57de1`이다. 인수 때 이미 추정·1차 채점이 끝나 있었으므로 **새 물리·렌더·추정 재실행0**이다. 복구는 저장401프레임의 완료 기록만 만들었으며 실행을 소급해 깨끗한 무오류 실행으로 바꾸지 않는다. 원래 writer의400ms v122 미지원·monitor 종료와 후속 evaluator의 registry 충돌도 [원장](attempts.json)에 보존했다.

측정 이동 길이는1.133579m, 횡 왕복은 출발19초→29초 **0.453339m**, 29초→39초 **0.441952m**, 복귀점 간격15.533mm다. 이전4초 진단보다 긴 동일 벽 왕복이지 넓은 지도 전체를 돈 결과는 아니다.

|평가(차체 시작 좌표계,401프레임)|LK만|벽 가상 스캔+RBPF|
|---|---:|---:|
|XY ATE RMSE / p95 mm|24.164 /42.051|20.226 /33.320|
|yaw ATE RMSE °|3.124|2.434|
|종료 XY 오차 mm|27.357|35.816|
|coverage /전체2,990셀|49(1.6388%)|49(1.6388%)|
|잘못된 free 셀|2|1|
|점유 TP/FP(지도 안)|8/0|9/0|
|지도 밖 예측 셀|4|6|
|벽 예측 표본 수 /벽까지p95|12 /100mm|15 /100mm|
|unknown 셀|2,941|2,941|

[전체 지표](results/summary.json), [reset/end 화물 포함 별도 채점](results/cargo-map-scores.json). 화물 collision box의 격자 표본11개는 양쪽0예측/11·unobserved다. 물체 인스턴스 검출률이나 동적 장애물 안전성을 뜻하지 않는다. 정적 지도 평가의 TP/FP만으로 전체 지도 정확도100%라고 부르지 않는다.

LK 측정390/400구간, 나머지10구간은 과거 native 명령 응답·공분산을 썼다(부트스트랩1프레임 별도). 가상 스캔401/401·38,496/38,496열이 벽–바닥 접점으로 반환됐다. 이 녹화에는 실제 차체/동료 가림 열이나 미관측 방위가 없어 가림 강건성의 새 인수는 아니다. 미관측을 최대거리로 바꾸지 않는 구현·기존 빈 RGB 배관 검사는 별개다.

순차 관문401→가시401→정착398→SIM스케줄40→삽입40(bootstrap1+정합39)이다. 스케줄 제외358·정착 제외3, 선택 입자/전체 입자 정합 거부0/0이다. 입자30×정합39=1,170개의 개선 제안, 후보검사1,675,440·색 경계 검사1,828,560이다. 재표본22/39회 모두 **Neff<15**를 확인했다([진단](results/diagnostics.json)). 거부가 없었다는 것이 정답 보정 성공을 뜻하지 않는다. [순차 funnel/거부표](rejection_table.json), [원격 재생 원표](results/replay-funnel.json), [다음 큐 ready=false](next-queue.json).

왕복에서 최근접 평가 벽은 양쪽 모두 `wall_west`다. 29.3–39.3초 보정11회 중 XY 개선5·악화6, 보정 직전/직후 평균26.420→25.661mm다. 31.3초는18.221→29.288mm, 33.3초는30.830→13.672mm, 38.3초는27.560→34.167mm다. 끝 오차와 복귀 일관성까지 개선했다고 판정하지 않는다. 벽 이름은 봉인 후 평가에서만 붙였다([재관측 요약](results/return-summary.json)).

## 봉인 후 평가·공유·영상

평가 소스 `a6a10a16aed40f9191e77bb8271741ecf922a600`은 [새 평가 프로세스](../../scripts/mapbuild5_evaluate.py)에서 frozen renderer를 먼저 import하고 녹화 당시 renderer 절대경로와 warpfit 원본 변환을 재사용한다. 동일 bytes를 다른 경로로 복사해도 XML의 asset 절대경로가 바뀌므로 이를 느슨하게 허용하지 않았다. c1은 native 변환 누락, c2는 asset 경로 차이로 XML 검사가 거부했고, 원 renderer 진단 뒤 c3가 **원 XML SHA `dc71d38961bb95dcd6841124889eecc98ec78bddd0d41f6b3bf4a89b6cb3f74d`와 완전 일치**했다. 판정·잡음·seed·입자 수 재튜닝0이며 기존 예측6파일 해시는 모두 유지됐다. 후속 실행기에도 프로세스 분리를 연결했다. [완료 영수증](results/completion.json), [XML 진단](operations/xml-source-diagnostic.json).

실제 카메라 중심/회전은 저장 qpos+같은 XML의 CPU `mj_forward`401회만 사용했다. **CPU 적분0·제어 전달0**, 추정용 고정 FK와 평가용 실제 자세를 구분했다. LK/RBPF 카메라 중심 추정은 고정 body–camera lever arm만 썼으며 roll/pitch·sag를 새 GT로 보정하지 않았다. MASt3R 자체 채점·결과는 별도 작업자 소유다.

- 원 녹화 manifest: `/home/ugrp/ugrp-sim/runs/mapbuild5/recording-r2/manifest.json`, SHA `de9addf5a7c268db99b0b8c7198e435a5adf90713bda7a718b4e6a7aec34e7d5` 불변.
- mast3rcmp2의 추정·척도 봉인:14:44:08.636758 UTC, seal SHA `3f34f8784e444498b31139720e07b26ca947e10d25ce53cc4cb8ff788c00aa28`.
- 봉인 확인 뒤 공개한 확장 manifest: `/home/ugrp/ugrp-sim/runs/mapbuild5/evaluation-c3/manifest-evaluation-release.json`, SHA `8ff6dbaf090a555b9ed52e1a6d251567b010df79913021fc60c0ade66a6fd458`. 실제 카메라401/고정 FK 카메라 추정/LK·RBPF 궤적·원 prediction seal을 포함한다([공유 영수증](sharing-release.json)).
- RGB401/401+고정 보정의 전송 ACK14:40:22.572157 UTC, 평가4파일 SHA 일치 ACK14:48:40.267631 UTC를 ops-alert에서 확인했다. 원본1,217파일·확장 공유416파일·봉인 예측6파일 해시 불일치0([무결성](results/integrity-final.json)). 원본은 gcp5 디스크에 보존한다.

[시간순 직접 영상 검토](playback-review.md)는 개요+r1+r2 전체0–40초2Hz와 마지막30–40초10Hz다. gcp5 ffmpeg으로 만든3배속 영상은401프레임·13.366667초·60,377bytes다. GUI 없이 ffprobe로 확인하고, 실패 보정31.3/38.3초와 개선 보정33.3초를 프레임 띠에서 직접 봤다. 이는 같은 실행의 구간 사례이고 독립 실패2+성공1 실행으로 부풀리지 않는다. Mac에는 요약·검토 미디어47파일(3,629,012bytes)만 회수·SHA검증했다([회수](playback-retrieval.json)). 원본 RGB/정답 복사0. 선택적 그래프는 matplotlib 부재로 만들지 않았고 수치표·ffmpeg 검토를 보존했다.

[실제 재현 명령](reproduce-native-r2.json)은 기존 완료 실행의 명령을 그대로 기록한다. 재실행 때는 새 출력 이름을 쓰고 별도 평가 queue의 `renderer_source`/`renderer_receipt`를 원 녹화와 맞춘다. 새 물리 인수 없이 결과를 기본 적용하지 않는다. 새 번들 ID/공용 backend/장면/warpfit 모듈 수정0, 표준 관리의 새 물리 인수도0이다.

비물리 변경 시험 **7 passed**, diff 검사 통과([검증](validation.json)); 기존53개 결과와 합산하지 않는다. 전체 CI·독립 검토·병합은 별도이며 DRAFT를 유지한다. no wallcap·idle20/budget-stop 유지, CPU VM 시작0·모델키/에이전트 자격증명 전송0·모델호출0·Drive/GUI0이다.

자체 Python/MuJoCo/ffmpeg0·GPU0·다른 임대0·자체 임대 제거를 확인하고, 전송 ACK2건 뒤 gcp5를 직접 정지했다([종료 점검](operations/close-c3.json)). **2026-10-16 23:50:43.189 KST (14:50:43.189 UTC), TERMINATED** 확인([GCP 영수증](operations/gcp5-after-stop-c3.json)). 실제 청구 비용은 별도 미측정이다.
