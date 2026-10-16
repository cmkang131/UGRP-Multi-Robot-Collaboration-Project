beampair8 성공185시드의 두 로봇 기록을 묶어 학습166/60,023행·검증19/6,908행으로 분할하고, TRAIN-only 정규화를 다시 계산했습니다. 보류20과 중복0, shard1,480파일 해시 및 정규화 재계산 정확 일치를 확인했습니다.

동일 기체·입출력 형식/교차 색 끝 배정을 근거로 공유 ACT 하나를 선택합니다. ACT16과 동일하게16개 wheel/pulse 이력을 학습·배포 양쪽에서 TRAIN 평균으로 가리는 기본 OFF 후보를 기존 trainer에 연결합니다. PWM·age·토큰·명령 시계는 유지하고, whole-history dropout은 ACT16 첫 계획과 같은0입니다. adapter에 변환을 저장하고 stock loader의 묵시적 누락을 거부합니다.

검증 persistence(마지막 실제 명령 유지)의 wheel MAE는 전체0.02312898(N6908), 8틱 재추론 격자0.02280942(N913)입니다. 단계별 pulse/PWM 지표를 함께 보존합니다. 실제 학생 방문의 재추론이나 ACT 오차가 아닙니다.

두 번째 L4 생성은 전역 GPU 한도1개에 막혔고 2개 증설도 GCP가 거절했습니다. **학습·L4 smoke·ACT 검증 MAE·학생20시드 평가·Release는 모두 미실행**입니다. 추가 L4 VM/디스크는0, GPU0h입니다. warp3 L4는 변경하지 않았습니다. 기존 pair14d ACT에는 별도 READY 출력이 없으며, 자기 명령의 닫기 요청을 READY로 해석해 GO/ACK로 연결하는 학생-only 실행기도 미구현입니다. 평가 큐는 command=null·ready=false이고 n/20과 퍼널은 null·미시작20입니다. 교사185/200과 합산하지 않습니다.

검증: Mac 관련 비물리34pass/2skip 및 catalog/입력26pass/1skip(겹침 있음); GCP2 CPU 실제 무작위 초기화 ACT adapter 저장/재로딩·동일 예측과 입력6pass. CPU 검사는 optimizer/GPU smoke를 대신하지 않습니다. persistence 표준 관리 기록 exit0·입력/소스 변경0, 회수 파일 SHA 일치 확인. 전체 원본은 gcp2 디스크 보존이고 독립 전체 백업은 없습니다.

기록: experiments/2026-10-16-beamact1/README.md, summary.json, rejection_table.json, verification.json. PR #537 위 DRAFT·NOT_READY이며 병합하지 않습니다.

참고: ACT https://arxiv.org/abs/2304.13705 · 공식 코드 https://github.com/tonyzhaozh/act · Causal Confusion https://arxiv.org/abs/1905.11979 · PR #504/#528 및 act16w c6a4569cf.
