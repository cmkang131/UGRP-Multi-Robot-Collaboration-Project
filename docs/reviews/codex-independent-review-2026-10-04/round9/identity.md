# 현재 v100 실행 identity 경계 — 한정 반박과 남은 범위

2026-10-04, source `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. **이 경계에서는 새 결함을 확정하지 않았습니다.** 실제 CLI→bundle→case→backend의 source를 읽었으며 새 물리·모델·렌더·trial 실행이나 기존 raw/outcome 검토는 하지 않았습니다. 전체 provenance 무결성 인증이 아닙니다.

| 의심 | 실제 caller에서 확인한 방어 | 판정 범위 |
|---|---|---|
| expected SHA와 다른 코드를 실행할 수 있는가 | [CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_pair_llm.py#L109-L129)가 실행 전 [check_source](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_final_environment_checks.py#L31-L37)를 호출합니다. HEAD 일치와 `git status --porcelain --untracked-files=all`의 빈 출력을 요구합니다. | 정상 CLI가 명시적인 source mismatch나 untracked 변경을 묵인한다는 의심 반박. source를 병행 변경하는 비협조적 프로세스까지 원자적으로 잠그는 계약은 아님. |
| calibration 이름만 같으면 다른 bytes도 허용되는가 | [CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_pair_llm.py#L108-L113)는 물리 시작 전에 [measured_calibration](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_final_pair_contract.py#L97-L158)으로 SHA와 map/model/render 계약을 검사합니다. 실제 값은 같은 calibration path/hash로 전달합니다. | 정상 measured 경로의 단순 path/hash 불일치 허용 의심 반박. 측정이 편향되지 않았거나 미지 조건에 정확하다는 검증은 아님. |
| map·parent·camera mount identity가 분리되는가 | [resolve](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_final_environment.py#L53-L90)는 map file/static hash, parent file, calibration contract, static source와 camera mount SHA를 확인합니다. v88 [resolve](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_final_pair_contract.py#L68-L80)가 자기 calibration/render 계약도 덧붙입니다. | 현재 허용 지도 조합의 선언된 identity 연결 확인. 실제 동역학·렌더 영상이 맞다는 새 실행 증거는 아님. |
| 함수 안 import가 source closure에서 빠지는가 | [source_closure](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/python_source_closure.py#L13-L73)는 AST 전체를 순회하여 함수 내부 import, relative import, package initializer를 포함합니다. v100 [bundle](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_contract.py#L164-L254)은 별도 config 목록과 평가 source 목록도 기록합니다. | 이 종류의 정적 import 누락이라는 일반 가설 반박. 문자열 기반 동적 import·별도 실행파일을 자동 발견한다는 계약은 없고, 해당 입력은 explicit entry가 필요합니다. |
| 60초 smoke가 bundle의 300초 본실행처럼 감춰지는가 | [CLI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/scripts/run_pair_llm.py#L91-L108)가 plan에 실제 cap을 적고, [case](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L160-L191)는 `case_sim_cap_s`와 `registered_case_cap_s`를 구분합니다. physics case cap을 실제 cap으로 바꾸고 그 digest를 별도 기록합니다. | 서로 다른 cap이 있다는 사실만으로 기록 오류를 추가하지 않음. 다른 arm/다른 cap 결과를 이후 분석에서 잘못 합치는지는 별도 collector 검토입니다. |

## 새 결함으로 올리지 않은 API 가설

`run_pair_case`에 전달하는 bundle과 별도 calibration/cap 인자를 고의로 불일치시키는 호출은 만들 수 있습니다. 그러나 현재 CLI와 live driver는 같은 값으로 bundle을 만들고 case에 전달합니다. 정상 caller 도달성을 입증하지 않은 임의 API 조합을 현재 실험의 provenance 오류로 세지 않았습니다.

`_v88_bundle`과 closure 파일명에는 process-local cache가 있습니다. 현재 runner는 source freeze 후 단일 실행을 만드는 계약이며 source hash는 bundle 생성 시 기록합니다. 실행 중 같은 process에서 파일을 수정하거나 별도 root를 섞는 상황이 실제 caller에서 발생한다는 근거는 찾지 못했습니다. 캐시가 존재한다는 사실만으로 stale 현재 결과를 주장하지 않습니다.

## 다음에 좁게 확인할 범위

1. 실제로 configuration-selected dynamic module 또는 외부 subprocess 경로가 바뀌는 새 실행기를 선택하면, 그 파일과 asset의 identity가 explicit entry/별도 hash에 연결되는지 확인합니다.
2. source freeze 이후 변경이나 실행 도중 calibration 교체의 실제 증거가 나오면, 검증과 사용 사이 시간 간격을 재검토합니다. 지금은 가정한 적대적 변조를 신규 결함으로 추가하지 않습니다.
3. #363 최신 HIGH controller와 v100의 기반 v88는 별개 source 계보입니다. 한 쪽 fix·물리 성공을 다른 쪽 bundle로 자동 승계하지 않습니다. 이 구분은 기존 6–8차에서 지적한 범위이며 신규 발견으로 계상하지 않습니다.

파일별 Git blob/SHA256은 `identity-source-manifest.json`에 보존했습니다. 결과 상태는 `negative`(위 의심의 제한된 source 반박)이며 전체 시스템 `passed`가 아닙니다.
