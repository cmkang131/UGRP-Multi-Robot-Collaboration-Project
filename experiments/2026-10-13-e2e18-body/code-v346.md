# v346: 강한 규칙 몸 스킬과 탐색 완료 정지 복구

2026-10-13 17:50 사용자 결정에 따른 후보이다. 몸 스킬의 새 기본은 `body_backend=code_v1`; d1·Jev는 명시적으로 켜는 비교 옵션이다. `body_controller=jev_v1`이라는 기존 토글 이름은 호환용으로 유지하며 전체 기능은 기본 off다. 이 토글을 켜고 backend를 생략하면 bounded 스킬과 code_v1이 적용된 **e2e18-v346 / 7.239.0**이 된다. 명시적 d1 v344·Jev v345도 남는다. 번호는 main·열린 PR 브랜치 최대345를 확인한 뒤 사용했다.

## 바뀐 행동

- 같은 자기 RGB·자기 지도·명령 이력, 초음파와 합의 상태, 안전 필터를 소비한다. 코드가 현재 목표 스킬, 반대쪽 우회, 후진·재관측, 파지·들기·운반·내려놓기/카메라 배치를 고른다. 매 펄스 수치 실행과 기존 안전·현재 GO/ACK 검사는 유지한다.
- 같은 단계의 최근10개 결과에서 관측 진척 없는 스킬을 기억한다. 같은 선택3회 무진척이면 안전한 대안이 있을 때 제외한다. 안전상 필요한 대기를 강제로 없애지 않는다. 자기 추정 이동·회전을 진척에 함께 써서 지도 작성 중 범주 이름이 같다는 이유만으로 실패를 확정하지 않는다.
- 정렬 예산/20초 무진척은 기존 넓은 시야→standoff→카메라 팬 순서를 쓴다. 세 가지가 소진되면 안전한 좌우 대안으로 계속하며 관측 이력은 지우지 않는다. 통신 조건에 따른 별도 우회는 없다.
- `exploration_finished`이고 아직 mapping의 explore 소유권이 남아 있으면 upstream hold도 몸 결정 진입점이 된다. 즉시 재계획을 한 뒤 여전히 종료 상태이면 스캔→후진→반대쪽 우회를 유한 스킬로 순환한다. 새 관측 지도와 자기 위치는 보존하고 오래된 목표 blacklist/visited 억제만 만료한다. 실패·종료·r3·배치/카메라 소유권·이미 생성된 경로에는 개입하지 않는다. 임무 완료나 다음 단계 진입을 만들어내지 않는다.
- 코드 결정은 provider_calls=0, 비용0, 외부 API 대기0으로 기록한다. 결정 횟수·선택·규칙·자기 영상 해시는 따로 보존한다. body relay/키/receipt를 읽지 않는다. Gemma 메시지용 relay는 기존 경로대로 필요하다.
- 프로토콜 행동 선택과 문장 렌더링 분리는 별도 #466 계열의 담당 범위다. 여기서는 전달된 합의 상태만 소비하며 자연어 메시지 본문을 고치지 않는다.

## 원인과 검증 범위

감독자 #465 코멘트와 VM3 r73 원본을 대조했다. v344 r2의 67.2/76.2/85.2 SIM초 ownmap은 `exploration_finished`, `hold`, finished=true였다. 93.6초 기록에서야 idle_s=30.05의 기존 재시도가 발동했다. `PersistentNavigator.update`의 완료 조기 반환과 `BodyGate`의 이동 제안 없는 결정 생략이 결합한 정지였다. 전역 탐색기 구현을 바꾸지 않고 새 번들 gate에서 연결했다.

저장 장면은 r70 r2 8개, v321 16개, v344 r73 5개를 모두 보존한다. 재생 대상23개와 제외6개를 분리한다. 제외는 직접 이동 제안이 없는 정렬2개, 현재 GO/ACK·실행 배치가 보존되지 않은 파지/운반4개다. 가짜 합의를 만들어 질의하지 않는다. 진행/복구 스킬 선택률은 물리적 이동 성공률이나 정확한 스킬 정답률이 아니다. 현재까지 코드 재생 23/23(8/8, 10/10, 5/5), 핵심 terminal mapping 3/3 즉시 재계획, 몸 provider0이다. 최종 SHA 재생과 원본 해시는 code-v346-summary.json에 남긴다.

관련 시험은 body_code/body_controller/body_upstream 3파일이다. 새 코드의 실제 dispatch·무호출·필터/반대 우회·반복 제거·합의·기본/등록·receipt 불필요·terminal 소유권을 검사한다. 실제 native 탐색기에 과거 종료 플래그와 명시적인 **합성 known-free/no-frontier costmap**을 넣은 단위 시험에서 30초 대기 없이 다음 수신에 스캔 명령이 나왔다. 이 시험은 저장 costmap 또는 물리 재생이 아니다.

미확인: v346의 첫30 SIM초 raw, 전체 seed61006, 정렬 시작≈76→공동 파지 시간(v321 기준435 SIM초), 재획득·진동·물리 성공, CI 완료. VM 제출은 #461에서 감독자에게만 요청한다. 새 source/bundle을 기존 관리 실행기에 등록해 감독자가 속도 게이트와 동시 수를 정해야 한다. code_v1에는 body relay가 없으므로 body receipt 수명 검사는 필요 없고 Gemma receipt의 유효 기간은 유지해야 한다.

## 참고 자료

- [Navigation2 현재 복구 트리](https://github.com/ros-navigation/navigation2/blob/main/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml): 재계획과 RoundRobin 복구. 2026-10-13 직접 확인. 지도를 지우는 동작은 우리 관측 보존 제약에 맞춰 목표 억제 만료로 제한했다. 논문의 물리 성공을 이 코드에 승계하지 않는다.
- [감독 r73 정지 원인](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/465#issuecomment-6141846233): 원본 시각과 우리 추출 장면을 대조했다.
- [정책 변경 #467](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/467), main AGENTS.md와 docs/decision_model_control.md. 작성 당시 main은 변경 전 문구이며 17:50 사용자 지시와 #467 갱신을 우선 적용했다.
- `/private/tmp/claude-501/-Users-changmin/2eb0ff27-da4f-4484-8131-64ef091df6ae/scratchpad/realscene/README.md`, `results_e1.json`: 다른 작업자의 실제 장면 비교. 원자료 경로와 제한을 확인했으며 우리의 신규 결과 분모에 합산하지 않는다.
- 같은 scratchpad `decision-v2/README.md`, `results_test.json`: 840회 토이 근거. SayCan 작업은 방향 변경으로 중단했고 신규 모델 호출0이다. 중단 사본은 `outputs/e2e18-body/abandoned-selection/`에 보존하며 실행 등록/커밋 대상이 아니다.
