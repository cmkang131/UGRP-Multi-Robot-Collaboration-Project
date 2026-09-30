# PR #347 독립 검토 반영

대상 리뷰 `cfc562da`, 수집 원본 `eaeaaff05553ea02c649b4db9ff82470fe6372b5`.
물리·렌더·모델 호출은 0회다. 수정은 검사·계산에 한정하고 명령·배치는 보존했다.

| 지적 | 수정 | 검증 |
|---|---|---|
| R1 전체 경로 여유 누락 | 양/음 gain·drive/stop τ·초기 오차·세계 축 속도 오차의 구간을 요구한다. 명령 경계마다 정확 적분식의 구간을 전파하고, 내부 이동은 시작 속도/목표 속도의 범위를 덮는 이동 구간으로 검사한다. 독립 근거가 없거나 전체 경로가 0.35 m 여유를 못 지키면 backend 생성 전에 거부한다. | 리뷰 두 반례의 독립 궤적은 계속 0.3 m를 위반하며 실제 실행 진입은 거부된다. 양 끝점만 안전한 내부 극값 사례, 비대칭·횡오차·범위 누락/NaN/overflow·근거 해시 변경도 검사했다. |
| R2 두 번째 형상 NaN 누락 | 모든 r1 형상의 xyz·반경·거리·합산 반경을 각각 검사한다. 한 개라도 부적합하면 hold·abort 기록 뒤 예외를 올린다. | 리뷰의 두 NaN 사례, z NaN·Inf·음수 반경·거리 overflow 모두 중단한다. |
| R3 v1 Fisher 창 연결 | 양·음 각각 x=v=0으로 시작하는 독립 4초 창 21행씩을 Fisher와 nuisance-stop 잔차 계산에 동일 적용한다. | 실제 `report()` 출력을 독립 수식과 비교한다. 조건수 18,523.6155 / 92,735.1010, 최소 RMS 0.030015 / 0.010292 mm. v2 값은 유지된다. |

현재 운동 범위는 **미확정**이다. #346의 확장 격자와 #348의 한 수집만으로 범위를 좁히지 않았다.
새 sidecar에 `bounds=null`, `BLOCKED_UNBOUNDED_MOTION`을 기록하고, 조회는 `runnable=false`다.
검토의 두 점 모델은 안전성 범위가 아니라 반례로만 계산한다. 보수적 경로 하한은
전진 0.067031 m, 측면 −0.182485 m이며, 샘플 궤적의 정확 최솟값이나 실제 충돌 관측이 아니다.
기존 substep 중단 인터록을 유지했다. 독립 근거를 갖춘 운동 범위의 검토 없이는 새 수집을 시작하지 않는다.

명령 JSON SHA-256은 `bda01f670febea5d5d298ac0e707515f956d25d2cc1c412c8690047bf86ed402`로
원본과 바이트가 같으며 4,600개 명령도 같다. v89를 유지하고 #348의 자료는 같은 명령 등록의
`eaeaaff0` 실행으로 보존한다. 수정 head의 실행으로 소급하지 않는다.
README에 #348의 입력 크기별 gain·deadband와 선형 1차 모델 부적합을 알려진 한계로 연결했다.
v1/v87의 166개 소스·9개 번들, 기존 설계 JSON·TensorBoard snapshot을 보존했다.

검증은 관련 회귀의 최종 결과 기준 **654개 + 27 subtests 통과**, 미해결 실패/xfail 0개다.
리뷰 검사는 원래 **2 passed / 6 strict xfailed**를 먼저 재현했고, 수정 뒤 **8 passed**다.
최종 변경 범위 전체는 [63개 통과](review_fixed_final.xml)했다. 큰 묶음은
[652 passed / 1 failed / 9 skipped](review_fixed_offline.xml)였다. 그 실패는 검사 중 작성자가
경로 계산에 유한성 검사를 보완하여 **소스 변경 감지가 정상적으로 완료를 거부**한 것이다.
가짜 수집 결과는 완료였고 `source_unchanged=false`, 달라진 파일은
`harness/measurement_path_clearance.py` 하나임을 직접 읽어 확인했다.
[확인 기록](source_change_abort_evidence.json)과 최종 63개 재검증을 함께 보존한다.
큰 묶음 전체가 한 번에 성공했다고 보고하지 않는다.

MuJoCo/Torch import를 막았으므로 native 컴파일·렌더 검사 9개는 건너뛰었다.
기존 프로세스 정리 검사 1개는 sandbox의 `ps` 금지 때문에 로컬에서 제외했다.
fixture 3개, bundle/registry 불변성, 수정 JSON 재계산 일치, 실제 CLI 계획 차단을 확인했다.
정확한 환경·소스/결과 해시는 [verification_review_fixed.json](verification_review_fixed.json)에 있다.

시작 시 최신 main `78ce7916`을 반영했다. 작업 중 추가된 `a520d9d8`(#345)은 CI workflow 변경을
포함하며 이번 수정에 필요하지 않아 가져오지 않았다. `.github/workflows` 전체는 `eaeaaff0`와 같다.
리뷰 원문/결과는 `git show`로 읽고 복사했으며 `/private/tmp`에 압축을 풀지 않았다.
리뷰의 이전 해제 경로 `/private/tmp/ugrp-review347.DvUEdY`도 없음을 확인했다.

수정된 합성 지표는 새 [TensorBoard snapshot](http://127.0.0.1:6006/?runFilter=%5E1001-v89-design-fixed%2F&smoothing=0#timeseries)의
v1/v2 × 두 축 4개 run에 보존했다. [저장된 고정 카드 링크·검증 기록](tensorboard_review_fixed.json)의
16개 scalar를 EventAccumulator와 실제 서버 HTTP 양쪽에서 원본과 대조했다.
HParams 이벤트 메타데이터는 확인했지만 Chrome `cgWindowNotFound` 때문에 화면·표시 열 재적용은
미완료다. 기존 서버는 변경하지 않았고 새 영상은 없다. #348 원본의 새 분석/변환은 수행하지 않았다.
