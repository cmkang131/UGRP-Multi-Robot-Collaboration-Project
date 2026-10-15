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
`harness/grasp_act_visible_world.py:75-77`이 적용한다(고정 의존성 SHA 기준).
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
현재 상태는 후보 검증 전 NOT_READY다. 관련 비물리24개 PASS; 물리 성공은 아직 미측정이다.

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
