# egomap71 — 자기 RGB 재확인·공분산 층화 (DEV, 기본 OFF)
기준 `4199f7e1`의 calib_traversed: 거짓귀환3/6·B오인1/6; 동일 체크포인트63001–63006 × off/on12회. 새 seed 확증·LLM·운반 E2E가 아니다.
토글은 독립 기본off: `rgb_reconfirmation=two_view_rgb_v1`, `covariance_inflation=nees_stratified_v1`; 본 비교는 둘을 함께 켜므로 단독 효과를 주장하지 않는다.
RGB는 B·통로정합·복귀 선언 전 다른 각도에서 영상 일치, 최대20초 순수 회전; 원본 home은 고정. [조사·차이](gate_references.md).
공분산은 과거 자기 명령×단계 proxy에 고정 배율; 온라인GT0·평균/입자 직접수정0. [문헌·오프라인 결과](COVARIANCE.md).
확보8run(2seed) 확인NEES χ²99.9초과 raw1747/5084→층화3/5084, pooled1/5084보다 나쁘다. 70c×4.154·41/1260 원자료 미발견·미재현.
관련22시험 통과(초기18통과/1fixture실패 수정 후 최종); Mac물리0. [사전계획](prereg.json): Azure구독88b7ee7f,3worker,90분실행+30분보관/종료,다른lease보존.
실행은 표준 `sim_cli workflow run egomap-reconfirmation-dev`; 기존 azctl/remote_run API로 live VM을 재사용하고 frozen Git object만 보낸다. [실행 조정기](code/launch_azure.py).
결과 원본은 Azure 영속디스크→검증ARM,Mac fetch-lite; 체크포인트 원본은 기존ARM,새입력복원목록은 실행에 기록한다. HOST_ERROR·분모를 summary.json에 모두 남긴다.
실행 소스 `813424857666340176ebfcf96707641bba1e3eb6`로 Azure에 제출했으나 체크포인트의 필수 `own-contacts.jsonl`이 5seed에서 누락되어 입력 복원 단계에서 차단됐다. 12/12 HOST_ERROR_INPUT_ADMISSION, 실제 물리0/12, 측정된 짝0/6. 거짓 복귀·B 오인은 각각 측정 분모0이며 성능 변화는 미확인이다. [전체 결과](summary.json).
실패 원본16파일을 ARM 전체 해시 검증 후 Mac fetch-lite로 회수했다. VM 사용149.55초; 자기 lease만 해제했고 다른 s3 lease 때문에 VM을 유지했다. [보관 검증](azure-preservation.json). 원본 로그를 합성하거나 체크포인트 무결성 검사를 완화하지 않았다. `oracle-x86`은 SSH 시간초과, ARM incoming의 일부 대응 폴더는 비어 있다.
동일 개발 자료의 RGB 오프라인 재생은 선언 직전 최대20프레임의 기하 필요조건만 확인한다. 다른 각도 행동의 반사실 결과나 B 의미 추적 전체를 재현하지 않는다. [재생기](code/replay_rgb_gate.py). 12회 주행 완료·개선·채택은 주장하지 않으며 DRAFT를 유지한다.
RGB 진단 소스 `5bd1f03e`는 정상 종료했으나 seed63002 참조 `bank-63002.npz`가 ARM에 없어 실제 게이트 재생0/2선언(63001 선언0건, 63002 B참1건·복귀거짓1건)이다. 로그의 exit0은 진단 기록 저장 완료이며, 게이트 개선을 뜻하지 않는다. [원본 요약](rgb-offline-summary.json), [11파일 보관 검증](rgb-preservation.json). 두 제출의 자기 lease 보유 시간 합244.03초이며 물리·LLM 모두0이다.
검토 후 재생기에 bank의 checkpoint SHA 일치 검사와 선언 분모 미확정 run 계수를 추가했다. 이 보강은 재실행하지 않았으며 위 진단의 소스와 구분한다. 복구에 필요한 것은 5seed의 체크포인트 로그 접두부, 원본 bank NPZ 및 egomap70c 원자료 위치다.
TensorBoard: 새 `1011-egomap71-v1` 스냅샷8run에 원본/pooled/층화 NEES, 과거 baseline, Azure off/on HOST_ERROR와 RGB 미완료 분모를 나눠 넣었다. 이벤트 scalar 재로딩은 통과했다. [뷰 설정](tensorboard.json); 새 영상은 없고 기존 원격 RGB는 Mac으로 복사하지 않았다.
공유 logdir로 native TensorBoard를 시작하고 Chrome 강 계정에서 저장된 pin URL을 열었지만, 자체 viewer가 로딩 중 반복 SIGTERM으로 종료되어 HTTP 값·HParams 표시 확인은 미완료다. [표시 제한](tensorboard-live-verification.json). 다른 viewer·실험은 종료하지 않았고 현재 이 작업 viewer는 남아 있지 않다.
