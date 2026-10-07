# 공개 navigation 평가 어댑터 v2

구현 전 사전 등록과 변경하지 않은 성공 기준은 [public navigation §7](../2026-10-07-mapfree-public-navigation/README.md#7-평가-어댑터-v2-사전-등록-구현-전-2026-10-07),
커밋 `e194bb59`다. 이전 v1/실패 자료는 보존한다. 결과는 개발/과거 실패 진단/새 확인을 분리한다.
순수 2D 오프라인만 사용하며 MuJoCo·모델 호출·패키지 설치0. PR #409 DRAFT, 병합하지 않는다.

## 구현·새 시작점 등록 (실행 전)

사전 등록 `e194bb59` 및 첫 도크 HOST_SETUP_ERROR 보완 `b333019d` 뒤 구현했다.
[cohort.json](cohort.json)은 새 I/J×5701/5702 32쌍, 도크 원점/이동/거부24후보와 출처 해시를 담는다.
모든 배치의 선택점은 원 도크에서 동쪽 .10 m다. 실제 S2 reset에서 출발한 주행 결과가 아니다.
첫 실패의 빈 파일도 `cohort-host-error-empty.json`으로 보존했다. 기하 후보는 과제 결과로 선별하지 않았다.

`navigation=public_ros_v2`는 별도 actor/runner다. v1 파일·원 센서 모델·B v3는 변경하지 않았다.
원본 라이선스/바이트/포트 경계는 [SOURCES](../../third_party/mapfree_navigation_recovery/SOURCES.json)와
[설명](../../third_party/mapfree_navigation_recovery/README.md)에 있다. ROS 전체 동작과 동등하다고 주장하지 않는다.
Spin .5 rad/s, curvature 최소 반경 .24 m, 보정 후 명령 포화는 UGRP 속도/크기 어댑터다.
Nav2의 동작 순서/거리/대기/횟수는 그대로지만 원본 acceleration, ROS BT scheduler는 실행하지 않는다.
2 s 관측+1 s 행동이 회복 중에도 비용에 들어가며 spin/backup 제한은 modeled10 s다.

기존16 + 새8 =24 시험 통과: off bytes, 원본 해시, 회복 순서/상한, carrot 예측,
static/current obstacle 보존, valid setup, actor import 경계, 관문29/32 차단.
로컬 패키지 설치/새 venv0, CPU 시간 벤치마크가 아니므로 lock 미사용.
