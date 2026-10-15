ACT 외 교사·진단 흐름을 MJWarp 공통 백엔드에 연결합니다. 첫 대상은 beampair6 빔 짝 교사이며 고정 adapter/교사 소스의 advance scheduling만 coroutine으로 바꾸고, 기존 판단·가시 측정·held 숨김·성공식을 유지합니다. warp1 transport를 재사용해 두 로봇의 명령·카메라·다중 빔 형상 force 평가를 지원합니다.

- 읽기/설계: 57파일·753구문 inventory, 공식 MJWarp/Playground/Brax/Isaac Lab reset·pause 비교, 빔→release→reloc 주행→E2E 우선순위.
- 비물리 검사: 12 passed. 기본 off/Mac 차단, lane 모듈 격리, 액추에이터 열 격리, 고정 scheduling AST 구조 확인.
- gcp2 물리 검증 진행 전: 새 성공률·처리량·SIM초/$ 미측정. HOLD_SCENE·관문 미승인·학습/LLM 호출 0.
- warp1 위의 stacked draft입니다. backend별 결과를 합산하지 않습니다.

Refs #523
