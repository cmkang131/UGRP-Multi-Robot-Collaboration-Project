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
