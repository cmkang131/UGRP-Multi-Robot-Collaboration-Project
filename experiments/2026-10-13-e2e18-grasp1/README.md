# 봉을 한 번에 집기 — DEV 후보 v384–v386

기준 v375에 접근 중 시야 유지·자기 좌표 기억 후보를 추가했다. **실제 후보 파지 0회 실행, 성공률·시간 개선 미확인**이다. r80 정렬 상태 4개와 공용 v387 staging 어댑터를 이 PR에서 만들었다. 서버 단계 실행은 미확인이다. 전체 E2E로 대체하지 않는다. 부모 소스 `f4d79b7772d9e7f115424241f741b44a4ab60094`, 브랜치 `claude/e2e18-grasp1`, 감독 PR #461. 최초 후보 코드 SHA는 `e8407cffbdbc3c0f99b474d832e8abf605ac98be`; 새 단계 시험은 PR #461 제출 코멘트의 v387 소스 SHA를 사용한다.

## 원인과 관측 범위

- r69 v324/v329 seed61006 로그 2개는 정렬 궤적 해시가 같아 **독립 궤적 1개**다. 샘플 기준 정렬 76→511 SIM초, 435초. v324 상세 프레임/명령/이벤트 소스는 `c11b4a9474b65a013c11c319efd6266b91851cdb`다. v329 이벤트를 별도로 측정한 것으로 세지 않는다.
- r1: 접근182초·acquire121초·visual_servo70초. r2: 접근196초·acquire177초·visual_servo5초. visual_servo 상태 진입은 파지/held가 아니다. 먼저 도착한 r1의 대기와 r2의 지연이 겹친다.
- r1 목표 소거: t132.8/268.8, 마지막 RGB 이후60.2/60.8초. r2: t297.2, 60.4초. `expire12_v1`이 있으나 `memory60_view_v1`이 60초까지 소거를 막으므로 이 코호트는 **12초 소거가 아니다**. acquisition 시작은 r1 2회, r2 2회(처음 진입1+재진입1); 로그 상태 전환만 세면 다른 복구가 끼어 과대 계산되므로 이벤트 기준을 쓴다.
- 최초 검출 실패는 항상 완전한 시야 이탈이 아니다. 예: r1 t73.2/140.0 `BAND_INWARD_SIDE_UNRESOLVED`, t200.8 `BAND_CLIPPED`; r2 t237.2 `BAND_CLIPPED` 직전 경로 회전. 상세 onsets·RGB 해시는 압축 진단에 보존했다. 끝의 방향 판정 오류와 시야 이탈을 구별해야 한다.
- 기존 `gaze_target()`은 `memory60_view_v1`에서 fresh=false이면 팬 목표를 반환하지 않는다. `view()`도 마지막 팔 자세를 그대로 유지한다. 따라서 경로 회전·접근으로 상대 방향/거리가 바뀌어도 검출 상실 이후 시선은 따라가지 않는다. 마지막 명령으로 움직인 실제 카메라 방향은 이번 자료만으로 확정할 수 없다.
- r69 저장 영상 `r1-132.8.jpg`, `r1-268.8.jpg`, `r2-297.2.jpg`를 직접 열었다. 세 장에 봉은 보이지 않는다(바닥/벽, r2에는 다른 로봇 일부). **이들은 소거 시점 영상이며 최초 손실 시점의 영상은 아니다.** 전체 시야 밖인지 가림인지 인과관계는 미확인이다.
- r76 회수본 전체32개 중 align 진입18/32, align 완료0/32(진입 부분집합0/18). 관측 종료까지 시간은 중앙130.1·최대197.45초이며 완료시간이 아니다. acquire 시간 중앙/최대: r1 2.825/136.95초, r2 6.8/138.8초. acquisition 시작 중앙1회, 최대2회; 기록된 최대 cycle은 r1 7, r2 6. 초기 획득과 재탐색을 구별하며 짧게 중단된 실행을 빠른 성공으로 세지 않는다.
- r79 HOST_ERROR(402)는 조정자 지시대로 제어 성공률에서 제외하며 이번 통계에 합산하지 않았다. r80 후속 회수 장면4개는 `r80-stage-diagnostic.json.zst`와 staging.md에 별도로 기록했다. 이전 통계와 합산하지 않았다.

## 후보와 경계

| 버전 | 기본 off `--grasp-once` | v375에서 추가되는 동작 |
|---|---|---|
| v384 | regulated_v1 | v356의 기존 RPP 주기·경로 재사용·팬 deadband·마지막 관측 방향 탐색을 그대로 결합 |
| v385 | gaze_v1 | 자기 RGB의 관측 밴드를 자기 odom에 기억; 일시 검출 상실에도 현재 자기 위치로 팬/기존 팔 자세를 재선택; 80PWM 반복 대신 제한 범위 내 절대 팬 명령 |
| v386 | track_gaze_v1 | v385 + 유효한 기억으로 staging 접근 유지 및 정렬 진입 시 가설 구성 |

관측마다 자기 RGB와 자기 명령 기반 위치만 쓴다. 신선한 RGB로 기억을 갱신하고, 미검출 중 자기 좌표의 목표 평균은 고정한다. 불확실성은 시간·자기 이동거리·회전량에 따라 단조 증가한다. 기억 상한120초·불확실성0.18m, 초기0.03m와 증가 계수는 **DEV 가정이며 보정된 Kalman 공분산/신뢰구간이 아니다**. 전체 Kalman 필터는 측정 잡음·끝 대응의 검증이 없어 채택하지 않았다. 최신 RGB 없이 final alignment/파지를 승인하지 않으며 8cm staging 안에서는 기존 재관측을 요구한다. 큰 불확실성에서는 기존 경로로 돌아간다. 장기 가림·오검출·반대 끝 오인 해결을 보장하지 않는다.

팬 범위±60도, 물리 카메라/FOV/로봇 외관은 그대로다. 도달 불가능한 방향은 `gaze_pan_reachable=false`로 기록하며 경로 자체를 새로 만들지 않는다. 벽/팔 clearance·카메라 settling·실제 명령 승인 경로를 유지한다. 이 후보가 경로 회전 중 모든 프레임의 봉 가시성을 보장한다는 뜻은 아니다. 두 로봇의 대기 정책은 변경하지 않고 각자 접근을 개선하는 비교다.

## 단계 시험 요청

후속 지시를 적용한 [staging.md](staging.md)와 `stage-request-v2.json`이 현재 계획이다. `stage-request.json`은 이전 제안 기록으로 보존하며 실행하지 않는다. 4조건×r80 4상태×2seed=32회, seed별16개씩 두 묶음, 최대300SIM초, VM3 게이트3.5다. 정답은 TEST_SETUP_GT 초기 배치와 평가에만 쓴다. 매핑30초 상태도 함께 제공한다.

로컬에서 정렬 상태4/4·매핑 상태1/1의 causal prefix·출처·압축 왕복을 확인했다. 자기 지도는 원본 accepted RGB·자기 명령을 재생해 복원하며 모든 과거 자기 추정과 대조한다. 전체 격자 원본 해시는 없으므로 재구성 지도 해시/인계 일치와 과거 추정 일치를 구분한다. 서버에서의 실제 RGB 재생, 배치오차, 기준선 재탐색 재현, 물리 실행 전체0/32·핵심0/16은 미확인이다.

## 검증·기록

관련 3개 시험 파일만 실행한다: `test_e2e_grasp_once.py`, `test_e2e_approach_commit.py`, `test_e2e_approach_efficiency.py`. 실제 approach dispatch에서 fresh gate, 기억 상한/불확실성, 로봇별 분리, 옛 off 동작, 팬 제한, 새 bundle 등록·변조 거부를 확인한다. 물리/렌더/모델 호출은 하지 않았다. 시험 결과는 summary의 verification에 기록한다.

분석 재현: `python3 scripts/analyze_e2e_grasp_once.py --r69-inputs <r69-approach-inputs.json.zst> --r69-logs <r69-logs> --r76-root <e2e18/outputs> --output <새 경로>`.
`diagnostic.json.zst`는 새 분석 보고서이며 원본은 입력 경로에 그대로 있다. 압축 전후 전체 SHA를 확인했고 `summary.json`에 기록했다. 영상3장의 해시는 `visual-evidence.json`에 보존한다. 로컬 원본은 원격 백업으로 표현하지 않는다.

## 참고 자료

- [Nav2 Docking 공식 사용법](https://docs.nav2.org/jazzy/tutorials/general_tutorials/using_docking/) 및 [공개 docking_server.cpp](https://api.nav2.org/nav2-rolling/html/docking__server_8cpp_source.html): 2026-10-13 열람. staging→초기 검출→최종 접근 분리와 실패 후 재시도를 확인했다. 기존 staging/fresh gate 구조를 유지한다.
- [Zhang 등, The Field-of-View Constraint of Markers for Mobile Robot with Pan-Tilt Camera (2019)](https://arxiv.org/abs/1909.10682): 초록 열람. 카메라 가시성 제약을 주행/팬과 함께 다루는 선행연구. 여기서는 기존 장착/범위에서 기억 방향 팬을 적용하며 논문의 제어기나 보장 재현은 아니다.
- [Qin 등, Active Perception Meets Rule-Guided RL (ICCV 2025)](https://openaccess.thecvf.com/content/ICCV2025/html/Qin_Active_Perception_Meets_Rule-Guided_RL_A_Two-Phase_Approach_for_Precise_ICCV_2025_paper.html): CVF 검색 결과 초록의 탐색/last-mile active target perception 구분을 확인. 페이지/PDF 재열람403으로 **전문·구현·수치 미확인**. 본 후보의 성능 근거로 쓰지 않는다.
- [Welch & Bishop, Introduction to the Kalman Filter](https://www.cs.unc.edu/~welch/kalman/media/pdf/kalman_intro.pdf): 이번 도구에서 원문 접근 실패, **미확인**. 후보는 Kalman 구현/잡음 검증을 주장하지 않는 bounded stationary track이다.
