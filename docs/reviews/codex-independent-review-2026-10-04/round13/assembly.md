# R13 · D5/v92 측정 조립기의 검토 경계

이번 추가 범위는 완료된 측정 수집의 reader → 수치 fitting → 부분 조립 → loader 입장이다. main 소스 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`를 읽었고, 공식 compare로 현재 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`까지 이 코드가 동일함을 확인했다. **이 경로에서 새 결함을 확정하지 않았다.** 원본 calibration/held-out 결과를 읽거나 실제 수집·fitting 실행으로 다시 점수화하지 않았다.

## 실제 읽은 범위

전체 파일: `scripts/assemble_final_pair_calibration_v92.py`, `scripts/final_pair_calibration_v92_io.py`, `scripts/final_pair_calibration_v92_motion.py`, `scripts/final_pair_calibration_v92_camera.py`, `scripts/final_pair_calibration_motion.py`, `scripts/final_pair_calibration_camera.py`, `harness/zone_final_pair_calibration_v92_contract.py`.

부분 파일: `scripts/final_pair_calibration_io.py`의 `Inputs` 및 시간 검증, `scripts/validate_consumer_criterion_b.py`의 고정 criterion/plan 생성, 관련 v92/assembly 테스트의 합성 fixture·계약·오차/음성 대조. 테스트 이름/관련 body를 확인한 것과 실행한 것을 구분한다. 이 문서의 검토는 **source-only**이며 해당 pytest suite는 새로 실행하지 않았다. 별도 [V2 stale metric 반례](stale-metric.md)만 실제 함수를 실행했다.

| 계약/의심 | 소스에서 확인한 경계 | 판정 한계 |
| --- | --- | --- |
| 완료되지 않은 수집이 fit에 들어가는가 | `load_collection`은 collection/case 완료·UNQUALIFIED·source unchanged, 계획/번들/사례 일치, 파일 집합과 각 hash를 검사 | 수집 완료 선언과 원본 감사 경계. 실제 측정 품질 통과 선언 아님 |
| 같은 숫자 timestamp면 camera label과 pose가 같은 상태인가 | 저장 trajectory qpos/qvel로 현재와 pre-substep chassis를 별도로 재구성하고, pose와 camera label을 각 시각 상태에 비교 | 해당 integrator·timestep·기록 schema로 제한됨. 정지 샘플만으로 시간 정합성을 증명한다는 주장이 없음 |
| fit/validation이 섞이는가 | step 창으로 mean/noise를 fit하고 PRBS 창으로 수치 기준을 검사; axis support와 각 horizon 창 수를 요구 | 같은 수집 안의 시간 블록 분리. 독립 새 cohort·임무 성공 증거가 아님 |
| loaded 표본 선택 뒤 양쪽 식별 지지가 사라지는가 | `selected_segments` 뒤 robot별 signed step/PRBS와 stop·두 ramp·saturation 지지를 다시 요구 | 실제 입력이 이 gate를 통과하는지는 미확인 |
| HIGH 카메라 평균이 다른 자세까지 확장되는가 | v92 HIGH camera window를 half-open으로 제한하고 settled drive/arm·load mask·등록 자세를 검사; loader는 HIGH center key만 허용 | 일반 저자세 보정으로 승격하지 않음 |
| 서로 다른 collection SHA를 한 SHA로 오인하는가 | metadata의 `collection_sources`에 unloaded/fine/loaded를 각각 기록하고 loader가 세 키를 요구 | 실제 provenance 파일을 여기서 개봉/재검증한 것은 아님 |
| supplied B score가 full calibration을 승격하는가 | `optional_evidence`는 JSON을 증거로만 보존하고 `axis_candidates_qualify_full_profile=false`; unloaded section은 명시적으로 거절 | 의도된 미완료 관문. 공급된 pass를 보고 `MEASURED_SIM` 가능이라고 해석하면 안 됨 |
| 부분 값이 기본값으로 채워져 measured가 되는가 | required field가 없거나 section 미승인 시 null+missing; 모두 채워져도 각 지도에서 실제 loader 검사를 요구 | schema acceptance는 물리 성공·P03/carry 인수와 별개 |

핵심 소스: [조립의 unloaded 거절](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/assemble_final_pair_calibration_v92.py#L194-L216), [부분 조립과 loader 호출](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/assemble_final_pair_calibration_v92.py#L73-L114), [measurement reader](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/final_pair_calibration_v92_io.py), [motion fit](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/final_pair_calibration_v92_motion.py), [최종 loader 계약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_final_pair_calibration_v92_contract.py).

실행 막힘을 해석할 때 D5의 PARTIAL과 현재 DEV_PILOT의 제어 실패를 합치면 안 된다. 이 조립기가 요구하는 complete unloaded/scalar-stop 제품은 축별 기존 후보와 다른 산출물이다. 기존 기준을 바꾸거나 이미 본 held-out 자료를 다시 튜닝에 쓰는 것을 권하지 않는다. 새 증거가 필요한 부분은 완성된 제품의 identity·독립 승인이고, source-only 검토로 비어 있는 측정치를 채울 수 없다.
