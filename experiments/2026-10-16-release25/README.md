# release25 — READY A40/40 B40/40

새 장면의 **내려놓기 교사 관문**을 통과했다. 실행 소스는
`8e81b7d96c0c73171635348c90631462adfe1eb0`, PR [#535](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/535),
기준점은 PR #491 최신 `7c752fcdef2627a6aedd3766346a1241a1788d7b`이다.
브랜치 `claude/release25`; 이후 기록·CI 목록 커밋은 실행 제어 모듈을 바꾸지 않았다.
**CI는 아래 4개 assertion 실패가 남아 있어 PR은 미병합이다.** 교사 관문 READY와 구분한다.

| 새 gate80 | 성공 | 실패 | cap_end | HOST_ERROR | 감독 중단 | 미제출 |
|---|---:|---:|---:|---:|---:|---:|
| A / release18 |40/40|0|0|0|0|0|
| B / release19 |40/40|0|0|0|0|0|

- gcp2 `n4-highcpu-64` / Xeon8581C / C MuJoCo3.12.0 CPU. 확정 장면
  `walls_floor_contrast_v5_indigo110_s80` + 원본 v1 바닥 + `no_mip_v1`,
  `release_geometry_v1`. 장면·바닥·GL_LINEAR 확인80/80, weldOFF.
- 입력 감사80/80: `invisible_measurements=0`, `held_world_reads=0`,
  `control_top_camera_reads=0`. 원본22,544파일 저장/복호화 SHA 불일치0, 오수용0.
- 저장 evaluator qpos/contact를 `mj_forward`로 재계수했다. 물리 step 재실행은 없다.
  구역 적합·바닥·기울기·비접촉·개방 명령·집게 거리와 안정 조건80/80 통과,
  마지막25개 샘플 모두 통과(시간 범위2.4SIM초). 종료 코드80/80이0이다.
- 첫16개 첫30SIM초 wall/SIM 중앙4.285490, 전체80개 첫30SIM초 중앙4.748040.
  경고 기준3.5 초과, 차단 기준6.0 이내. 첫16개도 본관문에 포함되며 별도 속도 실행은 없다.
- 최대16동시, 공유 호스트 입장 시 예약·실제 worker 합계40 이하를 검사했다.
  110633 A/B →88639 A/B →110622 A/B 순으로 우선 제출했다.
- 학습 RGB·프로젝트 모델 호출0, ACT 학생 실행0, Mac 물리·렌더·GUI0.
  이전 a41781dd A31/40·B31/40, 짧은 실행, 다른 호스트·장면·A/B는 합산하지 않았다.

## 원인과 영상 확인

수정 전에 [거부 사유 표](baseline-rejection_table.json)를 만들었다. 기존 최종78회는
성공62·실패1·감독 중단15, 미제출2였다. `static_sweep`2건은 A실패와 B감독 중단의
같은110633 결함이다. 실행 예외15와 복구된 FOV 거부3은 별도 범주다.
[분포·원본 SHA](baseline-audit.json), [분포 요약](baseline-distribution-summary.json).

처음 내려놓기는 지도 위치 미확정 상태에서
`PairReleaseCode.decide(require_seen=False)`가 현 위치를 선택했다.
이후 자기 RGB로 위치를 잡았다. r1은 북쪽 후퇴15/10/5cm를 모두 거부해 제자리에 있었고,
r2만 남쪽15cm 후퇴했다. 둘러보기는 pan−60/0/+60도였으며 몸 회전은 없었다.
재집기 뒤 선택한 이동은 **북벽에서 멀어지는 남쪽30cm**였다.

기존 sweep은 시작점을 포함한 convex hull 전체에 양의 halo 여유를 요구했다.
r1 자기 추정(4.73618,1.24281,−1.52423), sigma≈0.05m에서 halo≈0.100007m이고,
시작 robot footprint의 북벽 틈은 halo 제외+0.000718m, 포함−0.099288m였다.
그래서 멀어지는 경로도 명령 전에 거부됐다. 이는 추정 불확실성 범위의 겹침이다.
성공62회 중 이동 sweep이 있는46회의 북벽 최소 틈은 최소0.125382/중앙0.393690/
최대0.548516m였다. 나머지16회는 sweep이 없어 결측이다. 최종 추정 틈과 이동 틈은
다른 모집단이며 성공 최종124개 로봇의 halo 포함 최소 틈은−0.052497m였다.

북벽 안쪽 면 y=1.425m와 추정 중심 거리0.182190m에 비해 기존16각형 footprint의
전체 회전 반경0.183526m+halo0.100007m는0.283533m다. 완전한 몸 회전을 가정하면
여유−0.101343m이므로 새 회전 허용을 넣지 않았다([계산](rotation-diagnostic.json)).

실패 A110633 전체0–56.1SIM초2Hz, 실패 사건 직전 world45.5–55.5초의 native 자기 RGB
10Hz202장을 직접 보았다. 초기/중간/끝 native1Hz 입력도 로봇별6장씩 확인했다.
성공 B110600 전체0–32.2초2Hz도 확인했다. 시간순으로 내려놓기→두 번의 panorama→
정렬/접근→재집기·긴 들기 확인→55.5초 sweep 거부였다. 마지막10초에서 큰 진동이나
북벽 방향 이동은 관찰하지 못했다. 듬성한 프레임에서 놓치기 쉬운 부분은 들기 확인 동안
두 자기 카메라를 빔이 거의 채운다는 점이다. 전체 재생 끝2.4초는 평가 안정 기록이다.
[직접 검토 범위·타임라인](visual-review.json), [회수 SHA/ffprobe](baseline-playback-verification.json).

새 gate110633 A는 같은55.5초 위치에서 이탈을 인증하고 남쪽 이동→재내려놓기→
panorama→집게 후퇴·종료까지 이어졌다. 전체0–81.1SIM초2Hz를 직접 확인했다.
[대표3배속 영상](representative.mp4)(442,555바이트·ffprobe 통과),
[직접 검토·원본 해시](gate-110633-visual-review.json).
고속 실패 tail 밖의 자기 뷰는 저장 qpos/원래 카메라 보정의 평가용 재구성이며,
native 고속 입력이라고 표현하지 않는다. 재생 bodyXYZ 오차0, 제어/물리 재실행0이다.

## 수정과 상수 근거

기본OFF `release_sweep_wall_aware=release_sweep_wall_aware_v1`을 새 후보에서만 켰다.
정적 지도·자기 RGB 추정 위치·자기 발행 명령 FK만 사용한다. 조건은 다음과 같다.

1. 두 로봇과 각자의 빔 가설의 **명목 whole swept footprint**가 모든 정적 장애물·경계 밖이다.
2. 이미 halo가 겹친 면에서는 하나의 고정 분리 평면으로 모든 명령 경계의 틈이 줄지 않는다.
3. 끝점은 기존 halo 밖으로 나온다. 고정 방향 병진의 경계 사이가 affine이므로 연속 구간에도 성립한다.
4. 명목 충돌·벽쪽/중간 역행·새 장애물 진입·탈출 부족·위치 미확정·회전은 계속 거부한다.

robot0.18m, beam0.60×0.04m, halo=max(0.02m,2sqrt(max eigenvalue(Pxy)))는
기존 release23 그대로다. 새 수치 허용 오차는 없고0은 기하 접촉 경계다.
180SIM초·3회 보정·성공 한계·카메라·물리·근거리 파지 경로도 유지했다.
계산은 발행 계획 길이×형상2개×지도 장애물 수×사각형 축으로 유한하며 wall 시한은 없다.
불확실성 범위 안의 이동이 실제 안전을 보장한다는 주장은 하지 않는다.
기존 [release15의 단조 이탈](../../sim/release15.py)을 whole-sweep·끝점 회복 조건으로 제한한 후보다.
수용된 음수 틈이 다른 물체의 거부를 가리지 않도록 terminal 사유는 거부된 검사 중 최악값을 고른다.

## run-first·승인·재현 기록

| 구분 | 실행 SHA | A | B | 원본 해시 불일치/오수용 |
|---|---|---:|---:|---:|
| 1라운드 |08cf9d0ab69c47a2f4b61ffdeeb9c197f933a019|3/3|3/3|0/0|
| 2라운드 |8e81b7d96c0c73171635348c90631462adfe1eb0|3/3|3/3|0/0|
| 새 gate80 |8e81b7d96c0c73171635348c90631462adfe1eb0|40/40|40/40|0/0|

1라운드 후 원장 물체명 우선순위 반례만 보완하고2라운드를 다시 확인했다.
최대3라운드 중2라운드 사용. 각 라운드는 별도이며 입력 감사도 각각6/6 0/0/top0이다.
1라운드110633의 옛 중단 지점까지 로봇별 명령454/438행과 자기 카메라180장은
원본과 바이트/SHA가 일치했다([비교](110633-before-fix-equivalence.json)).
이후 전체 궤적 동등성을 주장하지 않는다.

[gate-config.json](gate-config.json)에2라운드 `rejection_table` 절대경로와 SHA를 연결하고,
`review_detail="REVIEW_SKIPPED_BY_USER (10/15 run-first rule)"`,
`status="APPROVED_PINNED"`로 승인했다. 독립 코드 검토 완료를 뜻하지 않는다.
[최종 요약](summary.json), [원본 재계수](gate-summary.json), [거부·사례 funnel](gate-rejection_table.json),
[프레임·이벤트 모집단](gate-population-funnels.json), [후보·fit funnel](gate-candidate-funnels.json).
새 관문의 native 입력7536장·선 후보2478개·들기186회·fit692회는 각각 별도 모집단이다.
기록되지 않은 optimizer 중간 생존 수는 추정하지 않았다.

원본은 gcp2 `/home/ugrp/ugrp-sim/runs/release25-*/raw`, 분석은
`/home/ugrp/ugrp-sim/ops-reviews/release25/`이다. Mac에는 요약·몽타주·실패 프레임·작은 영상만 회수했다.
[회수 SHA](gate-retrieval-verification.json), [실제 소스·환경](runtime-verification.json),
[정리·공유 호스트 보존](cleanup.json). raw는 gcp2 영속디스크에 보존했으며 독립 전체 백업은 아니다.

```sh
# gcp2; 물리 step 없이 저장 원본 재계수
/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release25/analyze_release.py /home/ugrp/ugrp-sim/ops-reviews/release25/gate-config.json
/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release25/release_candidate_funnel.py /home/ugrp/ugrp-sim/ops-reviews/release25/gate-config.json
```

## 코드 검사와 CI 잔여 문제

관련 비물리 release25/23/24 **40 PASS**, CI 목록/분할 검사 **68 PASS**.
새 회귀3파일을 CI 목록에도 등록했다. 명목 겹침·벽쪽 이동·중간 역행·중간 장애물·탈출 부족·
회전·위치 미확정·다른 거부 물체명 은폐 반례와 기본OFF 동등성을 포함한다.

CI run [38806760928](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/38806760928)는
3개 shard의4개 assertion이 실패했다. 등록 파일/교사 파일 보존 검사3개는 기준점7c752fcde에서도
같은 실패를 재현했다(비물리3 FAIL,6.56초). 나머지는 기존74963 위치 추정의 legacy-before 오차가
0.426748m라 진단용 `>0.5m` assertion이 실패한 CI-only 사례다. 해당 소스·시험·fixture는
기준점과 바이트가 같으며, 기준점의 단독 Mac 검사는1 PASS였다. 플랫폼/순서 원인은 미분리다.
봉인 해시·허용 오차를 완화하지 않았고 병합하지 않았다.
[정확한 실패·비교·로그 SHA](ci-findings.json). 이 문제는 교사 관문 성공과 별도로 남는다.

## 표준 방법 조사

- [Nav2 Spin::isCollisionFree](https://api.nav2.org/nav2-jazzy/html/spin_8cpp_source.html):
  162–188행을 열람했다. 추정 pose에서 유한 주기로 회전 궤적의 footprint를 검사한다.
  이 사건은 몸 회전이 없어 새 회전 계획기를 추가하지 않았다.
- [Nav2 FootprintCollisionChecker](https://github.com/ros-navigation/navigation2/blob/main/nav2_costmap_2d/src/footprint_collision_checker.cpp):
  지도상의 footprint 변을 검사하는 구현을 열람했다. 본 후보는 중심점 대신 기존 convex whole sweep을 유지한다.
- [Nav2 Behavior Server](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/configuring_behavior_server/):
  BackUp/Spin·simulate-ahead·대안 행동을 확인했다. 기존 경로가 이미 벽 반대이고 후퇴 후보는 차단되어
  새 방향 탐색은 추가하지 않았다. 문서의 속도/2초 기본값은 우리 상수로 가져오지 않았다.

단조 불확실성 이탈 인증은 표준 footprint 원리·원본 분포·기존 release15에 따른 본 프로젝트 적용이며,
Nav2가 이 후보의 안전성을 직접 보장한다고 표현하지 않는다. ACT 학생·새 장면 일반화·실물 검증은 별개다.
