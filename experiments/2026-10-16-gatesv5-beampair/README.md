# gatesv5 빔 짝 관문 — NOT_READY

확정 장면의 정답 교사 관문이다. 소스 `0b5faa4cfdc52f87df0fdf49e7b254bafc5b8bc0`, 고정 의존성 `26f84d0f0ada1c33473c83cca2d3415ce51bd247`. gcp2 `n4-highcpu-64`, C MuJoCo3.12.0, `walls_floor_contrast_v5_indigo110_s80` + 원본 v1 바닥 + `no_mip_v1`. `beampair_gate_valid_v2`, `beampair_wall_clear_v1`, 접근v2·피어v2·held-hidden을 켰고 경계 검출/학습/weld는 OFF다. 원래 기본값은 유지한다.

짧은6회는6/6 통과했다. 새 gate40은16회 시작 후 성공15·cap_end1·HOST_ERROR0, 나머지24회는 감독 중단 규칙으로 미제출이다. 성공38/40을 입증하지 못해 NOT_READY다. 이전 장면·gcp1·짧은6회를 합산하지 않는다. 장면 연결 최초6건 HOST_ERROR는 별도 원장에 있다.

|관문|통과|거부/미제출|
|---|---:|---:|
|새 계획40 중 시작|16|24 미제출|
|양측 align|15|1|
|양측 READY|15|0|
|양측 pick·명령완료|15|0|
|공동3초 유지·입력적합|15|0|

[요약](summary.json), 관문·후보·프레임·이벤트 표 `beampair-gate-rejection_table.json`(큰 파일은 `.zst`, 압축 메타데이터의 원문 해시), 모든16개 원본별 해시·판정은 `beampair-gate-summary.json`에 있다. raw/adapter1,745파일 검증, invisible_measurements=0·held_world_reads=0. 첫30SIM초 중앙4.015925(n11; 성공5회는30초 이전 종료),6.0 차단 기준 이내다. 첫16회 자기 RGB와 GO/ACK·명령 이력을 점검했다.

8318711(r1 blue/r2 teal)은 접근 교착 후60SIM초 상한 종료다. 전체0–59.9초2Hz와49.9–59.9초10Hz를 직접 봤다. 마지막10초 자기 원본202장, saved-qpos 재구성 몸체 오차0. 20–60초 두 활성 로봇 기준점 간 거리0.154877–0.198977m, 마지막40초 r1은322/400틱·r2는400/400틱 이동 명령을 냈지만 양측 align에 닿지 못했다. r1 시야의 피어 가림과 반복 탐색은 확인했다. 경로/발행 명령 기반 위치 추정/피어 대기 중 근본 코드 원인은 미분리이며 벽/바닥 색 검출 회귀는 입증하지 않았다. 근거 없는 상수·시간 상한 변경과 잔여 채우기는 하지 않았다.

[실패3배속](representative-failure.mp4)(631715B), [성공8318726 3배속](representative-success.mp4)(271904B), [시간순 검토](visual-review.json). 개요는 평가 전용, 앞 구간 자기 화면은 저장 qpos·실제 카메라 보정/어안/그룹 마스크를 적용한 재렌더이고 실패 마지막10초는 원촬영이다. 예비 재생기의 어안 누락은 고친 별도 파일로 다시 확인했다. ffprobe만 사용했고 Mac 화면 앱·물리·렌더는0이다.

장면은12개 짧은 실행에서 실제 GL_LINEAR 및 v1 바닥 일치를 확인했다. 빔 짝 이전 gcp2 장면과 선택 물리 배열은 전부 동일했다(정적 배열 비교 범위). PR527 원본 질감/장면 모듈을 사용하고 고정 의존 경로에도 명시적으로 연결했다. 관련 비물리32개 PASS. 이 기록은 ACT 학생·배송·실물 성공을 검증하지 않는다.

원본은 gcp2 영속 디스크 `/home/ugrp/ugrp-sim/runs/gv5-beampair-gate-*-0b5faa4c/{raw,adapter}`. 별도 전체 raw 백업은 없다. 운영·분석·재현 명령은 `operations/`, 거부표의 reproduce 및 원본 PROCESS.json에 보존한다. 자기 빔 짝 실행과 임대는0이며 다른 임대와 release 운영을 보존했다.
