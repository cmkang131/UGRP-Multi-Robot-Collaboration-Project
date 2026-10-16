# mapbuild9 — 정적 지도 AMCL 저장 재생 후보

**최종 NOT_READY. 지도 문제는 아직 해결되지 않았다. 새 물리0회.** 기본 off `selfmap_map_correction_v1`의 새 method `static_amcl_v1`. 자기 지도는 기록하고 보정 우도에는 사용하지 않는다. 전역 자유 공간 균일 초기화, spawn/정답 입력 금지. 입자 분포 미수렴 때 인계·운반 금지.

수정 전 분포: [이전 거부표](prior-rejection_table.json). 자기 서브맵 비영 보정 오채택4/4, 초기 정적 등록 모호2/3·고잔차1/3.

## 먼저 읽은 참고 자료와 라이선스

- [Fox 2001 KLD-Sampling](https://papers.neurips.cc/paper_files/paper/2001/file/c5b2cebf15b205503560c4e8e6d1ea78-Paper.pdf), §2–3·식7: 알려진 지도에서 이동/관측 갱신과 다봉 전역 위치추정, 점유 bin에 따른 입자 수.
- [Thrun/Burgard/Fox Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/), 5장 sample_motion_model_odometry·6장 likelihood field·8장 MCL/AMCL/전역 초기화 및 kidnapped recovery. 출판사 서지만 확인; 책 본문 전체 신규 열람 아님. 코드에 대응하는 교과서 쪽136은 아래 Nav2 원문의 주석으로 확인.
- [Nav2 공식 AMCL](https://docs.nav2.org/configuration/packages/configuring-amcl.html): 이동 상수·우도장·관측 간격·recovery/입자 설정.
- [Nav2 고정 소스](https://github.com/ros-navigation/navigation2/tree/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_amcl): differential_motion_model.cpp의 순방향/역방향 대칭 odometry, likelihood_field_model.cpp의 `1+sum(pz^3)`, pf.c의 KLD 다항 재표본화·평균 우도 recovery를 줄 순서대로 NumPy로 옮긴다. 소스·원저작권·LGPL-2.1-or-later 전문·SHA는 `harness/mapbuild_amcl_vendor/`에 함께 보존. 기존 UGRP AMCL 포트와 비교하되 새로운 scan matcher를 만들지 않는다.

라이다 실험 성능은 자기 RGB 가상 스캔 성능으로 승계하지 않는다.

## 사전 동결한 비교 조건

R1/R2 자체 영상에서만 이동 모델을 동결하고 R3는 held-out이다. 빈 FOLDED
회전은 mapbuild8의 `own_command_motion_v1`과 정확히 같은 명령 signature에서만
사용한다. R1/R2 기존 OFF와 달라질 수 있으므로 같은 새 융합 증분의 OFF를
함께 다시 계산한다. R3 새 OFF 끝43.216mm/3.311°는 기존과 일치했다.

초기 `calibrated_kld_v1` 100000→최소2000 비교 뒤, 표준 설정의 두 진단을
추가했다. `fixed_population_v1`은 같은 σ=.0202m에 min=max=100000으로 고정;
`nav2_sigma_fixed_v1`은 입자100000을 유지하면서 공식 Nav2 기본 σ=.2m를 쓴다.
둘 다 코드/상수를 먼저 커밋하고 전체 예측을 봉인한 뒤 평가한다. 데이터에서
수용 문턱을 맞추거나 정답을 이용해 입자를 초기화하지 않는다. 필터가 좁아져도
정답이라는 보장은 없어 별도 평가가 잘못된 수렴을 센다.

## 알려진 입력·운영 한계

- R1 원본에 scans.json이 없고 실행 원장에는 scan 전체가 없어, mapbuild8에서
  같은 자기 RGB로 재구성한 `replay-r1-v2/scans.json`을 입력으로 명시했다.
  R2/R3는 원본 scans.json을 사용한다. R1 최초 경로 누락 오류는 예측 생성 전
  운영 실패로 별도 보존하며 물리 라운드에 합산하지 않는다.
- α1/α4는 이전 R2 반복 회전의 자기 LK predictive covariance/평균 회전량²,
  α2/α3는 R1/R2 LK 보고 분산 잔여를 비음수 회귀했다. 이것은 실제 이동 오차의
  GT 보정이 아니며, 직선·적재 경로의 시스템 오차는 검증되지 않았다.
- gcp3 입력은 열린 집게·드문 pan418뷰다. 이전 owner source의 자기 RGB
  추출기를 그대로 호출했으며 실제 저장 대기 .8/1s에 따른 settled만 사용했다.
  빠른 차체 이동·적재 FK·들고 있는 물건 위치 사용 자격을 뜻하지 않는다.
- 최신 stack check는 `historical_replay`로 통과했다. 현행 물리/전체 스택을
  새 실행으로 입증했다는 뜻이 아니다.

## 최종 결과 — 같은 저장 자료, 조건별 분리

|조건|R1 수렴 제안/오류|R2 수렴 제안/오류|R3 수렴 제안/오류|판정|
|---|---:|---:|---:|---|
|calibrated KLD · 가산 우도|0/0|0/0|1/1|NOT_READY|
|100000 유지 · 가산 우도|0/0|0/0|0/0|NOT_READY|
|100000 · 공식 σ=.2 · 가산 우도|0/0|0/0|0/0|NOT_READY|
|100000 · 곱 우도, 반환 열 압축(퇴역)|0/0|2/2|6/6|NOT_READY|
|100000 · 곱 우도, 원래96열→NaN 건너뛰기(현재)|0/0|2/2|4/4|NOT_READY|

총15재생은 같은 R1–R3 1044프레임의 반복이며 독립15실험 성공률이 아니다.
각 후보의 전체/구간별 ATE·끝 오차·수렴 SIM초/자기 추정 이동량·원본/재현 명령은
[전체 비교](remote-export/comparison.json), [각 실행 요약](remote-export/),
[관문별 funnel](rejection_table.json), [기계 판독 최종 요약](summary.json)에 있다.
평가 정답은 예측 봉인 뒤 별도 프로세스에서만 열었다.

R3 같은389프레임의 OFF 끝43.216mm/3.311°(XY RMSE29.769mm)는 기존과
일치했다. 현재 곱 우도 후보는35.2SIM초에 처음 좁아졌지만 끝 전역 후보 오차는
**1.823m/91.149°**이고, 수렴 제안4건 전부 요구표 밖이다. 첫 수렴까지 자기
추정 이동량 .485056m, 별도 평가 이동량 .208434m이다. R2는32.3SIM초에
처음 좁아졌으나 오제안2건, R1은 끝까지 미수렴이다. 미수렴 가중 평균을 올바른
전역 궤적으로 채택하지 않는다. OFF는 시작 SE2 정렬/척도1의 상대 오차이고, AMCL
전역 값은 정렬 없이 정적 지도 좌표로 채점한 **진단 후보**다. 두 gauge를 숨겨
초기화 전 전역 평균 오차를 실제 제어 악화나 공정한 상대 drift로 해석하지 않는다.
수렴 뒤에도 전역 요구표를 틀렸으므로 OFF 개선/물리 제출 관문은 모두 거부다.

자기 지도는 관측한 가상 벽 스캔과 인과적 자기 odom 자세의 키프레임으로 계속
저장했다(R3 39개). 이를 위치 우도에 되먹이지 않았다. 올바른 정적 위치로 보정한
지도 품질·coverage 향상은 **확인 안 됨**이다. 모든 새 자료의 닫힘 명령/적재 주행은0;
servo_fk_carry_v1의 실제 적재 주행·문·구역·복귀·놓기 자격도 확인 안 됨이다.

### gcp3의 별도418뷰

warp8f 원본14세계/28로봇의418뷰를 동일 calibrated AMCL로 한 번 재생했다.
프레임 funnel **418→벽190→관측 갱신176→수렴0**, 로봇 전역 수렴0/28,
인계 요구 충족/개선0/28이다. [결과](results/gcp3-418views-evaluation.json),
[관문표](operations/gcp3-rejection_table.json). 열린 집게의 드문 pan 기록이며
적재 주행·release 성공 근거가 아니다. gcp5 수치와 합산하지 않는다.

## 확인한 실패 경로와 남은 원인

현재 R3 곱 우도의 첫0.4SIM초 관측 직전에는 기존 인계 오차 범위 안 입자가
23/100000개 있었지만, 관측 뒤 가중치 합이1.1356e-28이 되어 재표본화 뒤0개로
사라졌다. 다음1.4–4.6초5갱신에도 그 범위 내 입자0이다. 정답은 이 영역을
채점하는 별도 프로세스만 사용했다. [6갱신 지원 대역 추적](results/r3-support-trace.json),
[trace 봉인](operations/trace-seal.json). 스냅샷을 더한 재생의 trajectory.json은
원본 현재 후보와 **바이트 SHA 일치**다. 기록 때문에 행동/추정이 바뀌지 않았다.

이는 현재 곱 우도/제안 분포 조합에서 첫 관측이 올바른 위치 주변 표본을
제거한 구체적인 경로다. AMCL 일반의 실패, 인식 전체의 오류, 수학적으로 완전한
장면 모호성을 증명한 것은 아니다. KLD를100000 고정으로 바꾸어도 미해결이므로
입자 수 조기 축소 하나로 모든 원인을 설명하지 않는다. 정적 likelihood에서
진단 정답의 우도가 높은 것과, 유한 표본 posterior가 그 위치를 유지하는 것은
별도 문제다. 실제 ROS 노드와 전체 필터 동등성은 아직 확인 안 됨이다.

## 구현·검증 범위

- 기본 off `StaticAMCL`/method `static_amcl_v1`: 전역 자유 공간 초기화,
  자기 명령+LK와 기존 반복 명령 모델, 정적 벽 likelihood, 다봉 입자/KLD,
  augmented recovery, 전체 posterior 분산·P95·ESS를 기록한다. 기존 CSM 기본
  경로/접촉/카메라/모델 설정은 바꾸지 않았다.
- 현재 API는 `runtime_qualified=false`, `ready_for_handoff=false`,
  `adopted_pose=null`이다. 좁아진 분포는 proposal만 기록한다. 초기 후보 raw의
  ready는 실험용 분산/ESS 제안 관문이며 실제 인계 승인으로 승계하지 않았다.
  `SelfMapCorrection`/실제 운반 실행기에 새 방식은 아직 연결하지 않았다.
- 미관측 열을 먼저 삭제하던 차이를 고쳐, Nav2 원문처럼 원래96열에서 stride를
  고르고 NaN을 건너뛴다. 곱 우도는 `likelihood_field_model_prob.cpp`의
  do_beamskip=false 경로를 옮겼다. 이웃 RGB 열의 독립성은 자격 미확인이다.
- Mac 비물리 **18개 통과**(새 모듈9+기존mapbuild8 9), gcp5 최종 후보9개 통과.
  [원문 C++/C 수치 대조](operations/native-parity-full.json): 이동5조건/1000표본
  최대 SE2 차2.0213e-15, KLD12조건 일치, 가산/곱 우도의 dense/NaN4조건 최대
  상대 차2.28e-13. 동일 정규 난수와 fixture 지도 ABI shim 검사이며, 전체 ROS·
  Gaussian RNG 바이트 동일·물리/실물 성공 검사가 아니다.
- 원본2151파일,15후보+동일 궤적trace의16봉인 입력/예측 해시 불일치0.
  gcp3 JPEG418와 봉인142파일 불일치0(실제 개수는 integrity 원문 기준).
  [gcp5](remote-export/final-integrity.json), [gcp3](operations/gcp3-final-integrity.json),
  Mac 회수63파일 해시 일치를 확인했다. raw RGB/상태/입자 배열은 VM 디스크에 유지했다.
- 원인 검토: [직접 본 영상 시각/타임라인](playback-review.md). R1/R3 실패를
  전부2Hz로, R3 마지막10SIM초를10Hz로 확인했다. 성공 운반1개 대조는 자료가 없어
  미충족이다. Mac 앱/GUI0.

## 운영 오류와 다음 경계

R1 scan 경로 누락, clone checkout 완료 전 runner 시작은 예측 전 HOST_ERROR로
분리 보존했다. C++ 시험 shim의 사용하지 않는 alpha5_ 선언 누락은 수정 후 통과했다.
선택적인 그림은 VM matplotlib 부재로 만들지 못했고 수치 JSON은 보존했다.
실패들을 지우거나 성공 실행으로 바꾸지 않았다. 상세는 summary.json의 operator_failures.

사용자 조건인 “오프라인에서 OFF보다 좋아질 때만 새 물리”를 충족하지 못해 새
물리/적재 라운드는0회다. 요구표200.751mm/방향결합21.423°·점수·수용 문턱을
낮추지 않았다. 다음 검토는 새 정합기/임의 상수가 아니라 교과서8장과 공개
AMCL recovery/제안 분포를 먼저 대조하고, 초기 지원 대역 소실·상관된 가상 스캔의
측정 자격을 분리해야 한다. 관측에 맞는 σ와 운동 분산의 시간 집계를 자기 자료로
동결하고 같은 봉인 재생에서 다시 판정하기 전에는 [다음 큐](next-queue.json)를
제출하지 않는다. 새 실제 경로·ACT·LLM 성공은 확인 안 됨이다.

## 호스트 종료와 전달

gcp5 종료 전 자기 lease 해제·타 Python/MuJoCo/ffmpeg0·GPU0%/0MiB를 확인했다.
- gcp3: **TERMINATED**, cloud lastStop 2026-10-17T04:31:29.604000+09:00; [실제 상태](operations/gcp3-terminated.json).
- gcp5: **TERMINATED**, cloud lastStop 2026-10-17T04:46:12.232000+09:00; [실제 상태](operations/gcp5-terminated.json).

gcp3의 기존 비어 있는 `.warp9-claim.lock`은 열린 holder0이었으나 다른 작업 파일이므로
보존했고 수동 정지는 보류한 뒤 cloud TERMINATED를 확인했다. 종료 원인은 별도로
단정하지 않는다. gcp5는 정상 stop 명령을 사용했다. 원본 디스크·동결 소스 보존,
가드 설정 변경0·CPU VM 시작0·새 모델 자산0이다. PR #556은 DRAFT/NOT_READY로
갱신하고 병합하지 않는다.
