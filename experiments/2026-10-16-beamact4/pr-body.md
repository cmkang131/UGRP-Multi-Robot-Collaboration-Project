beamdiag에서 확인한 PWM 감소→조기 READY/GO와 done 뒤 재추론 중단에 대응하는 학생 후보다. `beamact4_stage_v1`은 같은 ACT decoder의 별도 학습 단계 head로 READY를 선언하고, READY 철회 때 기존 GO/ACK 프로토콜을 다시 거친다. `beamact4_done_recovery_v1`은 done 다음 틱에 새로 추론하고 완료 철회를 허용한다. 두 토글은 기본 off다. 자기 RGB·발행 명령·역할 입력, 기존 GO/ACK 형식·시한, 원래 completion 출력과 물리 평가의 분리를 유지한다. 수제 근거리 경로나 온라인 정답 가드는 추가하지 않는다.

TRAIN 접근 거리 p99=0.78167263m·yaw 오차 p99=2.93671514rad에서 상대 추정 오차 예산을 뺀 지도→ACT 입구와, 실제 반대 역할·원거리/복구 시연의 요구를 명세했다. 상대 오차 예산·새 head 체크포인트는 아직 없으므로 실행 NOT_READY이며 계획은 `ready=false`다. 교사 `codex/warp6`는 warp8 관문 종료 뒤 조정자가 배정할 대상이며 이 PR에서 수정하지 않았다.

- Base: `codex/beamact3` / PR #545, 시작 SHA `14f9c135de2a008ef1224d503c7cdbda6ae98f68`.
- 검증: Mac 비물리 3파일 **15 passed / 1 skipped**. 조기 닫기 거부, PWM과 무관한 학습 READY, READY 철회 후 새 GO/ACK/지연, done 뒤 새 추론, 모의70행 명령 재생·PWM/단계 로그 변조 거부, 기존 barrier/replay를 확인했다. Linux 합성 head/loss gradient 시험은 Mac에서 건너뛰었고 실제 모델 학습·저장/재로딩·물리 개선은 미검증이다.
- 기록: [README](experiments/2026-10-16-beamact4/README.md), [거부표/순차 퍼널](experiments/2026-10-16-beamact4/rejection_table.md), [입구 명세](experiments/2026-10-16-beamact4/handoff-spec.md), [교사 명세](experiments/2026-10-16-beamact4/teacher-spec.md), [검증 원장](experiments/2026-10-16-beamact4/verification.json).
- 새 시연 기록·학습·모델 추론·물리·렌더·GCP·GUI 실행0. 공용 MJWarp/장면/기존 입력 계약 변경0, 새 실행 번들 ID 없음. 기존10Hz 실패 직전10SIM초 기록 옵션 유지. 기존 C1/beamdiag 미추적 자료 보존. CI 목록은 끝에 새 시험2개 추가만 했다.
- 방법 근거: [ACT §IV](https://arxiv.org/html/2304.13705v1), [DAgger](https://proceedings.mlr.press/v15/ross11a.html)를 직접 확인했다. 고정 upstream LeRobot 원문 웹 열람은 실패해 저장소의 기존 공유 decoder/one-forward 어댑터를 사용했다. 논문은 이 환경의 개선 성능을 보증하지 않는다.

후속 순서는 warp8 종료/교사 배정→새 교사95%·최소40→승인된 시연/단계 표적→배포 모드 READY 검증/새 모델 로딩→새 입구/소스/모델을 등록한 학생 평가다. 이번 PR은 draft로 유지하며 실행·학습·병합 승인을 요청하는 대기열이 아니다.
