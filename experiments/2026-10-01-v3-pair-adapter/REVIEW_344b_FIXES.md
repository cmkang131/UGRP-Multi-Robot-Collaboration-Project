# REVIEW_344b 반영 — v88 미실행, draft 유지

기준 후보 `b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a`, 독립 재검토
`26534b1217a27ac9f7d7623fc03cd7e6b91f068e`의 B1(P1)·B2(P2)를 한 묶음으로 반영했다.
최신 main `2c45b137c480eecff3dac871277cf48914dd5cf4`를 병합해 #342(v87), #347(v89),
#348 기록을 포함했다. 원문 `REVIEW_344b.md`·증거 JSON은 검토 브랜치의 바이트 그대로 보존한다.
이번 문서는 작성자 수정 기록이며 새 독립 승인이나 물리 인수가 아니다.

- **B1:** #347의 `path_preflight()`를 공유한다. 종류별 독립 운동 범위·근거는 null로 보존하고
  세 계획 모두 `runnable:false`로 닫았다. CLI는 물리 모듈 import 전에, `run_case`와 직접
  `PhysicsBackend` 생성은 출력/생성기/세계 구성 전에 재검사한다. 저장된 PASS를 신뢰하지 않는다.
  공용 검사는 근거 해시, 양/음 gain, drive/stop, 초기 오차, 축간/yaw/slip 오차와 명령 사이의
  연속 경로를 확인한다. 초기 hold와 마지막 팔/카메라/coast까지 370초 전체를 넘긴다.
  공용 계산기는 아직 단일 평행이동만 지원한다. 회전 명령이나 두 운반자·빔을 누락해 계산하지
  않고 명시적으로 거부한다. 독립 범위와 해당 경로 지원의 검토 전에는 수집을 열 수 없다.
- **B2:** #347의 xyz·반경·거리·envelope 검사를 `geometry_envelope()`로 공용화했다.
  v88은 모든 로봇·빔 geom의 xyz를 이 검사에 넘긴 뒤 XY로 투영하고 최종 gap의 유한성도 확인한다.
  비정상 z/반경/거리의 기존 hold + abort 기록을 유지하며 명령을 보정하지 않는다.
- **회전:** unloaded에 이미 양/음 .01/.02/.03의 10초 회전 계단과 PRBS31(0.5초 chip)이 있다.
  242–326초의 84초 블록이며 pose 0.05초, 종류별 reset 포함 최대 375초다.
  누락된 블록을 추가하라는 조건에 해당하지 않아 일정은 바꾸지 않았다. #346용 원시 수집은
  아직 실행되지 않았으며 이 기록을 회전 측정 자료로 쓸 수 없다.

`tests/test_review_344b.py`의 5 strict xfail만 제거해 기존 assertion을 required pass로 만들었다.
그 외 14개도 유지했다. 근거 hash 변조, v89 근거의 v88 재사용, 저장된 PASS, 직접 생성자,
거리 overflow, 로봇·빔의 NaN/Inf, 실제 회전 일정을 추가 검사했다.
기존 fake clock/reset/render 검사는 새 관문 이후의 동작을 검사하도록 테스트 내부에서만
관문을 대체한다. 실제 세 진입점 거부 검사는 대체 없이 실행한다.

[계획 확인](review344b_plans.json), [검사·소스 해시](REVIEW_344b_FIXES_VERIFICATION.json)에
고유 테스트 **520개 최종 통과**, 기존 sandbox 프로세스 권한 검사 **1개 제외**를 기록했다.
초기 6개 실패를 수정한 뒤 29개 및 workflow 17개를 재검증했고 중복은 한 번만 셌다.
재검토 19개에는 이전 strict xfail 5개가 모두 포함된다. frozen fixture 3개, 386파일/8 shard coverage,
v63/등록부 불변성, 미디어 크기, diff 검사를 통과했다. 초기 검사 실패 로그도 보존했다. 가짜 렌더 검사 5개는 새 preflight에서
먼저 막혔고, 병합 후 workflow 개수는 44에서 45로 갱신했다. 관련 검사를 다시 통과시킨 뒤 커밋한다.
`scripts/run_ci_tests.py`에는 재검토 테스트를 추가했고 `.github/workflows`는 수정하지 않았다.

물리·MuJoCo 컴파일·렌더·모델 호출 0회. 새 실험/학습/평가 코호트가 없어 TensorBoard 재변환은
하지 않았다. 기존 일정·raw·스냅샷은 보존했으며 Drive는 사용하지 않는다.
`/private/tmp` extraction 디렉터리는 만들지 않았다. PR #344는 draft로 유지하고 병합하지 않는다.
