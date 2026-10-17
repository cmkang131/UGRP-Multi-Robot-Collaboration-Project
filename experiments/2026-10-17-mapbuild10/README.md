# mapbuild10 — 측정모델 감사·시작 구역 사전 후보

**NOT_READY. 지도 문제는 아직 해결되지 않았다.** MC20 미개선 기록을 보존하고, 조정자 별도 승인으로 공개 시작 상자의 장경로 진단1라운드를 진행 중이다. 첫 녹화는 소스의 속도 정책 오류로5.1 SIM에 중단·제외했고 교체 녹화 f3a91cb85를 실행 중이다. 장경로·적재 결과는 확인 안 됨이다. [편향 원인 표](bias-review.md), [418뷰 벽 관측 분포](wall-observations.md).
측정 감사 후 조정자 운영 정의에 따라 합성 시작 사전과 전역 초기화를 각20회 비교했다.
R3 합성 사전은20/20 수렴·오수렴0이지만 끝 XY 중앙값61.96mm로 OFF43.22mm보다
나빴다. 별도 gcp3도 OFF 개선0이다. 기본 채택·인계/운반 자격·PR 병합은 없다.
새 사전은 평가용 조건부 Monte Carlo이며 실제 운영 시작 구역/새 물리 성공이 아니다.

## 첫 관측의 수치 경로

수정 전에 [거부표](prior-rejection_table.json)를 만들고 mapbuild9의 원본 예측을
검증했다. R1–R3 1044프레임의 점별 벽 잔차·거리 편향·모델 로그우도·지도 밖/먼 점 수와
저장 qpos의 카메라 FK를 프레임별로 계산했다. [측정 요약](operations/measurement-summary.json),
[카메라 요약](operations/camera-summary.json), [첫 6갱신 지원 대역](operations/support-models.json).
전체 프레임 표는 gcp5 `/home/ugrp/ugrp-sim/ops-reviews/mapbuild10/measurement-fk-r{1,2,3}.json.zst`.

R3 첫0.4 SIM초는 정답 자세에서 벽 최근접 잔차 P95 **15.064mm**, 지도 밖0,
거리장 잔차0이다. 정확한 평가 자세의 곱 로그우도는 **−32.7934**로 전체 최댓값이다.
그런데 인계 범위 내23개 유한 입자의 점 거리 중앙값은 **.13m**, 그중 가장 좋은
곱 로그우도도 **−94.7000**이다. 자세 허용 범위 안이라는 것과 좁은 센서 우도의
지지 범위 안이라는 것이 다르다. 정답 자세의 벽 점 오투영 때문에 전멸했다고 볼
근거는 없으며, 이 프레임은 유한 표본과 뾰족한 곱 우도 조합이 지지 대역을 제거했다.
이는 수치 underflow나 AMCL 일반의 실패를 증명하는 결과가 아니다.

|같은 관측 전 입자·사전 가중치의 반사실 측정|갱신 후 인계 범위 질량|10만 재표본화 기대 생존 수|
|---|---:|---:|
|기존 곱 σ=.0202m|1.1356e−28|1.1356e−23|
|곱 σ=.2m|.0071733|717.33|
|가산 σ=.0202m|.0004600|46.00|
|Nav2 기본 가산 σ=.2m|.0007075|70.75|

이 표는 **고정 입자 한 프레임의 평가 전용 반사실 비교**다. 새 궤적 재생·수렴·
정확도 개선으로 보고하지 않는다. 1.4초 이후 기존 분포에 이미 없는 지지 대역을
가중치만 바꿔 되살릴 수는 없다. 정답은 어떤 필터에도 제공하지 않았다.

기존 코드는 z_hit/z_rand=.5/.5, range_max=100m, 거리장 상한2m를 이미 사용했다.
단 σ=.0202와 마지막 곱 프로필은 Nav2 기본 likelihood_field와 다른 선택이었다.
원문 정수 stride를 그대로 따르면 max_beams=60인 **96열 가산 입력은96빔**,
곱 입력은48빔이다. “항상60개 이하”라고 부르지 않는다. RGB 이웃 열의 독립성은
확인 안 됨이며 새로운 stride·임의 상수는 만들지 않았다.

## 카메라·거리 꼬리 확인

|자료|명령 FK 위치 오차 P95|명령 FK 각도 오차 P95|갱신 프레임별 벽 잔차 P95의 최댓값|평가 실제 카메라로 재투영한 최댓값|
|---|---:|---:|---:|---:|
|R1|1.288mm|.318°|19.13mm|3.38mm|
|R2|.953mm|.256°|179.48mm|35.97mm|
|R3|1.013mm|.268°|171.66mm|37.32mm|

앞의13–20mm 진단은 선택한 프레임의 값이었고 전체 꼬리를 대표하지 않는다.
작은 명목 외부 파라미터 오차가 낮은 카메라/먼 접점 투영에서 커지는 구간이 있다.
R3 첫0.4초는 위치.471mm·각도.152°·높이 편향+.429mm이고, 명목 깊이를 실제
카메라에 놓은 점 높이 중앙값은−3.082mm다. 실제 카메라 바닥 재투영 잔차 P95는
3.417mm다. 이는 **평가 진단**이며 실제 카메라/관절·정답 보정은 제어에 넣지 않는다.
`mj_forward`로 저장 qpos의 기구학만 계산했다(적분/렌더0). 원래 점 높이0은
바닥 평면 투영 가정이고, RGB가 실제 벽 점 높이를 측정했다는 뜻이 아니다.

## 후보 구현·검증 범위

- `StaticAMCL`의 기본 off `selfmap_map_correction_v1`, 새 명시 프로필
  `nav2_defaults_v1`: 기존 vendor 가산 likelihood_field를 그대로 사용한다.
  σ=.2, 입자 최소500/최대2000, recovery alpha slow/fast=0/0은 공식 기본값이다.
  α1–α4와 LK/명령 융합은 mapbuild9의 자기 RGB 기반 동결값을 유지했다.
- 별도 기본 off `start_zone_prior_v1`: 운영자가 준 상자와 대략 방향에서 균일
  초기화한다. 기본 최소 .5m/방향 반폭30°는 조정자 설계(사용자 미확인)다.
  정적 지도에 더 작은 시작 구역이 실제로 있으면 literal start_zones 필드와
  일치하는 경우만 허용한다. spawn/pose 같은 추가 키·빈 출처·지도 불일치·정확한
  점 사전은 거부한다. 지도 파일 SHA는 실행기에서 확인한다.
- 자기 지도 기록은 계속 남고, 정적 우도는 자기 서브맵을 읽지 않는다.
  `runtime_qualified=false`, `ready_for_handoff=false`, `adopted_pose=null`을 유지한다.
  이 후보의 실제 운반 실행기 연결·적재 주행·지도 품질 개선은 아직 확인 안 됨이다.
- R1–R3 및418뷰용 실행 어댑터는 `--initial-prior`를 필수로 요구한다.
  예측 봉인 뒤 기존 별도 평가기로 요구표와 OFF를 비교한다. [API·재현](API.md).
- Mac 관련 비물리27개 통과, gcp5 코어 후보0df021e73에서24개 통과. MC 실행기는120/1120조건을 완료했고, 별도 직접 RGB sparse 어댑터는 compile/help 확인만 했다.
  [검증](validation.json). 전체 프로젝트 CI/실제 ROS 노드·물리 인수는 확인 안 됨이다.

## 조정자 운영 정의와 조건부 MC20

원래 정적 지도에 시작 구역이 없는 것은 [인벤토리](operations/gcp3-start-zone-inventory.json)로
확인했다. 이후 조정자가 [운영 정의](coordinator-mc-directive.md)를 제공하여 초기 입력
대기를 해소했다. 평가 하네스가 GT 시작점을 .5m×.5m 상자 안 무작위 위치,
방향±30° 안 무작위 값이 되도록 상자/방향 중심을 배치한다. **상자 중심을 정답에 맞추지 않는다.**
필터에는 범위만 제공하며 정확한 자세·상자 안 상대 위치·사전 생성 RNG는 제공하지 않는다.
사전 생성, 예측, 채점을 별도 프로세스로 분리했고 예측을 봉인한 뒤 채점했다.
정답을 전혀 쓰지 않았다는 주장이 아니라 **평가에서 생성한 제한된 사전 정보**를 쓴 것이다.

각 스트림에 합성 사전20회와 사전 없는 전역 초기화20회를 같은 입자 RNG로 비교했다.
모두 Nav2 기본 가산 σ=.2m·입자500–2000이다. 이전10만 입자 결과와 합산하지 않는다.
R1–R3는 저장한 자기 OFF 궤적을 SE(2) 차분해 재사용했으며 재합성 최대 차는
4.44e−16(gcp3는0)이다. RGB 해시1044/418을 각각 확인했다. 같은 프레임의 반복이며
독립20개 녹화·실제 출발 위치20종의 물리 시험이 아니다.

### gcp5 R1–R3

|자료/조건(각20)|수렴/오수렴 조건 수|끝 XY 중앙/p90 mm|끝 yaw 중앙/p90 °|같은 운동 OFF 끝 XY mm/yaw °|OFF 개선 관문 통과|
|---|---:|---:|---:|---:|---:|
|R1 합성 사전|0/0|56.39/110.33|1.49/3.24|25.13/2.60|0|
|R1 전역|0/0|2889.43/3187.94|125.51/173.75|25.13/2.60|0|
|R2 합성 사전|19/0|54.74/68.12|.41/.95|15.75/2.94|0|
|R2 전역|13/11|3155.59/5649.07|1.32/179.71|15.75/2.94|0|
|R3 합성 사전|20/0|61.96/73.65|1.37/1.95|43.22/3.31|0|
|R3 전역|11/7|3041.30/5687.94|88.39/179.05|43.22/3.31|0|

수렴은 전체 입자 분포의 기존 P95/ESS 제안 관문이며 실제 인계 승인이 아니다.
오수렴은 제안 시 실제 오차가 동결 인계 요구표200.751mm/결합21.423°를 벗어난 조건이다.
R1 합성 사전의 끝점은20/20 요구표 안이지만 분포 미수렴이라 채택할 수 없다.
R2 합성 사전은19/20 수렴, 첫 수렴 SIM초 중앙32.3/p90 34.1,
자기 추정 이동량 중앙.46920m/p90 .47031m다. R3는31.5/32.5 SIM초,
자기 이동량 .44283/.46698m다. 실제 이동량이나 적재 주행 성공으로 바꾸어 보고하지 않는다.

R2 OFF는 mapbuild9의 자기 R2 명령 보정 모델을 적용한 같은 운동 기준이다.
mapbuild8 실행 당시 R2 OFF와 다르며 그 숫자와 합산하지 않는다. R1/R2는 이동 모델
동결에 쓰인 자료이고 R3가 held-out이다. OFF는 GT로 시작 SE(2) 한 번만 정렬한 상대
drift이고 AMCL은 시작 불확실성까지 포함한 정적 좌표계 절대 오차다. 이 gauge 차이를
숨기지 않는다. 끝 XY뿐 아니라 기존의 **수렴 후 전체 요구표 유지·오수렴0·XY RMSE의
OFF 개선** 관문을 그대로 적용했으며 모든 조건이 실패했다. 점수/요구를 낮추지 않았다.

[전체 요약](operations/gcp5-mc20-summary.json), [구간별 중앙/p90 RMSE](operations/gcp5-mc20-phase-summary.json),
[관문표](operations/gcp5-mc20-rejection_table.json). R3 20조건의 끝 오차 벡터 평균은
(+55.31,+27.37)mm, 표준편차는(9.82,6.53)mm였다. 후보 우도가 평가 정답보다 높은
갱신은110/880이고 나머지는 같거나 낮았다. [봉인 후 진단](operations/r3-likelihood-summary.json).
이는 잔여 오차가 초기 전역 alias 제거만으로 해결되지 않았다는 관측이며,
특정 센서/운동 결함 하나를 원인으로 확정하거나 새 상수로 재맞춘 근거는 아니다.

### gcp3 별도418뷰

각28스트림×20의 합성 사전560조건 중 수렴3(w001-r1/w007-r2/w011-r2 각1),
오수렴0, OFF 개선0이다. 전역560조건은 수렴0이다.
합성 사전의 진단 끝점405/560은 인계 오차 예산 안이지만, 미수렴 제안을 실제
인계나 release 성공으로 세지 않는다. [28스트림별 중앙/p90 표](results-gcp3.md),
[전체 요약](operations/gcp3-mc20-summary.json), [구간 RMSE](operations/gcp3-mc20-phase-summary.json),
[관문표](operations/gcp3-mc20-rejection_table.json). 이 열린 집게·드문 pan 영상은
적재 주행·배치·내려놓기 실제 성공 근거가 아니다. gcp5와 합산하지 않는다.

[현재 funnel](rejection_table.json)과 [다음 큐](next-queue.json)는 입력 대기 대신
**OFF 개선 관문 실패**를 기록한다. 새 물리0/최대3회를 유지한다. 실제 공개 시작
상자에서 시작점을 균일 샘플링하는 새 물리 경로·적재 servo_fk_carry_v1 주행·ACT/LLM
인계·정확한 자기 지도 품질은 미구현/미검증 상태다. 오프라인 통과 전 제출하지 않는다.

[영상 검토](playback-review.md)는 실패 R1/R3 전체2Hz·R3 마지막10초10Hz를 파일로
직접 확인했다. 해당 코호트의 성공 운반 대조 영상은 없어 미충족이다.

## 원본·운영

코드는 실행 전에 commit/push했다. 분석은 원본 L4 VM CPU에서만 했고
Mac 시뮬레이션/렌더/학습/GUI·모델 호출·CPU VM 시작·키 전달은0이다.
원본·실패·기존 예측은 보존했다. 대형 감사 JSON은 zstd 해제 전체 SHA 확인 뒤
압축본으로 보존했다([gcp5 영수증](operations/audit-integrity.json)). Mac에는 작은
요약/표/기존 몽타주만 회수했다. 준비 오류는 [별도 기록](operations/operator-errors.json).
UGRP는 Drive를 사용하지 않는다. 새 모델 산출물도 없다.

MC20은 고정 소스9fa2aad39, 봉인 후 검증/압축은44a29092a로 실행했다.
gcp5 입력11/예측124파일·RGB1044, gcp3 입력11/예측1149파일·RGB418의 해시 불일치0이다.
GT 사전 생성 연결·원본 GT/자기 입력·예측 봉인을 모두 검증했다.
[gcp5](operations/gcp5-mc20-final-integrity.json), [gcp3](operations/gcp3-mc20-final-integrity.json),
[Mac 회수9파일 검증](operations/mc20-local-retrieval.json). 대형 원본/예측/자기 지도·
합성 상자/평가 전용 상대 위치는 VM 영속 디스크의 `runs/mapbuild10-mc20/`에 보존했다.
압축 해제 SHA가 일치하며 새 필터 예측을 바꾸지 않았다.

gcp5는 10:53:47 KST 1차 정지 뒤 조정자 MC 정의로 재시작했다.
MC 종료 후 두 VM의 자기 lease를 해제하고 다른 Python/MuJoCo/ffmpeg·GPU·활성 JSON
임대0을 확인했다. gcp3의 기존 `.warp9-claim.lock`은0바이트·holder0으로 보존했다.
조정자가 종료된 warp9 lock이 정지 차단 사유가 아님을 확인해 정상 stop으로 직접 정지했다.
최종 두 VM **TERMINATED**를 확인했다([gcp5](operations/gcp5-mc20-stopped.json),
[gcp3](operations/gcp3-mc20-stopped.json)). 유휴20/budget-stop은 변경하지 않았다.

## 먼저 확인한 참고 자료·라이선스

- [Nav2 공식 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/):
  센서/입자/recovery 기본값을 확인했다. 라이다 성능을 RGB 가상 스캔에 승계하지 않는다.
- [공식 likelihood_field 원문](https://api.nav2.org/nav2-rolling/html/likelihood__field__model_8cpp_source.html):
  p=1+sum(pz³), 원래 빔 슬롯에서 stride 후 NaN 건너뛰기.
- mapbuild9의 [고정 Nav2 소스](https://github.com/ros-navigation/navigation2/tree/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl),
  원문·LGPL-2.1-or-later·NOTICE는 `harness/mapbuild_amcl_vendor/`에 보존했고 수정하지 않았다.
- [Fox 2001 KLD-Sampling](https://papers.neurips.cc/paper_files/paper/2001/file/c5b2cebf15b205503560c4e8e6d1ea78-Paper.pdf),
  Thrun 등 Probabilistic Robotics 5/6/8장: mapbuild9의 검토와 이식 근거를 유지한다.
  이번에 책 전체를 신규 열람했다는 주장은 하지 않는다.
- PR #571의 시작 구역 사용자 결정은 이번 사용자 지시로 승인됐다. 열람 시 PR은
  OPEN이었으며 공용 configs/current_stack.json 소유자의 변경을 대신 병합하지 않았다.
