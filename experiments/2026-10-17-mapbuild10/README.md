# mapbuild10 — 측정모델 감사·시작 구역 사전 후보

**NOT_READY / START_ZONE_INPUT_REQUIRED. 지도 문제는 아직 해결되지 않았다.**
측정 감사와 기본 off 후보 구현은 완료했다. 실제 시작 구역 범위·대략 방향이 원본에
없고 외부에서도 아직 제공되지 않아, 새 AMCL 재생·ATE 개선·적재/새 물리는 **미측정**이다.
spawn/평가 정답을 반올림해 시작 구역을 만들지 않았다. PR #556 DRAFT 유지.

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
- Mac 비물리24개와 gcp5 같은24개 통과. sparse 어댑터는 compile/help 확인만 했다.
  [검증](validation.json). 전체 프로젝트 CI/실제 ROS 노드·물리 인수는 확인 안 됨이다.

## 시작 구역이 없어 남은 판정

R1–R3 정적 지도에는 시작 구역 필드가 없고, gcp3의14개 정적 지도·28개 스트림에도
start_zone/start_zones·시작 구역ID가 없다. [gcp3 원본 인벤토리](operations/gcp3-start-zone-inventory.json).
[필요 입력](start-zone-priors.required.json)에 실제 운영 사전이 없는 상태를 명시했다.
정확한 시작점이나 eval-only를 반올림해 대체하지 않았다.

따라서 새 후보의 수렴 수·오수렴 수·끝 ATE·구간 오차·수렴까지 이동량·인계 요구표
통과 수는 **미측정(null)**이다. mapbuild9 OFF의 R3 끝43.216mm/3.311°는 이전
봉인 기준값이지 이번 새 후보 개선 결과가 아니다. 요구표200.751mm/결합21.423°는
낮추지 않았다. 새 물리는0/최대3회이며 OFF 개선 전 제출하지 않는다.

별도 gcp3에서는 새 필터를 돌리지 않고 원래418뷰의 측정만 감사했다.
프레임 funnel **418→벽190→기존 갱신176**, 새 시작 사전이 있는 스트림은0/28이다.
[JPEG418·기존 입력/예측 봉인 해시 불일치0](operations/gcp3-integrity.json),
[감사](operations/gcp3-measurement-summary.json), [표](operations/gcp3-rejection_table.json).
418뷰의 새 후보 재생 성공이나 실제 release 성공을 뜻하지 않으며 gcp5와 합산하지 않는다.

[현재 funnel](rejection_table.json)은 gcp5 입력3→사전0, gcp3 입력28→사전0을
분리한다. [다음 큐](next-queue.json)는 rejection_table 절대경로와 ready=false를 가진다.
[영상 검토](playback-review.md)는 실패 R1/R3 전체2Hz·R3 마지막10초10Hz를 파일로
직접 확인했다. 성공 운반 대조 영상은 없어 미충족이다.

## 원본·운영

코드는 실행 전에 commit/push했다. 분석은 원본 L4 VM CPU에서만 했고
Mac 시뮬레이션/렌더/학습/GUI·모델 호출·CPU VM 시작·키 전달은0이다.
원본·실패·기존 예측은 보존했다. 대형 감사 JSON은 zstd 해제 전체 SHA 확인 뒤
압축본으로 보존했다([gcp5 영수증](operations/audit-integrity.json)). Mac에는 작은
요약/표/기존 몽타주만 회수했다. 준비 오류는 [별도 기록](operations/operator-errors.json).
UGRP는 Drive를 사용하지 않는다. 새 모델 산출물도 없다.

gcp5는 자기 lease 해제·타 작업/GPU0 후 **2026-10-17 10:53:47 KST TERMINATED**를
확인했다([cloud 상태](operations/gcp5-stopped.json)). gcp3는 자기 lease 해제·타 작업/GPU0을
확인했지만 기존 `.warp9-claim.lock` 때문에 수동 정지를 보류했고 파일을 보존했다.
유휴20분 가드를 유지하며 cloud TERMINATED 확인은 아직 대기 중이다.

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
