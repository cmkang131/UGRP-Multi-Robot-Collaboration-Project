Claude가 시작한 PR #249를 Codex가 이어 작업했습니다. **초안·미병합**입니다. 원격 head는 `961271a4`이고, 아래 Codex 변경은 현재 세션의 Git 권한 제한으로 **로컬 미커밋·미push** 상태입니다.

## 변경
- 기존 v2 장면·지도·동결 소스를 보존하고 `zone_wide_door_geometry_v3`, `zone_wide_door_geometry_v3_dock_v1` 두 새 버전에만 `robot_model: masterpi_v3`와 새 해시를 등록했습니다. 표식 없는 geometry_v2 지도에서 파생했습니다.
- 표준 Scene 상속과 host XML hook을 재사용합니다. 환경 변환 뒤 실제 템플릿의 물리·보정 파라미터로 v3 로봇을 만들고, 최종 로봇/장면 XML 해시를 기록합니다.
- 새 station/dock/footprint 소비자는 장면의 모델을 읽습니다. 차대 기준 파지 거리는 203.2 mm이며, 도킹·keepout은 같은 장착 위치를 반영합니다. 동결된 zone_teacher/zone_start_dock/zone_team_footprint는 수정하지 않았습니다.
- 새 `visual_arm_v3`는 기존 수학을 import해 48.2 mm 장착·2.2 mm 어깨 높이 차이·86.85 mm 실제 패드 중심을 반영합니다. 카메라 위치/FOV를 임의 조정하지 않았습니다. 새 스윕 가드는 자기 명령·자기 추정·정적 지도만 사용합니다.
- 장면별 runtime 선택과 v2 소비자 사전 거부를 추가했습니다. v3 손목 스킬·표식 없는 자세 제공자·짝 운반 실행기·전체 교사 상태기계 이관은 아직 남아 있습니다.
- 새 정적 감사 CLI를 표준 workflow 카탈로그에 등록했습니다.

## 번들 번호 확인
정적 감사 후 main `d5bd208e` 및 열린 PR #246/#248/#249/#250/#251/#252/#253/#254/#255/#256/#257의 GitHub head와 로컬 origin 참조가 모두 일치함을 확인했습니다. 전체 origin/*의 RUNNABLE_ID/EXECUTION_BUNDLE_ID/BUNDLE_ID 최대는 v73(#257)입니다.
- 선택: `zone-study-integration-v74-masterpi-v3`
- 기존 v69는 은퇴 목록에 보존
- workflow: 열린 브랜치 최대 2.3.0 다음인 **2.4.0**
- SHA 근거: `experiments/2026-09-28-masterpi-visual-v3/codex-bundle-heads.json`
- 원격에 게시되지 않았으므로 push 전에 번호 충돌을 다시 확인해야 합니다.

## 검증
- 사용자 지정 v2 기하 두 테스트: **23 passed in 0.87s**. 이 두 파일에만 허용된 짧은 물리 step이 있습니다.
- 기존 통합 pair/seams·입력 경계: **125 passed in 25.60s**.
- v3·동결 소스·번들 및 v64 대비 회귀 **826 passed in 924.17s**. 후속 감사 프로필·CI 수집 보완의 관련 검사 **31 passed in 3.73s**. 명령과 파일 해시는 `codex-validation.json` 참조.
- 최종 정적 감사 `codex-static-audit-v3.json`: 두 장면 × seed 700 × 3대, cargo_noslip_v1·noslip 10회. 자기충돌·로봇 간 침투 0건, 바퀴–바닥 접촉 표본은 장면당 24건(최대 약 0.145 mm 침투).
- 카메라당 221개 원시 pinhole 광선: robot_cam 자기 형상 가림 0/221, nav_cam 손가락 가림 2/221. nav_cam은 standard host에 없는 고정 진단 카메라로 추가한 것입니다. fisheye 렌더 전체/작업 물체 가시성 검증은 아닙니다.
- 물리 에피소드·모델/LLM 호출 0. 정적 감사는 mj_forward만 사용하며 weld OFF입니다.
- 코드·정적 감사가 물리 파지/주행/운반/실물 성공을 뜻하지 않습니다.

## 남은 문제
- 실제 v3 소비자 이관과 host 초기화·settling·주행·파지·운반 검증.
- v3 팔축 180 mm/높이 24 mm 목표는 패드 길이·서보 제한상 도달 불가능하여 거부합니다. 성공한 수학 테스트는 반경 145/155/160 mm × yaw -10/0/10도의 9점입니다.
- 공용 Git 메타데이터의 FETCH_HEAD/index.lock 쓰기가 `Operation not permitted`로 차단되어 커밋·push하지 못했습니다.
- PR 댓글·본문 쓰기 모두 `MCP tool call requires approval, but approval policy is never`로 거부됐으며 원격에는 반영되지 않았습니다.

상세 기록: [실험 README](experiments/2026-09-28-masterpi-visual-v3/README.md). 기존 v3 치수·출처 설명은 [모델 문서](docs/masterpi_model_v3.md)에 보존합니다. 병합하지 않습니다.
