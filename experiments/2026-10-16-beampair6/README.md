# beampair6 — v7 배치 분포에 맞춘 빔 짝 교사 gate

시작 `a9f87f3f`, PR #522. v7 원본은 PR #519의 `34e5deb40caa58317ae9ec5e9ac934c8cf09a941`.

평가 전용 전체 조사 결과 분기 **A**: s1–s8 중 s5에는 빔이 없고, 나머지 7개 빔의 14개 끝은 세 seed 모두 인증 자세91개가 전부 고정물과 충돌 없이 남는다(42/42끝=91). s2의 삽입 고정물 사건 뒤도 동일하다. 기존 gate40은80끝 중79끝=91,8318626 파랑만0이다. [배치 표](placement-validity.csv), [원본/해시](placement-validity.json), [수정 전 거부 표](rejection_table-before.json).

기본 off `beampair_gate_valid_v2`는 각 끝의 가능 자세 수≥k를 초기 배치에만 적용한다. k=91은 v7 관측 분포의 최솟값(0백분위)이다. 기존 인증 집합·5mm 기하 여유·차체와 실제 지도 고정물을 그대로 검사하며 정답 계산 결과는 제어 입력에 전달하지 않는다. 원래8318626 배치는 연구 배치 지원 범위 밖으로 남긴다. 새 시드는8318700–8318739로 분리한다. 이전 gate 및 gcp1과 합산하지 않는다.

서쪽 벽 기억 팽창은 기본 off `beampair_wall_clear_v1`을 함께 켠 후보로 검증한다. 이 후보는 보이는 광선의 hit/miss만 쓰며 실제 북쪽 벽을 지우지 않는다. held 숨김·weld OFF·카메라·성공 판정은 그대로다. 학습off.

시험은 새 생성기8318726→기존8318620을 직렬로 먼저, 성공8318600/04/11/31 네 개 이후, 최대3라운드. 같은 결함이 확인되면 즉시 중단한다. 6/6일 때만 새gate40을HOLD_SCENE·미승인·16동시·학습off로 만든다.

## 참고 자료

- [v7 장면 PR #519](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/519): s1–s8 원본8개를 해당 커밋에서 추출해 inputs-v7에 보존했다.
- [beampair5 전체 인증 자세 감사](../2026-10-16-beampair5/README.md): 8318626 실제 북쪽벽 침범10.27cm와 서쪽 기억 팽창을 분리했다.
- 고정 의존성 `26f84d0f`: `sim.grasp_act_search24.reachability_map`, `sim.grasp_act_search18.body_clearance`, `sim.grasp_act_search21.FRESH_MARGIN_M`. 추가 문헌이 필요한 파지 동작 변경은 분기A에서 하지 않는다.

## 영상 열람(수정 전)

파일로 직접 확인: 실패8318626 beampair4 R3 전체0–27.5SIM초2Hz56장,마지막17.5–27.5초10Hz101장; 성공8318604 전체0–48.6초2Hz99장. r1은0–5.2초청록에READY, r2는탐색→17.5–20.7초팬·후퇴→20.7–27.5초파랑을보며정지. 같은끝쟁탈·상호몸체막힘은보이지않는다. 10Hz에서팬과그뒤무이동이구분된다. 성공은각자다른끝에접근·정렬후약42초부터공동들기. 기존gcp2 ffmpeg 3배속 영상과프레임띠를사용했으며전체영상의검증은ffprobe만사용,Mac화면앱0. 성공카메라는qpos재렌더로원촬영10Hz가아니다.

## 최종 결과 — READY_HOLD_SCENE

실행 소스 `08f129213031255dd188e20df832bb6714dfca9a`, 생성기 소스 `7facb60b921e80831ad50a20a8ae2ee89d0d2b25`, 의존성 `26f84d0f0ada1c33473c83cca2d3415ce51bd247`.
[전체 요약](summary.json) · [거부/관문 표](rejection_table.json) · [배치 분포 표](placement-validity.md) · [원본 무결성](r1-integrity.json).

|R1 시드|결과|SIM초|
|---:|---|---:|
|8318726|공동 파지·3초 유지 성공|38.0|
|8318620|공동 파지·3초 유지 성공|55.8|
|8318600|공동 파지·3초 유지 성공|31.2|
|8318604|공동 파지·3초 유지 성공|48.3|
|8318611|공동 파지·3초 유지 성공|48.0|
|8318631|공동 파지·3초 유지 성공|27.9|

6/6 성공, 시작6·미시작0·HOST_ERROR0·cap_end0, R1만 실행했다(상한3라운드). 후보·프레임·프로토콜·에피소드 모집단은 섞지 않았고 각 관문표는 rejection_table에 연결했다. 에피소드 관문은 시작/양쪽정렬/READY/pick/명령완료/공동3초유지/입력적합 성공 모두6/6이다. 거부 원장의 blocker 발생은 peer_goal178·cargo_goal2이며 이름·최소 틈이 전부 기록됐다(복수 blocker 행은 독립 후보 수가 아니다). 원본 raw/adapter manifest에 등록된613파일를 확인했고, 회수20파일의 SHA256이 gcp2와 일치했다([회수 검증](retrieval-verified.json)).

`invisible_measurements=0`, `held_world_reads=0`; held 숨김은 실제 근접 명령 뒤 모든 실행에서80–106틱 측정되어 공허한 검사가 아니다. 학습·학생·LLM 호출0, weld OFF, 카메라·물리·성공 판정 불변. 마지막10SIM초10Hz 기록 링은 켜져 있고 제어 경로와 별개다. 이번6개는 모두 성공이므로 실패 tail 원촬영 새 보존은0이며, 성공 영상은 저장 qpos 재렌더다.

서쪽 기억 팽창의 기존 토글 `beampair_wall_clear_v1`을 켠 같은 후보로6개를 돌렸다. 이번에는12개 로봇 실행 모두 활성화 조건(전부 blocked_goal)에 닿지 않았다. 따라서 벽 clearing의 새 물리 검증을 주장하지 않는다. beampair5의 가시 hit/miss 검증과 북쪽 실제 벽을 보존한 결과는 이전 기록으로 별도 남긴다. 원래8318626을 옮겨 같은 시드 성공으로 바꾸거나 벽을 삭제하지 않았다.

[첫30초 원본 점검](r1-first30.json):30초 이상 실행5개는 모두600명령, 예산 종류checks600회, wall/SIM3.360–3.751(중앙3.468). 8318631은27.9초에 성공해30초 구간이 없다(560명령). 모델/프롬프트/토큰0이므로 동일 교사 기준의 모델 비용도0이다. 이 값은 직렬 선행2개와 후속4개 부하이며16동시 처리량 검증이 아니다. VM scheduling은24h로 확인했고 이번 명령은8h cap이다. 기존 VM 가드는 바꾸지 않았다.

[gate40 큐](gate40-queue.json)는 새 생성기8318700–8318739만 사용하며8318726이 맨 앞이다. **HOLD_SCENE·ready=false·approved=false·submitted=false**,16동시·학습off, 절대경로 rejection_table과 해시가 존재한다. 관문 측정0/40이다. 장면 승인·조정자 pin·16동시 첫30초·VM 상한 재확인이 남아 있다. v1 gate·이전 교사·gcp1 결과·이번 짧은6개를 정식40회와 합치지 않는다.

새 대표 성공 영상은[8318726 3배속](representative-8318726.mp4),284710bytes. 전체0–38초2Hz77프레임을 직접 봤다. 각자다른끝으로접근→정렬/대기→30초이후공동파지·완료이며같은끝쟁탈·상호막힘이보이지않는다. [검토 범위](playback-review.json), [ffprobe 확인](ffprobe-checks.json). Mac 화면 앱·물리·렌더0. 학생·운반·놓기·실물 성공은 미검증이다.

관련 비물리8개 PASS(기존 기본off 계획·거부표 완전동일 포함), diff 공백검사PASS. 초기 운영 오류2건(증분 bundle 기준 누락·분석용 Python 환경 오선택)은 물리 미시작이고[별도 원장](operations-errors.json)에 보존했다.

원본은 `/home/ugrp/ugrp-sim/runs/beampair6-r1-08f12921/round/diagnostic/episode-000..005/`의 raw/adapter, 분석은 `/home/ugrp/ugrp-sim/ops-reviews/beampair6/`다. gcp2 영속 디스크 보존이며 별도 raw 백업은 아니다.

자기 활성 실행0과 회수20SHA 일치를 확인하고 자기 임대를 해제했다([임대 기록](lease-released.json)). 다른 임대 `simalt5.json`·`scenetex4.json`이 있어 VM은 정지하지 않았고 [gcloud 최종 상태](vm-final.json)는RUNNING이다.
