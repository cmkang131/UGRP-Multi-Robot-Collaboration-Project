# REVIEW_344 수정 묶음 — v88 미실행 개정

구현자 Codex. 대상 `45c4ebc43daa96542cf298cea6f69964e501ec4a`에 대한
[독립 검토: 별도 Codex, 17b54de7](https://github.com/kcm0127-dotcom/ugrp/blob/17b54de7f7440589fa5cc388a46b61f6c4c20467/experiments/2026-10-01-v3-pair-adapter/REVIEW_344.md)를 한 묶음으로 반영했다.
원문/증거는 이 폴더에 바이트 그대로 보존했다. 검토 판정은 BLOCK이며 **수정본의 독립 승인·재검토는 아직 없다**.

**v88은 한 번도 실행되지 않았으므로 같은 bundle ID/workflow 3.1.0 안에서 개정했다.**
실행된 v89(#347), 원본 v1 schedule, 봉인된 제어기/등록 검사, `.github/workflows`는 변경하지 않았다.
main `78ce7916`과 #345 `a520d9d8` 반영 뒤, 작업 중 추가 병합된 최신 main
`a2be72a8381dcc9e58e5206509ad0c64ed7f0fb3`(#303/#342/#341)도 반영했다. 물리 step·MuJoCo 컴파일·렌더·모델 추론·host lock은 0회다.

## 지적 → 수정

| 지적 | 수정 | 검증 |
|---|---|---|
| R1 P1, actual chassis를 floor로 오인 | 실측 optical→chassis와 자세/하중별 고정 chassis→floor-heading을 합성한다. XY/yaw를 제거하고 height/roll/pitch를 보존한다. 두 소비자(beam/PF)는 같은 `camera_record()`를 사용하며 floor 변환이 없으면 거부한다. 런타임 GT나 명목 wheel radius를 쓰지 않는다. | 32.36 mm 평면 교점 반례, v3 XML의 실제 링크/관절/robot_cam quaternion을 따라 만든 정적 FK, optical 축 부호, 비영 yaw/roll/pitch, 누락·NaN·반사·잘못된 frame 반례. XML은 텍스트 생성/해석만 수행했다. |
| R2 P1, gain/lag/deadband 식별 불가 | #347의 여러 크기 계단·PRBS31·0.05초 lease/평가 pose와 전체 경로 abort를 적용했다. 세 축 각각 양·음 10초 계단/1초 coast, PRBS/마지막 coast. loaded는 .006/.015/.025/.04 네 수준으로 deadband 아래, ramp 중간 둘, 포화를 포함한다. fine은 .004/.016/.028, unloaded .01/.02/.03이다. | 정확 lag 적분, log-parameter Fisher rank, gain 해석적 적합 및 deadband/drive/stop tau profile. 실제 schedule이 검사한 segment와 동일함을 검사했다. 로봇/팔/loaded 빔이 표본 사이 벽을 침범하거나 geometry/여유/이동 bound가 잘못되면 hold+중단한다. |
| R3 P2, 실행 시계 미선언 | `bundle.timing`과 `result.timing`에 reset phase, 학생 RGB/provider 0.05초, 수집 RGB 0.2초, eval 0.05초, control 0.1초/LOOK .4초/지연 .16초, 팔 0.05초 격자와 이전 physics-step gate의 차이, stabilization/보정 선택을 명시했다. | fake clock으로 0.05초 pose·arm 호출과 0.05/0.2초 capture 시각을 대조한다. PHYSICS_HANDOFF에 수치·위상·순서·부모 대비 변화가 있다. |
| R4 P2, 독립 검토 완료 출처 없음 | 기존 6개 요약은 `author_review_summary_unverified`로 바꾸고 독립 승인 근거에서 제외했다. 확인 가능한 reviewer/대상 SHA/원문/PR 댓글은 17b54de7 Codex BLOCK 검토만 연결했다. | 감사성 반례를 통과하며 PR 본문도 함께 정정한다. 이번 구현자가 독립 승인을 대신하지 않는다. |

## 보정 예산과 경계

이전 3지도×120초 반복을 **종류별 두 문 지도 1회×370초 + reset≤5초 = 최대375초**로 바꿨다.
P03의 세 checkpoint와 carry의 세 지도는 각각 120초+reset≤5초를 유지한다.
이는 수집 분모 변경이며 여러 지도에서의 보정 일반화 검증이 아니다.
loaded만 교사 station/빔 staging을 사용하고 학생 Runtime을 만들지 않는다.
낙하·하중 실패를 온라인 명령 변경에 쓰지 않으며 `COLLECTED_UNQUALIFIED`에 남긴다.
실제 geometry가 반경 .40 m, 벽 여유 .35 m 또는 substep 이동 .01 m bound를 벗어나면 수집은 중단된다.

[PHYSICS_HANDOFF](../../PHYSICS_HANDOFF.md)에 새 지도/375초 cap/시각/잠금·세션·표준 CLI 명령을 적었다.
이 작업에서는 명령의 plan만 확인하며 실행하지 않는다. 작은 물리 인수 재생도 사용자 지시 `No physics`에 따라 수행하지 않았다.

## 오프라인 식별 결과

방법은 #347 `eaeaaff05553ea02c649b4db9ff82470fe6372b5`의 정확 적분·profile 방법을 확장했다.
#348 `dba873d4b0e77e017373e5539ac077abb7c6f4b1`의 실측 보고는 선형 1차 모델의 부적합과
명령 크기별 gain, 약 0.84초 drive tau + deadband 구조를 뒷받침한다. 실측값을 loaded/fine 보정으로 채택하지 않았다.

[최종 합성 결과](identifiability_v2.json): 세 profile×세 축의 subtractive deadband 모델 rank 3,
loaded runtime ramp(c0/u1) 모델 rank 4. 모든 검사에서 20% 다른 drive tau/deadband(및 ramp knee) 대안의
최소 잔차가 가정한 0.1 mm(회전 0.1 mrad)의 5배를 넘는다. fine 전진/측면 tau 대안은 1.167/0.797 mm,
loaded는 1.583/1.112 mm, loaded ramp는 0.833 mm다. loaded ramp deadband/knee 대안은 2.306/5.422 mm다.

명령과 가정한 모델로 전체 경로를 계산한 최소 벽 여유는 unloaded/fine 0.625 m, loaded 0.442 m다.
이 수치는 로봇 반경 .4 m와 빔이 pair midpoint를 따른다는 **가정** 아래의 예측이다. 실제 경로의 안전 증거가 아니며,
실행 시 매 물리 substep의 fail-closed 중단 검사가 필수다.

**이 설계는 조건부로 식별 가능하다.** #348 실제 잔차 약 1.8 mm와 PRBS 3.4–4.24 mm는
여기서 가정한 0.1 mm보다 크다. 따라서 실제 수집에서도 동일하게 식별되거나 runtime 모델이 충분하다고 주장하지 않는다.
stop tau는 nuisance이며 빠른 정지는 20 Hz만으로 승인하지 않는다. 모델 형태·하중 유효성·잔차·holdout PRBS는 실측 후 다시 검토한다.
MEASURED_SIM 산출물은 만들지 않았다.

[초기 설계 실패](identifiability_v2_initial.json)도 보존했다. initial은 fine .004/.012/.024,
loaded .008/.02/.04, 각 크기 양·음 10초+1초 coast, 0.5초 PRBS31+2.5초 coast였다.
fine turn의 tau 대안은 0.455 mrad로 문턱 0.5 mrad 미만이었고, loaded는 ramp 중간 수준이 하나뿐이라
c0/u1 대안이 같은 응답을 냈다. initial/final은 구현 중 오프라인 설계 비교이며 실행 코호트가 아니다.
최종 four-level schedule로 이를 해결했다. 이 실패를 raw 물리 실험이나 v88 실행으로 세지 않는다.

재현(물리/모델 호출 없음, 출력은 새 경로):

```bash
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
OPENBLAS_NUM_THREADS=1 "$PY" -m scripts.check_pair_v88_identifiability --output /private/tmp/v88-design-NEW.json
"$PY" -m pytest -q tests/test_review_344.py tests/test_zone_final_pair_review_fixes.py tests/test_zone_final_pair_v3.py
```

정확한 검사 명령·결과·source/artifact hash는 `REVIEW_344_FIXES_VERIFICATION.json`에 기록한다.
기존 7 strict xfail은 7 required pass로 전환했다. 원래 R1 fixture의 expected 값도 독립된 바닥 기준
기대 교점으로 고쳐서 32.36 mm 차이를 지우는 대신 실제 변환 합성을 검사한다.
수집 cap 검사는 분모 1×375와 P03 3×125를 각각 확인한다.

임시 archive/extraction directory는 만들지 않았다. 테스트의 TemporaryDirectory는 자동 정리하며
이번 작업이 만든 `/private/tmp` 보조 파일도 종료 전에 제거한다. UGRP 규칙에 따라 Drive를 사용하지 않는다.

검사 결과: 관련 **331 passed, 1 deselected**, CI shard **66 passed**, frozen fixture 3개 확인.
기존 프로세스 자식 정리 검사는 앞선 sandbox `ps` 제한 때문에 로컬에서 제외했고 정상 CI에는 그대로 둔다.
main #345 통합 뒤 영향 검사 154개가 통과했다. #303/#342/#341 통합에서는 v87/v88 catalog·검사 목록을
모두 유지했고 workflow 수를 44개로 맞췄다. PHYSICS_HANDOFF는 v88, main의 v87, 원본 v84 순서로
각 번들 지침을 보존했다. 최신 main과 `.github/workflows` 바이트가 같다. 최종 재검사 결과는 JSON/로그에 기록한다.

TensorBoard [합성 설계 비교](http://127.0.0.1:6006/?runFilter=%5E1001-v88-review344%2F#timeseries)는
initial 실패를 포함한 20 runs/100 scalar를 EventAccumulator와 실제 서버 API로 대조했다.
[고정 카드 링크·HParams 설정·변환 기록](tensorboard_review_fixes.json)에 원본·manifest hash를 보존했다.
기존 서버의 공용 logdir를 확인하고 서버를 바꾸지 않았다. Chrome CUA `cgWindowNotFound`로
화면/고정 카드/HParams 열의 실제 표시 검증은 미완료다. 영상은 없다.

최종 main `a2be72a8` 통합 검사: **422 passed, 1 deselected**(576.24초).
이후 R1의 높이 유효성도 차체 기준 양수 조건을 제거하고 합성된 바닥 기준으로만 판단하도록 보완했다.
이 마지막 차이의 XML/반례/변환/보정 mutation/provider 검사 **19 passed**(2.17초).
차체보다 낮지만 바닥 위인 카메라는 허용하고 바닥 아래 카메라는 거부한다.
통합 중 충돌 정리에서 생긴 두 문법 수집 오류와 복구/재검사 기록도 삭제하지 않고 보존했다.
