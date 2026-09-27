# VIS5 작업·범위 기록

- 작업 브랜치 `codex/vision-loc-v5`, 시작 SHA `137ba742493b1f09c68238525cfc44a57054ae48`.
- 이슈 #216의 최신 [VIS5 코디네이터 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5855928447)을 connector로 확인했다. 관련 열린 PR은 VIS4 #242, 통합 #229다. VIS5는 실험 디렉터리의 opt-in 보고 계층에 한정하며 worker/통합 러너를 바꾸지 않는다.
- `git fetch origin`은 공용 Git 메타데이터의 `FETCH_HEAD` 쓰기가 sandbox에서 거부됐다. `gh` 네트워크 연결도 실패하여 공식 저장소 이름 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`의 connector로 이슈와 열린 PR을 읽었다. origin URL·main·다른 worktree는 바꾸지 않았다.
- primary main은 로컬 origin/main보다 315 커밋 뒤라고 표시됐다. 원격 fetch 완료 상태를 뜻하지 않는다. primary는 쓰기 허용 범위 밖이며 이번 작업은 커밋 금지이므로 갱신·커밋·push·PR·병합을 하지 않는다.
- 후보·fit/validation·선택 규칙은 `dev_plan_v5.json`에 **관측 feature 추출·GT 적합·후보 비교 전에** 고정했다. SHA256 `c81f4977ebb72e8f0c3109b93e2f4235df826e8d5c2ab5c360e98dbe2f4cb217`.
- 기존 학생 추정에 적용하는 보고 계층의 shadow 비교를 선택했다. yaw 보정은 현재 관측이 적용된 프레임에서만 수행하며 다음 PF 예측에는 되먹임하지 않는다. 이 선택은 물리/새 렌더 금지 범위에서 보고 계층을 동일한 저장 자료로 검증하기 위한 것이며 새로운 PF 전체 궤적·폐루프 개선의 증거가 아니다.
- VISW 원본 inventory에 분할 관측 캐시·분할 마스크·pre-resampling ESS가 없다. `n_eff`는 재표본화 후 값이어서 대신 사용하지 않는다. 새 추론 예산을 0으로 정하고, VISW는 baseline/s1 yaw 보정 fit 진단에만 포함한다. y1/y2/m1의 VISW 결과를 만들어내지 않는다.
- 모드 소실에 대한 첫 후보는 σ 팽창이다. 재초기화는 이번 유한 후보에 넣지 않았다. 앞선 대칭 지도 재초기화 실패와 혼동하지 않으며, 보고 불확실성 증가를 실제 위치 회복으로 부르지 않는다.
- 소스 동결 전 합성 검사에서 명령 필드 `pulses`, 최소 관측 열 수, 보정 테이블 fixture 오류를 수정했다. 활성 런타임 검사는 PF 적분 시각의 부동소수점 끝점 오차로 새 관측을 놓치는 문제를 찾았고 1e-8 s 비교 허용차로 수정했다. 단순 판정 임계값 조정이나 후보 추가가 아니다.
- 첫 추출은 9회 모두 완료했지만 비교는 fit 결과 생성 전에 `different report at the same timestamp`로 중단됐다. 교사 dev 495쌍·VISW 41쌍의 연속 프레임이 같은 SIM 시각을 가진다. 모두 유지하고 dt=0·last_scan 불변이면 새 근거로 집계하지 않도록 수정했다. 최초 산출물을 그대로 보존하고 `outputs/vision-loc-v5/final/`에 추출부터 전체 재실행한다. 사전 계획·후보·격자·선택 규칙은 변경하지 않았다.
- 물리 step·새 렌더·새 모델 추론·LLM 호출은 하지 않는다. pytest는 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행하고 finally에서 임시 폴더를 제거한다. 실행 로그는 `outputs/vision-loc-v5-checks/`에 보존한다.
- TensorBoard 공용 view 설정은 읽었다. `/bin/ps`가 sandbox에서 거부되어 서버 PID·소유권 확인은 불가능하다. primary 공용 root도 쓰기 허용 범위 밖이다. 이번 local native snapshot은 실제 event 재로딩으로 검증하며 공용 등록·화면 표시는 미완료로 명시한다. 기존 서버·다른 작업의 프로세스는 변경하지 않는다.
- 프로젝트 예외에 따라 Google Drive는 사용하지 않는다. 기존 raw·스냅샷·실험 기록을 보존한다.
