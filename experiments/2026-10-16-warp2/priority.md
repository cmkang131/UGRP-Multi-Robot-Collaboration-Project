# 우선순위·공수·기대 이득

공수는 **공통 백엔드가 정상 제공된 뒤** 한 명이 구현·비물리 검사를 하는 예상 집중 작업량이다. 실행 대기·GPU 컴파일·실패 수정은 제외한 설계 추정치이며 성능 실측이나 시간 약속이 아니다.

|순위/흐름|현재 CPU 근거와 범위|기대 이득|추가 작업/공수 추정|주요 제한|
|---|---|---|---|---|
|1 빔 짝 교사 beampair6|gcp2 n4, 첫30 SIM초 5개 3.360–3.751 wall/SIM, 중앙3.468; 6번째27.9초 성공. 직렬 선행2+후속4 부하, 16동시 아님|높음: 사용자 제공 beampair3 분해 physics85.5%·RGB3.0%를 가정하면 물리만4배/8배 빨라질 때 전체2.79배/3.97배, 이론 상한6.90배|setup/10Hz tick coroutine, lane별 2교사·guard·동기화, GPU force 평가 연계 / 1–2일|ray/FOV와 많은 후보 검사는 CPU; module monkeypatch 상태 분리; 실제 batch gain 미측정|
|2 release24 해제/둘러보기/재파지|기존 DEV6 6/6 요약, 첫30 중앙3.044; 이 요약에는 VM 식별 없음, gcp2 비교로 사용 금지|중간~높음 예상; 긴 물리 구간은 유리하나 RGB/ORB/계획 비중은 미분해|prefix→release phase coroutine, 2대 장벽·발행 odom·top audit·RGB buffer / 2–3일|prefix 평가 게이트·release 성공을 따로 보존. 10° 기존 근거미확인 문제를 가속 중 조용히 바꾸지 않음|
|3 reloc 주행/운반·고정 명령 재생|reloc15 gcp1 과거 selfmap R1/R2/R3 중앙4.193/4.395/4.647; carry2.742/3.767/3.615. gcp2 신규값 아님|물리 많은 주행은 중간, 고정 명령 재생은 높은 배치 적합성. 시각정합이 지배하면 이득 제한|capture/issue/advance backend 주입, 5Hz/10Hz clock, write-only 평가, frame_id 불변 / 2–3일|reloc15 자체 NOT_READY·오수용 미해결. backend 가속은 위치 정확도 개선 근거가 아님|
|4 LLM E2E|최신 고정 scene/profile의 gcp2 짝 측정 없음. 과거 교사 CPU값을 대입하지 않음|활성 세계가 많으면 가능; LLM 지연·429·RGB·host 전송에 좌우. 정량 예측 보류|별도 비동기 cohort scheduler·전체 상태 보존·call/ledger 경계 / 3–5일+모델 부하 검증|실제 host는 polling 후 계속 SIM을 진행한다. pause 모드는 별도 기본off 의미 변경이며 기존 E2E와 합산 금지|
|물리 이식 제외: 정적 reloc/저장 RGB 재생|저장 영상+발행 명령 재생은 physics0; wall/SIM은 해당 없음. 고정 자세 렌더는 mj_forward/카메라 경계만 있음|물리 배치 이득0에 가까움. RGB 전처리/ORB/ECC/정적 ray/render 묶음은 별도 최적화 후보|고정 RGB 입력 작업큐·프로세스 병렬·캐시 / MJWarp physics 이식 불필요|저장 RGB를 새 렌더로 대체하면 같은 입력 진단이 아님|

`speedup = 1 / (0.145 + 0.855 / physics_speedup)`. 85.5%·3.0%는 **이번 사용자 작업지시가 제공한 beampair3 값**이며 Mac에서 찾은 beampair3 회수 요약에는 세부 timing이 없어 원본 재집계하지 못했다. 원본이 gcp1에만 있으면 접근하지 않고 gcp2에서 새로 분해한다. 이 비율을 release/reloc/E2E나 gcp2의 현재 분해값으로 사용하지 않는다. RGB3%만 완전히 없애는 상한은1.031배이며, 관측/기록 프레임을 생략하는 최적화는 제안하지 않는다.

기존 CPU 수치의 파일 경로·SHA256·측정 모집단은 baseline-evidence.json에 있다. **새 MJWarp throughput·SIM초/$는 아직 미측정(null)**. N에 따른 batching gain은 Amdahl의 물리 speedup과 같지 않으므로 실제 N16/64/256 end-to-end 값을 재야 한다.
