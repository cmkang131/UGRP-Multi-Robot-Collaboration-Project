# release25 — 새 장면의 release24 sweep 결함

PR #491 최신 `7c752fcdef2627a6aedd3766346a1241a1788d7b` 위 `claude/release25`.
gcp2 전용, C MuJoCo CPU 교사 관문. 장면은 확정된
`walls_floor_contrast_v5_indigo110_s80` + 원본 v1 바닥 + `no_mip_v1`,
`release_geometry_v1`, weld OFF, 학습 RGB·모델 호출 0. ACT 학생 검증은 아니다.
이전 a41781dd A31/40·B31/40, 다른 호스트/장면, 짧은 실행을 새 관문과 합산하지 않는다.

## 수정 전 거부 사유와 영상

`baseline-rejection_table.json`을 먼저 만들고 수정했다. 최종 선택 78회는
성공62, 실패1, 감독 중단15이며 미제출2는 별도다. 사유 분포는
`static_sweep` 2(A실패+B감독 중단에 같은 결함), 실행 예외15, 복구된 FOV 거부3이다.
감독 SIGINT를 제어 결함 15건으로 해석하지 않는다.

실패 A110633 전체0–56.1 SIM초를2Hz, 실패 사건 직전 world45.5–55.5초를
native 자기 RGB 10Hz 띠로 직접 확인했다. 성공 B110600 전체0–32.2초를2Hz로
확인했다. 실패 초기/중간/끝 native 1Hz 저장 입력에서도 로봇별6장(0/9/18/27/36/45초)을 별도 몽타주로 확인했다. 각 개요+r1+r2 3배속 영상은 gcp2에서 생성된 기존 원본 재생을 재사용했다.
실패 직전202장은 native 입력이고, 이전 시각과 성공의2Hz 뷰는 저장 qpos/보정으로 재구성된 평가용 자기 뷰라는 한계가 있다. Mac에서는 파일 이미지만 읽었으며 화면 앱·물리·렌더를 실행하지 않았다.
실패의 처음·중간·끝을 포함한 자기 카메라 수백 장을 확인했다.

시간순: world10.9 lower 선택 → 13–14초 open/관측 준비 →16–20.5초 첫 panorama
→23–27.5초 두 번째 panorama →29.2초 남쪽30cm shift 선택 →33–35.5초 정렬/접근
→35.5–55.4초 재집기·자기 RGB 들기 확인 →55.5초 명령 전 sweep 거부.
마지막10초에는 큰 진동·벽 방향 이동을 관찰하지 못했다. 듬성한 프레임에서는
놓치기 쉬운 사실은 재집기 뒤 오랜 들기 확인 동안 빔이 화면을 거의 채운다는 점이다.
전체 재생 끝2.4초는 평가 안정 기록이라 사건 직전 띠와 구분했다.

원본 `map_backoff_checks`: r1의 북쪽 후퇴15/10/5cm는 전부 거부되어 제자리 유지,
r2만 남쪽15cm 후퇴했다. `lookaround`는 pan −60/0/+60도이며 몸 회전은 없었다.
따라서 이 사건에는 몸 회전 반경 계산이 적용되지 않는다. 거부된 sweep도 회전이
아닌 남쪽 이동이다. `release23.sweep`은 yaw가 있으면 별도 거부한다.

실패 r1 최종 자기 추정은(4.73618,1.24281,−1.52423), sigma xy≈0.050m,
기존 halo≈0.100m. 북벽과 추정 robot footprint만의 틈은+0.000718m,
halo 포함−0.099288m. 기존 검사는 시작점을 포함한 hull 때문에 벽에서 멀어지는
경로도 거부했다. 평가용 마지막 panorama 오차44.9mm는 원인 비교용일 뿐 제어에
넣지 않는다. 성공62회 중 이동 sweep이 있는46회의 북벽 최소 틈은
최소0.125382/p05 0.247810/중앙0.393690/p95 0.541571/최대0.548516m.
나머지16회는 이동 sweep이 없으므로 결측으로 둔다. 성공 최종124개 로봇 추정의
halo 포함 최소 틈은−0.052497m이다. 최종 틈과 이동 경로 틈은 서로 다른 모집단이다.
원본·재현 명령·저장 해시는 `baseline-audit.json`, `audit_baseline.py`에 있다.

## 후보와 상수 근거

기본 OFF `release_sweep_wall_aware=release_sweep_wall_aware_v1`은 기존 경로와
형상을 그대로 두고 **불확실성 범위에서 빠져나오는 병진 경로**만 별도 인증한다.
모든 로봇/자기 명령으로 만든 빔 가설/정적 장애물/지도 경계를 검사한다.
전체 명목 swept footprint가 엄격히 장애물 밖이고, 하나의 고정 분리 평면에서
각 명령 경계의 틈이 줄지 않고 끝점이 기존 halo 밖으로 나와야 한다.
고정 방향 병진은 경계 사이가 affine이므로 이 조건은 연속 구간에도 성립한다.
명목 충돌·벽 방향 이동·중간 역행·미완전 탈출·미확정 위치·회전은 계속 거부한다.
정답·평가 위치·파트너 위치/RGB를 읽지 않는다. 새 이동 후보나 근거리 파지 경로는 없다.

수치 상수/성공 한계를 새로 맞추지 않았다: robot0.18m, beam0.60×0.04m,
halo=max(0.02m,2sqrt(max eigenvalue(Pxy)))는 기존 release23 그대로다.
0은 기하 접촉 경계이며 여유를 줄이는 epsilon은 없다. 기존180SIM초와3회 보정은
유지한다. 계산은 발행 계획 길이×형상2개×지도 장애물 수×사각형 축4개 이내로
유한하며 wall 시간 제한을 사용하지 않는다. 불확실성 범위 안의 제어가 안전을
보장한다는 주장은 하지 않으며, 기존 release15의 단조 이탈 원칙을 whole-sweep과
끝점 여유 회복 조건으로 더 엄격하게 적용한 후보다.

## 참고 자료

- [Nav2 Spin::isCollisionFree](https://api.nav2.org/nav2-jazzy/html/spin_8cpp_source.html)
  — 실제 자기 pose에서 회전 전방 궤적을 유한 주기 수로 예측하고 footprint 충돌이면 정지.
  소스162–188행을 열람했다. 회전 각도 끝점만 확인하는 방법은 채택하지 않는다.
- [Nav2 FootprintCollisionChecker](https://github.com/ros-navigation/navigation2/blob/main/nav2_costmap_2d/src/footprint_collision_checker.cpp)
  — 지도에 footprint를 옮겨 변의 충돌 비용을 검사하는 표준 구현을 열람했다.
  본 후보는 점·중심만 검사하지 않고 convex whole sweep을 유지한다.
- [Nav2 Behavior Server](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/configuring_behavior_server/)
  — BackUp/Spin과 simulate-ahead 설정을 확인했다. 대안 방향 선택은 가능한 표준 방법이나,
  이 시드에서는 후퇴가 이미 차단되고 기존 이동이 벽 반대여서 경로 탐색 추가는 불필요하다.

Nav2 문서의 속도·2초 기본값은 우리 상수 근거로 가져오지 않았다. 불확실성 단조 이탈은
위 표준 footprint 원리와 저장 원본/기존 release15에 따른 본 프로젝트 적용이며 문헌의
직접 보장으로 표현하지 않는다.

## 검증과 잔여 작업

Mac 비물리 단위검사: release25/23/24 **39 passed**. 명목 겹침, 벽쪽/중간 역행,
탈출 부족, 중간 장애물, 회전, 위치 미확정 반례와 기존 기본 OFF 회귀를 포함한다.
run-first:110633 A/B + 이전 성공4개(A/B 혼합). 최대3라운드 뒤 통과한 고정 소스로
gate80을 처음부터 실행한다. 결과와 입력 감사·cap_end·HOST_ERROR·funnel은 후속 파일에 기록한다.


## run-first 1라운드

실행 소스 `08cf9d0ab69c47a2f4b61ffdeeb9c197f933a019`: A3/3·B3/3,
cap_end/HOST_ERROR/감독중단0. 저장 qpos의 mj_forward 평가 재계수와 입력 감사
6/6 0/0/top0, 명목 최종 조건·2초 안정 모두 통과. 1835파일 저장/복호화 SHA 불일치0,
오수용0. 네 입력 모집단은 native617장/선 후보193/들기16/위치 fit56으로 분리했다.
첫30SIM초 wall/SIM 중앙4.004159. 원본은 gcp2 `runs/release25-short-*-08cf9d0a/raw`.

110633은 A/B 모두 끝까지 통과했다. A는 기존−0.099288m를 그대로 남기고
nominal+0.000718m·끝점 halo 밖+0.202244m를 인증했다(B끝점+0.206132m).
기존 중단 지점까지 A/B의 로봇별 명령 원본454/438행은 바이트 동일,
저장 자기 카메라180/180 SHA 일치(`110633-before-fix-equivalence.json`).
이후 실행은 새 인증에 따라 이어지므로 전체 궤적 동등성을 주장하지 않는다.

게이트 제출 전 원장 표시의 추가 반례를 고쳤다: 수용된 음수 틈이 다른 물체의
실제 거부를 가리지 않도록 terminal 사유는 거부된 검사 중 최악값을 고른다.
이 반례 포함 release25 비물리9 PASS, 기존 release23/24 31 PASS.
실행 경로의 수용/명령에는 변화가 없지만 새 고정 SHA에서2라운드를 다시 확인한다.
1라운드와2라운드는 합산하지 않는다.
