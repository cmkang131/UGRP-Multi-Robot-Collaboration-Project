# egomap49 — 전에 자기 카메라로 본 B로 돌아가기 6회

2026-10-08 사용자 승인, **실행 전 사전등록**. 기준 `78084cf1` / PR405 DRAFT.
벽 검출기 egomap34 설정 동결, 개선/재튜닝0. 과제의 성공은 지도 품질 관문과 별개다.
설정: egomap47의 tape_v1·SEARCH·real_v1 강성·v122_rotL·RBPF100·graph·switchable·
TSDF support·inverse sensor·Manhattan·±20°·선택재표본·삽입수정·public_ros_v8·
Nav2 recovery·frontier 목표유지/360°관측·navfn_recovery_v1 그대로.
egomap48의 byte 동일성 입증 `scalar_rays_v1` + `match_cache_v1`만 추가 on.

## 실행 수·시간·목표

- 새 seed **49001,49002,49003,49004,49005,49006** 순서, 각1회 **총6회**.
  다른 seed의 이전 DEV와 합산하지 않는다. seed-audit.json에 원격 ref 검색 기록.
  시작 자세/장면은 egomap47 그대로라 다른 시작/장면 일반화 시험은 아니다.
- **360 SIM초 탐색**을 완료한 다음 위치 잃음 처리. 몸 순간이동0.
  egomap43와 같이 자기 snapshot의 free 전체·yaw균등100000입자로 초기화한다.
  loss 이전 pose를 초기 prior로 주지 않는다. AMCL/KLD·floor_zones_doors_v1·우도α=.5 불변.
- 탐색 중 floor_color_v3에서 **처음 확인한 자기 B 후보**만 기억한다.
  첫 색 검출 시각, 확인 시각, RGB/관측ID를 보존하며 목표 지정은 loss 때(반드시 그 뒤).
  미관측이면 GT 목표를 주지 않고 목표 미관측 실패로 센다. 상대 지도/배열 공유/모델0.
- snapshot은 strict t<loss의 online 지도·랜드마크·자기 목표만. loss프레임은 양쪽 입력에서 제외,
  재위치는 strict t>loss RGB만. 최종/미래 지도 역주입과 GT 정렬0.
- 최대 **630 SIM초=360 탐색+270 재위치/귀환**. 270은 egomap43에서 B가 이미 확인되어90초에
  전환할 경우 기존 전체360초까지 허용되던 잔여예산이다. 이번 사용자 변경은 탐색 예산이며
  도착/종료 문턱은 바꾸지 않는다. 재위치60초 미수렴 시 기존 dev_light 로그 후 귀환 시도 유지.
- 매회 60분 HOST 상한, raw합계6GiB 예산. 여유<10GiB/ENOSPC=HOST_ERROR.
  예상20–40분/회, 합계2–4시간+잠금대기(가속 비용모델 참고값, 보장 아님)를 감독 파일에 기록했다.
  한 번에 한 물리, agent_lock status=null에서 acquire·ugrp_session·종료 후 release.
  S2 점유 시 기다리고 다른 프로세스/잠금에 손대지 않는다. 우선순위 조정/freeze/유료자원0.

## egomap43 도착·종료 판정 그대로

- 내부 `resolved` **5프레임 연속**이고 자기 추정 중심과 기억한 B 중심 거리가 **≤0.20m**이면
  도달 선언·hold·종료. GT는 이 선언을 바꾸거나 제어에 돌려주지 않는다.
- 선언 시 **GT 차체 중심이 실제 B 영역 안**이면 도착 성공. **거짓 선언0**.
  시간만 지나거나 실제로 B를 스쳤으나 선언하지 않은 경우 성공으로 세지 않는다.
- 기존 물리 실패(wall contact/tilt/nonfinite 등) 중단, 예산 종료, HOST 오류를 모두 보존.
  정답 재위치(XY≤.25m, yaw≤10°,5프레임)도 egomap43 그대로 별도 보고하며 도착과 혼동하지 않는다.
- 실패/목표 미관측/중단도 사전등록6회 분모에 포함. 숨긴 제외·다른 seed 대체·조건 변경0.
  물리 시작 전 환경 오류는 시도0으로 따로 공개하고, 실행이 시작된 슬롯은 재실행하지 않는다.

## 결과 전에 고정한 보고·분류

시도수/실제 선언 도착수/거짓 선언수, 종료XY 오차 중앙·최대, **오차÷로봇 보고σ >3** 횟수,
XY NEES `e_local.T @ inv(CovXY) @ e_local`(평가 GT만 자기 시작 프레임으로 변환),
벽/로봇 접촉 표본·연속 표본 episode 수, SIM/wall시간을 보고한다.
PF의 σ는 원 `global_std_xy_m=sqrt(trace(CovXY))`, 탐색 종료의 보고σ와 정의를 구분한다.
공분산 특이/마지막 GT 누락은 숨기지 않고 NA/마지막 공통 시각·차이를 기록한다.
전체 후속 프레임의 >3σ 비율도 보조 지표이고 6개 독립 시도로 합산하지 않는다.
지도 snapshot의 덮음·점유칸/스캔·시야벽 표본 수를 함께 기록한다.

실패 대표 원인 우선순위(사후 문턱 변경0):
1. HOST/실제 물리 중단 → 기타(원 예외/접촉 별도).
2. loss 이전 자기 B 미확인 → 탐색 미커버.
3. 거짓 선언 또는 종료XY>.25m 또는 정답 재위치 한 번도 없음 → 위치 오차.
4. 위에 해당하지 않는 미도착 → 경로/예산(원 no_path/recovery/hold 기록 첨부).
성공이라도 위치 과신·거짓수렴은 그대로 공개한다.

## 산출·검증

raw `/Users/changmin/projects/ugrp/outputs/own-map-return-repeat-v1/seed<seed>`.
실행 결과 봉인 후 별도 평가기만 eval_only/GT를 읽는다.
성공이 있으면 등록 순서의 첫 성공, 실패가 있으면 첫 실패를 골라 각각4배속
손목RGB | 당시 자기 지도·추정 경로·기억한B 영상을 만든다(최소1개).
그룹에 성공이 없으면 성공 영상 없음으로 명시하며 성공을 만들기 위한 추가 실행은 하지 않는다.
원본/명령/판정/해시 전부 보존. 로컬 raw 보관이며 원격 백업으로 표현하지 않는다.
초록 시험 후 source/설정/드라이버를 커밋해 코호트 동안 고정. 기본off byte 동일·바뀐 모듈1–3시험만.
단계마다 supervisor 확인, push 실패는 로컬SHA 진행 후 재시도. TensorBoard 생략 유지.
PR405 DRAFT·병합0, #406 및 다른 worktree 수정0. 실물/다른 장면 확증 아님.

기존 방법/출처: [egomap43](../2026-10-08-own-map-closed-loop/README.md),
[NavFn 시작·회복 egomap47](../2026-10-08-navfn-start-recovery/README.md),
[결과 불변 가속 egomap48](../2026-10-08-graph-runtime/README.md).
