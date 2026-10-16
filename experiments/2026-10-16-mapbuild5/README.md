# mapbuild5 — 벽 색 경계 가상 스캔 + 기존 GMapping식 RBPF

**rbpf-ack / ownership-ack. 진행 중이며 성능 판정 전이다.** 같은 `codex/mapbuild1`, PR #556에 잇는다. 사용자 2026-10-16 원문: “mapbuild4에 벽 색 경계 가상 스캔 + GMapping식 입자 필터를 넣고, MASt3R-SLAM은 같은 녹화 영상으로 비교만 해줘.” 원본·분석은 gcp5(`ugrp-act-l4-gcp5`, `ugrp-sim-e-1016`, `changmin5781@gmail.com`)만 사용한다. 다른 작업자의 코드·결과와 합산하지 않는다.

현재 상태: MJWarp 왕복 녹화 실행 중. 과거 FOLDED 41프레임 배관 재생은 삽입4·개선 제안3, 빈 RGB는 unknown96·삽입0을 확인했다. 이는 새 주행 성능이나 실제 지도 확장 결과가 아니다. 새 결과·회수·종료 확인 전에는 완료로 보고하지 않는다.

## 수정 전 거부 원인

[사전 분포표](prior-rejection-table.json): egomap24의 t13.7 이후 거부48회는 search_boundary37, low_overlap10, high_residual1이다. yaw가 국소 ±8° 탐색창을 벗어난 문제와 거부 뒤 과도한 재표본화가 주요 과거 제한이었다. egomap26의 유효 스캔 삽입은7→55로 늘었으나 거부 재표본19회·최종 조상1개가 남았다. egomap27은 삽입+선택적 재표본+Manhattan 결합으로 거부 재표본0을 확인했으나 wide의525/891시각이2σ 밖이었다. 종료 한 점의 개선을 경로 전체 확신도로 해석하지 않는다. 과거 tape/장면/호스트 수치는 이번 결과와 합산하지 않는다.

mapbuild4의 횡60ms 되밀림은 CPU·MJWarp 양쪽에서 남아3라운드 종료했다. 접촉 원인을 더 파거나76배 역이득을 넣지 않는다. 새 녹화는 측정된 전진100ms와 좌/우400ms만 쓴다. warm400ms 약44mm와 cold/warm 전체 응답을 명령 예측 평균·문맥 공분산으로 쓴다. 이 분산은 독립 반복 측정의 신뢰구간이 아니다. 모델 파일에는 원본 NPZ/metrics/summary 경로와 SHA를 보존한다.

## 구현과 비교 경계

- 기본 off `mapbuild_rbpf_v1`: [위치 추정 어댑터](../../harness/mapbuild_rbpf.py). 자기 JPEG를 고정 K/D로 보정하고, 기존 `ColourBoundaryState` v2의 벽–바닥 경계96열을 서보 명령 FK의 바닥 평면으로 투영한다. 거리·방위·이유를 열마다 보존한다. 자기 차체 투영/동료 RGB 열은 제외하고, 미관측은 `range_m=null`인 unknown으로 둔다. 연속해서 관측한 인접 열만 잇고 가림 사이를 채우지 않는다.
- `SelfWallMemory(... own_map_rbpf_v1)` / `self_map_rbpf.py`의 개선 제안·정확한 중요도 비율·입자별 log-odds 격자를 그대로 쓴다. `rbpf_rejection.py`와 `rbpf_composition.py`의 결합은 거부 스캔에 CSM 가중치/재표본을 적용하지 않고 sampled motion 위치에 삽입한다. Manhattan은 첫 자기 관측에서 얻은 잠재 축만 쓴다. 정답 축/정적 지도는 없다.
- 이동 입력은 측정된 LK 바닥 증분·전체3×3 공분산, 그 외에는 고정된 과거 MJWarp 명령 응답·공분산이다. 공분산은 해당 구간에 한 번만 회전·전파한다. 새 녹화 정답으로 평균/분산/상수를 맞추지 않는다.
- ROS의1m/.5rad 이동 관문 설치 구조를 재사용하되 이번 짧은 왕복의 스캔 스케줄은 기존 CSM의1 SIM초다. 실제 wall초를 관문으로 쓰지 않는다. `pf_sensor_proposal.py`의 추가 혼합 제안은 **off**다. 기존 Grisetti Gaussian 제안을 유지하여 추가 가정의 효과를 섞지 않는다.
- [녹화](../../scripts/mapbuild5_capture.py)는 기존 mapbuild4 clean-start/장면/휠 relay/MJWarp graph를 재사용한다.18회 전진100ms 뒤 좌10회/우10회400ms를 각1초 주기로 발행,40 SIM초에 `cap_end`한다. 마지막10 SIM초를 포함한 전체10Hz 자기 카메라·r2·평가용 개요를 남긴다. 프레임 시점을 독립 렌더 세계16개로 묶는 최적화는 **완료된 물리 궤적의 렌더만** 바꾼다. 물리 리셋/GT 보정 주행이 아니다. 새로운 장면/접촉/공용 backend 수정0이다.
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

연습 원본은 `/home/ugrp/ugrp-sim/shares/mapbuild3-practice/manifest.json`, SHA `6b01b075aa8786f821a6d63e17268b486ec5c422bc13a4745fd07a98c7d12e0c`이다.89파일 재검증, 자기82프레임이며 HIGH는 미자격이다. mast3rcmp의 ops-alert ACK(13:52:34 UTC)는 gcp4로 RGB82/82 SHA 일치·전송 완료를 확인했다. 본 녹화 매니페스트는 완료 뒤 공유한다.

[시도 원장](attempts.json), [비물리 검증](validation.json), [운영 기록](operations/). 과거 연습 입력을 위한 상대 자산 cwd·보정 closure·RGB 경로 가드 오류는 각각 보존했다. strict SHA/path guard를 약화하지 않았다. 겹치는 두 테스트 묶음36/20 passed를56개 독립 테스트로 합산하지 않는다.

gcp5 실행상한/자체 wall상한 추가0, idle20·budget-stop ACTIVE 확인. gcp2CPU 시작0, 모델/키 전송0·Mac GUI0·Drive0. 최종 프로세스/타 lease/공유 전송 확인과 직접 정지 시각은 아직 미완료다. 실제 청구 비용은 별도 미측정이다.
