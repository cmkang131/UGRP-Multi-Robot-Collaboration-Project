지도 보정이 이동 오차를 키우던 문제에 대해 기본 off 방식 `static_amcl_v1`을 추가했습니다. Nav2 고정 원문의 이동·likelihood field·KLD/재표본화를 옮기고, 자기 RGB+발행 명령으로만 알려진 정적 지도에서 전역 입자 초기화/추정을 합니다. 자기 지도는 관측 키프레임으로 계속 저장하며 위치 우도에 되먹이지 않습니다.

**NOT_READY / 실제 인계·기본 채택 보류.** gcp5의 같은 R1–R3 1044프레임을 표준 설정/입력 어댑터별15회 재생했지만 모두 오프라인 관문을 실패했습니다. 현재 곱 우도 후보의 R3 끝 전역 제안은1.823m/91.149° 오류이며, 수렴 제안4건 모두 잘못됐습니다. 같은 프레임 OFF 끝43.216mm/3.311°는 기존과 일치합니다. 미수렴 가중 평균은 진단 후보이고 유효한 전역 궤적으로 채택하지 않았습니다. 현재 API는 분포가 좁아져도 `runtime_qualified=false`, `ready_for_handoff=false`, `adopted_pose=null`입니다.

- R3 첫0.4SIM초에서 인계 요구 범위 내 입자23개의 관측 가중치 합이1.1356e-28로 떨어지고 재표본화 뒤0개가 됐습니다. 스냅샷 추가 재생의 trajectory SHA는 원본과 같으며, 정답은 봉인 뒤 별도 지원 대역 감사에만 썼습니다.
- 원래96개 열에서 먼저 stride를 고르고 NaN을 건너뛰도록 입력 어댑터를 고쳤습니다. 기존 반환 열 압축 후보의 실패도 별도로 보존했습니다. σ/수용 문턱을 결과에 맞춰 낮추지 않았습니다.
- gcp3 warp8f의 별도418뷰/28로봇은 418→벽190→갱신176→수렴0입니다. gcp5와 합산하지 않습니다. 새 물리·모델·렌더0이며, 적재 주행/문/구역/복귀/내려놓기/ACT/LLM 성공은 확인 안 됨입니다.

검증: Mac 비물리18PASS, gcp5 최종 후보9PASS. 원문 C++/C 수치 대조에서 이동5조건1000표본·KLD12조건·두 우도 모델 dense/NaN4조건을 통과했습니다(전체 ROS/물리 동등성 주장은 아님). 원본2151파일·16봉인·gcp3 JPEG418/예측142파일 해시 불일치0, 요약 회수63파일 해시 확인. 실패2개의2Hz/R3 말미10Hz를 직접 확인했고, 성공 운반 영상 비교는 자료가 없어 미충족입니다. 입력/clone 준비 오류와 선택 그림 의존성 오류도 기록했습니다.

자기 임대 해제·타 작업 프로세스0·GPU0 확인 후 gcp5 정상 정지, gcp3 기존 lock 보존 후 실제 종료를 확인했습니다. **둘 다 TERMINATED**입니다. CPU VM/GUI/키 전송0, 원본 디스크와 동결 소스 보존. 새 물리 실행 조건인 OFF 개선이 충족되지 않아 실제 라운드는0회입니다. PR은 DRAFT로 유지하며 병합하지 않습니다.

[mapbuild9 전체 기록·참고 자료](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/mapbuild1/experiments/2026-10-17-mapbuild9/README.md) · [funnel](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/mapbuild1/experiments/2026-10-17-mapbuild9/rejection_table.json) · [API/해시](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/mapbuild1/experiments/2026-10-17-mapbuild9/API.md)
