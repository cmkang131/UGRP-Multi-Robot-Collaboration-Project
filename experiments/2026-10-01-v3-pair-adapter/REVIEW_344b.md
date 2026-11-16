# PR #344 수정 확인 — MERGE AFTER FIXES

- 대상: `45c4ebc43daa96542cf298cea6f69964e501ec4a` → **`b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a`**. 미실행 v88의 수정만 검토했다.
- 검토자: 독립 Codex, `codex/review-344`. 앞선 검토는 `17b54de7f7440589fa5cc388a46b61f6c4c20467`이다. 구현은 수정하지 않았다.
- 기준: `origin/codex/review-347`의 `cfc562daf80fcc4dddba1493ab3db0cefb1befe3` / `REVIEW_347.md`. 검토 중 #347·#348이 병합되어 최종 main은 `2c45b137c480eecff3dac871277cf48914dd5cf4`다.
- 물리 step·MuJoCo 컴파일·렌더·실제 모델 호출 **0회**. archive를 별도로 풀어 정적/가짜 backend/NumPy 검사만 했다.

**기존 7개 반례는 수정됐고, 되돌리기 7개도 모두 의도한 assertion 실패를 냈다. 남은 P1 1건과 P2 1건을 아래 한 묶음으로 전달한다. 현재 후보의 병합·수집 인수에는 동의하지 않는다. 최종 운동 모델 채택을 이번 PR에 요구하지 않는다.**

## 남은 수정 두 가지

### B1 · P1 — 전체 경로의 운동 범위가 없는데 수집을 허용한다

위치: `scripts/run_final_pair_v3.py:144–160`, `scripts/run_final_pair_v3.py:42–59`,
`scripts/check_pair_v88_identifiability.py:135–159`.

세 수집 모두 계획이 `runnable=true`, `blocked_on=[]`다. `run_case()`도 cap/timing만 확인하고
backend를 만든다. 가짜 생성기에 표식을 넣으면 **unloaded/fine/loaded 모두 생성기까지 도달**한다.
실제 backend나 물리 실행 없이 재현했다. 운동 불확실성 범위·독립 근거·그 범위의 전체 경로 여유를
실행 전에 확인하는 단계는 없다.

`enrich()`의 0.625 m / 0.442 m는 각 축의 합성 parameter 한 점과 빔이 pair midpoint를 따른다는
가정에서 계산한 경로다. 이 함수 자체도 실행 진입 조건이 아니다. 매 substep 중단 검사는 유용하지만
명령 전체를 수집할 수 있다는 사전 근거를 대신하지 않는다.

독립 수식의 구체적인 민감도 예: loaded의 전진 gain만 1.576→2.5, 나머지는 같은
τ=0.84 s / stop τ=0.08 s / deadband=0.005로 두면 r2 원판–벽 최소 여유가
**0.442121→0.143300 m**가 된다. 0.35 m 중단 문턱은 **85.75 s**, 최소는 89 s다.
이는 **가상의 loaded 모델에 대한 반례이며 실측·적합·충돌 관측이 아니다**.
이 모델을 안전 범위 밖으로 제외할 근거도 현재 수집 계약에는 없다.
#348의 unloaded 한 실행을 loaded/fine/turn의 운동 범위로 대신하지 않았다.

수정: #347과 같은 원칙으로, 근거가 연결된 운동 범위와 전체 경로 검증이 없으면
**계획부터 실행 불가로 표시하고 backend 생성 전에 거부**한다. 양/음 비대칭·stop/coast·축간 오차,
명령 경계 사이의 이동, loaded 양쪽 로봇·빔을 포함해야 한다. 근거 없는 최종 모델을 채워 넣을 필요는 없다.
기존 substep hold/abort는 유지한다. #347 수정본 `23ebc3c6`은 현재 bounds 미확정 상태를
그대로 보존하고 실행을 차단하며, 이제 main에도 들어가 있다.

반례: `test_collection_requires_qualified_full_path_before_backend` **strict xfail 3개**.
기대실패 표시를 끄면 세 개 모두 위 `runnable/backend_calls` assertion에서 실패한다.

### B2 · P2 — 로봇·빔 형상의 비정상 z 좌표를 검사 전에 버린다

위치: `sim/final_pair_v3.py:121–128`, `harness/zone_final_pair_clearance.py:66–79`.

`geom_xpos[ids, :2]`만 넘기므로 형상의 z가 NaN이어도 뒤의 `isfinite()`를 통과한다.
정상 guard 직후 **두 번째 로봇 또는 빔의 z 한 값만 NaN**으로 바꾸면 각각
`_clearance_min=0.4518`, 예외 없음, **hold 없음, abort 기록 없음**이다.
평면 거리 계산에 z를 쓰지 않는 것과 원래 형상 자료가 유효한 것은 별도 조건이다.
유효하지 않은 3차원 형상을 안전한 입력으로 인정하면 안 된다.

수정: XY로 투영하기 전에 선택한 모든 형상의 **xyz 전체·반경·계산 거리**를 유한성/유효성 검사하고,
잘못된 값 하나라도 있으면 기존 hold+abort 경로로 종료한다. #347의 두 번째 형상 NaN 지적과 같은 기준이다.
두 번째 형상의 XY NaN·반경 NaN·음수 반경은 이번 구현에서 이미 정상적으로 거부된다.

반례: `test_nonfinite_geometry_z_is_rejected_before_projection` **strict xfail 2개**.
기대실패 표시를 끄면 두 개 모두 `reason/held` assertion에서 실패한다.

## 기존 R1–R4 수정 확인

| 항목 | 확인한 경로와 되돌리기 |
|---|---|
| R1 카메라 frame | `camera_record()`가 optical→actual chassis→floor-heading을 합성한다. beam과 실제 PF provider가 같은 변환을 쓴다. 32.36 mm 교점, XML의 고정 transform, roll/pitch, 누락/잘못된 frame, 바닥 아래 카메라 거부가 통과했다. 변환을 빼고 이전처럼 record를 그대로 반환하면 교점 assertion이 실패한다. 원래 테스트의 expected를 독립된 바닥 교점으로 고친 것은 타당하며 허용 오차는 완화하지 않았다. |
| R2 자극 3개 | old SHA의 실제 `zone_final_pair_calibration.py`를 자식 인터프리터에 다시 적용하면 unloaded/fine/loaded 세 검사 모두 실패한다. 새 일정은 단순 배율/시각 변경이 아니라 여러 크기의 양·음 10초 계단·coast·PRBS31·0.05초 lease/pose다. |
| R2 loaded gain/deadband | 이전 두 모델이 새 네 수준에서 서로 다른 응답을 낸다. 이전 schedule로 되돌리면 다시 같아져 검사도 실패한다. 새 loaded ramp의 두 내부 수준과 포화 수준은 c0/knee/gain 분리에 정보를 준다. B1/B2는 별도의 수집 허용·중단 요건이다. |
| R3 실행 시계 | bundle/result에 reset phase, RGB/provider/pose/arm 주기와 명령 전 capture 순서, 부모 대비 차이가 있다. fake clock의 실제 호출 시각·개수와 일치한다. bundle의 timing 선언을 제거하면 기존 반례가 실패한다. |
| R4 검토 출처 | 원래 6개 요약은 작성자 제공·독립성 미확인으로 분리했다. 공개된 원문은 이전 Codex의 BLOCK 검토와 정확한 대상 SHA를 가리킨다. PR 본문도 수정본 승인 미완료로 표시한다. old verification JSON으로 되돌리면 출처 assertion이 실패한다. |

되돌리기는 파일을 고치는 대신 별도 인터프리터의 모듈에만 적용했다. R4는 임시 JSON만 사용했다.
새 검사에서 import/실행 오류는 `RuntimeError`로 남기며 의도한 `AssertionError`와 구분한다.

## fine/loaded 식별 자료의 충분성

설계의 **조건부 식별성**은 인정한다. 실제 명령 배열과 분석 segment를 대조했고,
프로젝트 적분기를 호출하지 않는 닫힌 식으로 10개 합성 조건을 다시 계산했다.
응답 최대 차이는 **6.67e−16 이하**, Fisher 조건수도 일치한다. 작성자의 전체 프로파일 격자 계산도
새 출력으로 다시 실행해 `identifiability_v2.json`과 JSON 값 전체가 같은 것을 확인했다.
subtractive 모델 9개는 gain/drive τ/deadband **rank 3**, loaded ramp는 **rank 4**다.
stop τ까지 nuisance 열로 넣어도 각각 rank 4/5다.

fine은 .004/.016/.028, loaded는 .006/.015/.025/.04에서 양·음의 지속 응답을 남기므로
#348에서 드러난 명령 크기별 gain·deadband와 transients를 비교할 수 있다.
PRBS는 계단으로 맞춘 동역학의 별도 확인 구간으로 보존해야 한다.
“선형 단일 gain 모델을 최종 확정해야 병합 가능”이라는 요구는 하지 않는다.

가상의 1.8 mm 오차·AR(1) 상관시간 0.5초로 stop τ를 nuisance 처리한 국소 민감도에서
fine 전진/측면 `SD(log drive τ)`는 **3.08%/4.51%**, loaded는 **2.04%/2.91%**다.
이는 정보량 점검이며 실측 신뢰구간이 아니다. #348의 잔차를 IID 센서 잡음으로 취급하지 않는다.
loaded/fine/turn의 실제 모델 형태·하중 유효성·잔차·정지/holdout 판정은 수집 후 #346 계열 작업에 남긴다.

## 상한·경계·보존

- reset 최대 5 s, 수집 종류별 **한 지도 370 s + reset ≤375 s**. fake clock에서 7,401 pose / 1,851 RGB 시각, 마지막 시각·닫힘을 확인했다. reset 초과는 첫 capture/command 전에 거부한다. P03/carry는 기존 3×(120+5) s다.
- teacher station/빔 staging은 `calibration-loaded`에서만 설치하고 학생 Runtime은 만들지 않는다. p03/carry에는 설치되지 않으며 clearance GT도 학생 경로에서 읽지 않는다. 평가 label 변경은 학생 frame/입력을 바꾸지 않는다.
- weld OFF 선언과 활성 weld 거부, floor_light_v1의 shadow/reflection/spot/dark/missing-floor 거부가 통과했다. 이 결과는 물리적인 파지·하중 유지·P03/E2E 성공이 아니다.
- 최신 main의 v87과 모델·카메라·render·v1 schedule·봉인 소스/검사 등 **16파일 SHA-256 일치**. `.github/workflows`는 main과 diff가 없고 리뷰에서도 수정하지 않았다.
- 최종 main + 열린 PR **13개 전체**의 고정 SHA에서 harness/configs 선언을 확인했다. v88은 #344 하나, v89는 병합된 #347이며 번호 충돌은 없다. ref와 hash는 증거 JSON에 있다.

## 실행한 검사와 보관

| 검사 | 직접 확인한 결과 |
|---|---|
| 관련 offline 12파일 | **355 passed, 1 deselected**, 275.09 s |
| `tests/test_review_344b.py` | **14 passed, 5 strict xfailed**. 통과 7개가 원래 반례의 PASS와 되돌리기 실패를 함께 확인한다. |
| 기대실패 표시 제거 | B1 **3 assertion failures**, B2 **2 assertion failures**. 환경/의존성 오류가 아니다. |
| 합성 설계·독립 계산 | 10조건 전체 보고서 재계산 일치 + 별도 적분·Fisher·stop nuisance 검산. 결과/방법과 로그 hash는 아래 증거에 연결했다. |

제외 1개는 이전부터 sandbox의 `ps` 권한으로 막힌 `test_parent_exit_cleans_background_child`다.
실행한 suite에는 native/모델 import·소켓 연결 금지 guard를 적용했다. archive의 과거 Git fixture 조회에만
`GIT_DIR=/Users/changmin/projects/ugrp/.git`를 연결했다. GitHub CI 상태와 로컬 검사는 증거에서 별도로 기록한다.
검사 후 archive의 harness/sim/scripts/configs/tests **2,310파일**이 후보 Git blob과 그대로 일치했다.

[검사·ref·수치·해시 기록](REVIEW_344b_EVIDENCE.json), [독립 검사](../../tests/test_review_344b.py).
새 물리/학습/평가 코호트 없이 기존 설계의 수식과 회귀를 검토했으므로 TensorBoard를 재변환하거나 열지 않았다.
기존 raw·스냅샷·다른 작업의 실행기는 건드리지 않았다. UGRP 규칙에 따라 Drive를 사용하지 않았다.
검토용 archive와 보조 임시 디렉터리는 필요한 기록을 저장한 뒤 삭제하고 부재를 확인했다.

재현:

```sh
git archive b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a | tar -x -C <empty-scratch>
REVIEW_344B_ROOT=<empty-scratch> OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_review_344b.py -rx
# 종료 전에 자신이 만든 scratch를 삭제한다.
```
