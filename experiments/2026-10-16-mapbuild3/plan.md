# mapbuild3 사전 기록

ownership-ack: 2026-10-16 agent-ownership.md를 읽음. gcp5 L4 단독, gcp2 CPU lease 공유. 시작 겹침 검사 새 모듈·지도 코드만 소유한다. 공용 backend/장면/타작업 코드 수정 금지.

- 기존 drivecheck PR564의 초기 차체–cargo_box_00 관통 15.3449mm를 재확인하고 먼저 거부 분포표를 저장한다. 기존 장면 파일을 수정하지 않고 새 fixture에서 로봇의 시작 배치만 유효하게 선택한다. 허용 관통 깊이0: MuJoCo signed contact distance의 기하학적 경계. margin/solimp는 접촉 포함/힘의 매개변수이지 초기 관통 허용치가 아니다(공식 computation/contact 문서).
- 기본 off `spawn_overlap_check_v1`, 새 후보에서 명시적으로 켠다. 로봇↔비바닥, 화물↔화물, 화물↔벽을 검사하고 이름·깊이·최소 contact gap·사유를 남긴다. 바닥은 명시 이름 집합만 제외한다. 비접촉 쌍의 미측정 간격은 명시한다.
- 읽기 전용 기존 ACT16w 기록40/최종heldout40, warp8 beam40/release A40 B40의 원본 초기 상태·고정 시드 목록을 감사한다. CPU mj_forward는 상태 검사만이며 CPU integration0. 유효 초기 상태가 보존되지 않았다면 새로 복원한 상태와 원본 증거를 구분한다. 남의 코드·결과를 변경하지 않는다. 겹침 발견 즉시 공용 ops-alert에 한 줄.
- MJWarp(gcp5 g2-standard-8/L4), 장면/원래 카메라·FOV·물리·질감·NoSlip10 불변. 기본4 SIM초 FOLDED/HIGH closed, 초음파OFF만. v122 동일100/60/100ms 펄스·정지 구간별 실제/예측 비율. 이전 mapbuild 결과와 합산 금지. HIGH는 자격이 없으면 unknown을 유지한다.
- 자기 RGB·자기 명령→LK 및 RGB열 제외 후보→부분 지도. 정답은 궤적/지도를 저장한 뒤 별도 평가만. 기존 상수 재튜닝0. 관문4는 warp10 자체 관문 통과/동일 시드 조건을 확인하여 실행 가능 여부를 기록한다. 임의 CPU 대체 금지.
- 각 큐에 실제 원격 절대경로 rejection_table. 기본 관문 후 필요할 때만 유한 계산/SIM 예산으로 후속 후보, 최대3라운드. cap_end는 임무 성공 아님. 30 SIM초보다 짧은 진단의 속도를 정식 첫30 관문으로 부르지 않는다.
- 기록 전용 자기카메라10Hz 고리 버퍼(마지막10SIM초), 개요/r1/r2 3배속 영상 각8MB 이하와 전체2Hz/끝10Hz 띠는 gcp2에서 만든다. Mac GUI0. 원인 주장 전 실패1–2와 추적 유지1을 시간순 검토한다.
- raw예산 최대2GiB(수집2세계×128MiB×최대3 + 감사/후처리1GiB), 영속디스크 보존. Mac 요약/몽타주/실패프레임/검토영상만. >64KiB JSON은 zstd 해제 SHA 검증 후 무손실 보관. 모델 호출0/키전송0/Drive0. 실행 코드는 먼저 커밋한다.
- gcp5 정지면 시작;8h상한 없음·idle20/budget-stop 유지. 끝에 자기 lease/PID 정리, 타작업 없는지 확인 후 gcp5 정지 확인. gcp2는 타 lease/PID 있으면 정지하지 않는다. gcp1 접근0. 목표2–3시간(자원 관리 계획, 행동 결정 wall 상한 아님).
