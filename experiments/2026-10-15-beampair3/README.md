# beampair3 — numpy 원장 직렬화 정지 수정

PR #522, `claude/beam-pair-teacher`, beampair2와 합산하지 않는 새 후보.

[수정 전 분포](baseline-rejections.json): 이전 40회 중 시작18, 정상성공14,
HOST_ERROR1, 동일 결함 감독중단3, 미제출22. peer_goal/r2 원장74건은
다른 모집단이고 직렬화 실패1건과 합산하지 않는다. 빈 사유를 성공으로 간주하지 않는다.

원본 stack은 고정 의존성 runner의 `diagnostic-snapshot.json` write에서 numpy bool을
거부하고 예외 처리 `result.json`도 같은 값으로 실패했다. 공통 strict NumPy encoder로
bool/int/float/ndarray를 JSON 수치/배열로 변환한다. 공통 atomic write, pinned runner의
JSON·JSONL, adapter 결과·명령 원장에 적용하며 pinned 소스는 수정하지 않는다.
NaN/Inf·지원되지 않는 객체는 계속 거부한다. 모듈 바인딩은 예외에도 복원한다.
실행 전 모든 기록 경로에 중첩 NumPy 값을 쓰는 비물리 단위시험을 포함한다.

[원본 영상 직접 검토](original-visual-review.json): 실패8318611 0–19초(전체39·끝101프레임),
성공8318604 0–48.6초(전체99·끝101프레임), 각 개요+r1+r2.
MP4 3배속·각8MB 이하, GCP에서 생성 후 Mac 지정 playback 폴더에 회수했다.
원래 자기 JPEG는1Hz라 원본10Hz 평가 qpos를 렌더링하고 camera-runtime 보정을 복원했다.
위치 차이0, 물리·교사 재실행/보간 없음. 평가용 개요는 제어기에 연결하지 않는다.
실패의 배정은r1=blue/r2=teal로 다르고 자기 관측 band도 배정색이다.
근접은 사실이나19초에 정지하여 단순 통과의 완결은 아직 확인하지 않았다.

[짧은 탐색](probe-plan.json): 8318611·8318604 먼저, 성공8318600/01/02/03,
기존 고정 장면을 유지하고 r1 교란12/5/1/3/8/10틱을 분산한다. 최대3라운드,
첫 seed 성공 뒤 나머지5, 호스트 합계40 이하. 학습카메라off, held 숨김on,
weld off. 계산량 예산 search24_checks_v1/search25_checks_v1를 계속 켜고
60 SIM초 상한·기존 판정 상수를 변경하지 않는다. 새 수용 상수는 없다.
6/6이면8318611·8318604를 앞에 둔 별도40회 대기열만 준비한다.

R1은 첫 sentinel의 교란 길이가 원본12와 다른1틱인 계획 오류로 감독 중단했다.
원본을 보존하고 R2에서는8318611=12,8318604=5틱을 원 관문 그대로 둔다.
이 중단을 교사 물리 실패나 R2 성공률에 합산하지 않는다.
