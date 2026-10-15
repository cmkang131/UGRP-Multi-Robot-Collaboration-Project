# beampair7 — 새 장면의 빔 짝 접근 교착

기반 `0b5faa4cfdc52f87df0fdf49e7b254bafc5b8bc0`, 고정 교사 의존성
`26f84d0f0ada1c33473c83cca2d3415ce51bd247`. gcp2/C MuJoCo CPU만 쓴다.
장면은 PR #527 `a68106fd`의 `walls_floor_contrast_v5_indigo110_s80`, 원본 v1 바닥,
`no_mip_v1`. 학습·학생·모델·weld OFF, held 숨김 ON. release 작업의 소스/프로세스는 건드리지 않는다.

## 수정 전 근거

[거부·관문 표](rejection_table-before.json), [성공15 대 실패1 분포](before-distribution.json).
성공의 peer_goal 수는 `[0,0,78,0,0,0,0,55,0,0,0,0,0,0,0]`, 실패는85다.
성공8318701의 blocker=r2 78회, 성공8318706=r3 55회, 실패8318711=r1 85회다.
peer_goal이 많다는 사실 자체는 실패 원인이 아니다. 원본15/16·cap_end1·미제출24는 별도 결과다.

[직접 영상 열람](visual-review-before.json): 실패8318711 전체0–59.9 SIM초 2Hz121장,
마지막49.9–59.9초 10Hz101시점(자기 원촬영202장), 원래 자기 카메라0/12/24/35/47/59초도 보았다.
성공8318726은 동일 소스·장면의 선행 실행 전체0–38초 2Hz77장이다.
개요는 평가 전용 saved-qpos 재구성이고, 자기 화면의 실패 마지막10초 이외는 실제 어안/카메라 보정을 적용한 재렌더다.
영상은 각각631715/271904B, ffprobe만 확인했다. Mac GUI·물리·렌더0.
8–18초 서로 반대 끝으로 가는 경로가 만난 뒤18–24초 청록 끝 쪽에서 두 차체가 붙는다.
r1 blue/r2 teal로 맡은 끝은 다르다. 24초 이후 r1은 r2 몸체에 시야가 가리고 r2는 청록을 보며 접근 명령을 반복한다.
10Hz에서는 완전 정지처럼 보이는 중간에 짧은 팬·회전과 다시 가림이 반복되는 것이 보인다. READY/pick 없음.

[허용 입력 재구성](allowed-world-summary.json), 재현은 [GCP 분석 스크립트](operations/replay_observations.py).
`sim/grasp_act_search23.py:23`의 `PEER_TTL_S=2.0`을
`harness/grasp_act_visible_world.py:67-69`이 적용한다(고정 의존성 SHA 기준).
마지막 신선한 상대 관측은 r1=15.9초, r2=12.1초이고 모델의 상대는 각각17.8/14.1초까지만 남았다.
그 뒤 새 관측 없이 상대가 모델에서 사라진다. `grasp_act_peer_rendezvous.PeerRendezvous.retry()`는
12초 재시도에서 peer_wait_ids를 지우고, `_peer_route()`는 상대가 없는 제약으로 접근을 다시 허용한다.
원본 평가 거리와 영상은 약20초부터 차체 간0.15–0.20m에 갇힌 것을 확인한다.
발행 명령 적분은 실제 진행이 아니므로 이후 목표 오차 감소로 이 교착을 검출하지 못한다.
이것은 TTL→빈 피어 모델→접근 재개라는 코드/기록 연결이며 새 장면의 색 검출 회귀로 확대하지 않는다.

## 후보와 상수

기본 off `beampair_peer_yield_v1`: 파랑 담당이 현재 자기 카메라에 보이는 빔에서 계산한 청록의
명목 파지 자리를 먼저 비워 둔다. 그 자리를 기존 A*·전체 경로·실제 명령 검사에 추가 정적 예약 disc로 넘긴다.
관측에서 사라진 로봇 위치를 현재 좌표로 되살리지 않고, 고정 작업의 목적 자세를 예약한다.
신선한 자기 끝 band≥5(기존 기준)가 있을 때만 빔 형상을 읽는다. 보이지 않을 때와 pick/complete는 비활성이다.
청록 담당은 원래 동작을 유지한다. 통신·피어 내부 상태·세계 정답·관절·접촉 입력을 추가하지 않는다.

새 판정 상수는 없다. 목적 자세는 기존 `STATION_M=.203m`, 예약 반경은 기존
`visible_route.constraints`의 피어 `.17 + (.17-own_radius)`를 그대로 쓴다.
own_radius=.13(접음)/.17(펼침)이므로 합산 간격은 기존 .34m다. 시간 상한60초와 모든 성공 조건은 불변이다.
blue가 양보하는 순서는 기존 `grasp_act_priority`의 blue-parks/teal-first와 같다.
예약은 여유를 줄이지 않고 추가 제약만 만든다. 예약 상태 표는 실제 피어 거부/후보 수와 다른 모집단으로 기록한다.

## 실행 계획과 범위

최대3라운드, 각 라운드는 실패8318711 먼저 직렬 확인 후 성공8318701/8318706/8318700/8318726 네 개.
같은 소스5/5 원본 재계수 뒤에만 새로운 gate40을 승인한다. gate40은8318711 먼저,16동시,
`APPROVED_PINNED`, `review_detail="REVIEW_SKIPPED_BY_USER (10/15 run-first rule)"`,
절대경로 rejection_table/해시를 필수로 둔다. 과거15/16·짧은5개와 합산하지 않는다.
첫30 SIM초 wall/SIM은 기록하며 중앙>3.5 경고,>6.0 또는 HOST_ERROR는 새 제출을 중단한다.
실패/감독 중단 직전10초 자기 카메라10Hz 링은 기존 기록 전용 옵션을 켠다.
실행 제어 소스는 `ef284e92510ca4283f1db5de9aecd1dac5c17b0b`로 고정했다. 관련 비물리24개 PASS, 후속 대기열 행 단위 검증7개 PASS(이 중 기존4개 중복). 후속 기록/CI 커밋은 제어 파일을 바꾸지 않는다.

원본/분석은 `/home/ugrp/ugrp-sim/ops-reviews/beampair7/`, 새 실행은
`/home/ugrp/ugrp-sim/runs/beampair7-*`. Mac에는 요약·몽타주·검토용 작은 영상만 회수한다.
임대·합계≤40·8h 명령 상한·비용/유휴 정지 장치를 유지하고 다른 임대가 있으면 VM을 정지하지 않는다.

## 참고 자료

- [Silver, Cooperative Pathfinding (2005)](https://ojs.aaai.org/index.php/AIIDE/article/view/18726):
  예약 표를 통한 분리된 경로 계획. 이 후보는 현재 보이는 빔의 고정 목적 자세만 예약하며 공유 경로·완전한 시공간 CA*는 구현하지 않는다.
- [Okumura et al., PIBT (IJCAI 2019)](https://www.ijcai.org/proceedings/2019/76):
  우선순위·상속·되돌리기로 교착을 다룬다. 이 후보는 end별 고정 우선순위만 쓰며 PIBT의 완전성 정리는 적용하지 않는다.
- [van den Berg et al., ORCA](https://gamma-web.iacs.umd.edu/ORCA/):
  상대 속도와 상호 충돌 회피 책임을 쓰는 표준 대안이다. 원본처럼 상대 관측 자체가 사라지는 경우를
  속도 최적화만으로 해결했다고 주장할 수 없어 이번 후보에서는 도입하지 않았다.

## R1 짧은 검증 — 5/5

[원본 재계수](r1-summary.json) · [거부/관문 표](r1-rejection_table.json) · [실제 장면/첫30초](r1-runtime-verification.json).

|seed|공동3초 유지 성공|SIM초|
|---:|---:|---:|
|8318711|1/1|46.4|
|8318701|1/1|56.7|
|8318706|1/1|36.5|
|8318700|1/1|27.0|
|8318726|1/1|37.9|

cap_end0·HOST_ERROR0·미시작0, invisible_measurements0·held_world_reads0, 빈 거부 사유/이름/틈 감사0이다.
첫30초가 있는4개의 wall/SIM 중앙3.911, 최대4.439로3.5 경고이며6.0 차단 미만이다.
모두 확정 장면·no_mip의 실제 GL_LINEAR를 확인했다. 이5개는 gate40에 합산하지 않는다.

[8318711 대표 영상](representative-8318711.mp4) 390806B. 전체0–46.4 SIM초2Hz94시점을 직접 보았다.
8–18초 파랑 담당이 청록 예약 자리를 돌아 나가고, 18–30초 청록이 정렬하는 동안 파랑은 반대 끝으로 이동한다.
30–38초 파랑 정렬, 38초 이후 양측 READY→pick→명령 완료→공동3초 유지다. 지속적인 차체 교착이 사라졌다.
자기 화면도 저장 qpos 재렌더이며 성공 원촬영10Hz로 주장하지 않는다. [범위/ffprobe/해시](playback-short-summary.json).

[gate40 승인 원본](gate40-queue-r1.json), [용량 대기 후 재제출](gate40-queue-r1-attempt2.json).
APPROVED_PINNED와 지정 review_detail, 동일 소스의 절대 rejection_table/해시를 연결했다.
첫 제출은 다른 임대40 때문에 물리 시작0으로 거부됐다. 이후 다른 작업이 임대를 해제하여 다른24+자기16=40을 확인한 뒤 실제 첫16개를 시작했다.
감독기 사전 오류의 pending 목록에서는 sentinel 한 개가 빠졌지만, 실행 폴더·PROCESS가0인 것으로40개 전부 미제출임을 별도 재구성한다.
최종 모집단은 새 gate40만이며 진행 중 결과는 완료/READY로 보고하지 않는다. 운영 오류는 [별도 원장](operations-errors.json)에 있다.

## R1 gate 감독 중단 — NOT_READY

[새 원본 재계수](gate-r1-summary.json), [거부/관문 표](gate-r1-rejection_table.json).
새 소스 gate는32개 시작 중 성공16, 실제 terminal 실패1(8318728), 감독 중단15, 미제출8이다.
cap_end0·HOST_ERROR0. 완료 입력 감사는17개까지이며15개 중단은 완료 감사로 올리지 않는다.
첫16은16/16, 첫30초10개 중앙4.443으로6.0 차단 미만이었다. 기존0b5faa4c·짧은5개와 합산하지 않는다.
8318723은 감독 SIGINT 뒤 렌더러 finalizer가3분 이상 멈춰 소유 PID/명령과 interrupted 원본을 확인하고 파일 해시를 남긴 뒤 해당 그룹에만 SIGTERM을 보냈다. 부분 raw와 미완 adapter 상태를 보존했다.

새 실패8318728 전체0–9.9초2Hz21장과10Hz100시점(자기 원촬영200장)을 직접 봤다. r1 blue는 파랑을 보면서 출발하지 못하고, r2 teal은 접근/대기/팬을 한다. 원래8318711의 차체 교착과 다르다. [영상 근거](playback-gate-r1-8318728.json).
r1은 예약 원 안쪽0.235m에서 시작하고61회 예약 쿼리 내내 머문다. 원래 search17.nearest_free의20cm 탐색과 search18.exact_start_path의3×3 주변5cm 연결점이 예약 밖 free cell에 닿지 않아 planner6/6 no_path,6초 무진행으로 핸드오프한다.

## R2 시작 연결점 수정

동일 기본 off 토글에 새 소스 후보로 넣는다. 원래 A*가 실패하고 자기 시작이 추가 예약 안쪽인 경우에만 가상 시작 연결점을 추가한다.
격자는 기존 exact_start_path의0.05m를 유지하고, 탐색 반경/검사 수는 예약 반경+own radius+시작에서 예약 중심까지 거리와 격자 반올림1칸으로 계산한다(삼각부등식). 수용 여유와 시간 상한은 바꾸지 않는다.
기존 free와 strict continuous segment 검사로 원·물체·벽을 전부 보존한 첫 안전 연결점을 고른 뒤 원래 유한 A*로 이어 간다. 이어지는 경로가 없으면 그 연결점을 재선택 목록에서 제외한다.
새 검사는 격자 후보 수와 최대 두 번의 원래40000노드 A*로 유한하다. 후보의 이름/최소 틈과 bounds→endpoint→connector, connector→continuation 관문을 각각 남긴다.
이 방식은 원래5cm 시작 그래프와 안전한 margin escape를 연결하며, Nav2의 시작 셀 처리 필요성도 참고했다. [Navfn clearRobotCell 공식 소스](https://github.com/ros-navigation/navigation2/blob/main/nav2_navfn_planner/src/navfn_planner.cpp). 시작 셀/물리 장애물을 지우지는 않는다.
R2 짧은5개는8318711→8318728을 직렬 선행하고 성공8318701/8318706/8318726을 뒤따른다. gate는 두 실패 시드를 앞에 둔다. 실패 시 새 제출을 멈추되 이미 도는 유한 실행은 자기 상한까지 기록하게 하여 중단 finalizer 교착과 불필요한 미완 결과를 줄인다.
