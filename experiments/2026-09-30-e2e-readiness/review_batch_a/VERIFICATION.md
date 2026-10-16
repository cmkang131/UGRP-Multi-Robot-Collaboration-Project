# Batch A 검증 기록

기준 main: `c12796676802ab54cad2f0635e3e96e911691c76`. 실제 로그/JUnit/실행용 재현 코드는 `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-a-20260930-76c6a8fe`에 로컬 보관한다. Git에는 이 기록과 코드 예시를 보존하며 raw 원격 백업이라고 부르지 않는다.

## 선별 pytest

- #303: tested `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8`, reviewed `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8`; 176 passed, 6 failed, 0 errors, 0 skipped.
  - `pr303-junit.xml` SHA-256 `3d2ed784168bd49db0031960837a34124a94829283f0b731fe1aa977d5731853`
  - `pr303-tests.log` SHA-256 `8113c9d0902f1a65413d5a190df551bea2eec6df8b9eac43c91d5b637b24fd64`
- #304: tested `0cfe29df04abead833940420f08bdd0acefdb556`, reviewed `247c264a7ff53963c7e62bd083e0b825e87d2739`; 56 passed, 0 failed, 0 errors, 0 skipped.
  - `pr304-junit.xml` SHA-256 `78f14eb32afeb1a7ca3c3f0d38a11c9ed4793adf1343b92ade7f54607c3cb0c6`
  - `pr304-tests.log` SHA-256 `c2b701116fd63e4eebf5c3de828e1f893cd889dde92c31719ccf11e796b1edb4`
- #305: tested `5a852fbfde3b0df836f3a423be29a774a9c54614`, reviewed `5a852fbfde3b0df836f3a423be29a774a9c54614`; 71 passed, 6 failed, 0 errors, 0 skipped.
  - `pr305-junit.xml` SHA-256 `b6a0be2aee6f2877fa5db00fe398ce8c06c72d46443aaee467e715f1f6921bb3`
  - `pr305-tests.log` SHA-256 `d61456b98543a7ad0ca2c1865aac0d364b35d93dd51dc20289ecd870381e8a6b`

기준 main 등록 검사: 6 passed. `base-pins-junit.xml` SHA-256 `3a2b39a25f288b050dc455afb9a2744cc783cf40bdd9ec350eb07664574d225b`.

선별 명령은 각 archive를 cwd/PYTHONPATH로 놓고 실행했다. 모든 pytest/재현 실행은 기존 Mac Python 및 공용 `run_locked` 안에서 수행했다. 아래의 returncode는 각 pytest의 종료 코드이며 failed를 숨기지 않는다.

```json
[
  {
    "pr": 303,
    "returncode": 1,
    "selectors": [
      "tests/test_zone_study_evidence.py",
      "tests/test_zone_study_eval.py",
      "tests/test_tensorboard_export.py",
      "tests/test_zone_pair_registered_source.py::test_v6e_records_current_scene_and_full_source_closure",
      "tests/test_zone_pair_registered_source.py::test_v6_rejects_stale_or_inherited_source_contracts",
      "tests/test_zone_pair_door_relax.py::test_registered_sources_are_not_touched_by_this_change"
    ]
  },
  {
    "pr": 304,
    "returncode": 0,
    "selectors": [
      "tests/test_stall_observation_contract.py",
      "tests/test_zone_pair_status.py"
    ]
  },
  {
    "pr": 305,
    "returncode": 1,
    "selectors": [
      "tests/test_zone_environment_registry.py",
      "tests/test_zone_study_source_pinning.py",
      "tests/test_zone_pair_registered_source.py::test_v6e_records_current_scene_and_full_source_closure",
      "tests/test_zone_pair_registered_source.py::test_v6_rejects_stale_or_inherited_source_contracts",
      "tests/test_zone_pair_door_relax.py::test_registered_sources_are_not_touched_by_this_change"
    ]
  }
]
```

## P06

파일 해시를 새로 계산한 복사본만 사용했고 원본 fixture는 보존했다. `accepted`는 event 변환 성공 여부다. raw 이름 `success`는 합성 fixture 디렉터리명이며 실제 임무 결과가 아니다.

```json
{
  "baseline_ids": {
    "raw_run_id": "success",
    "trial_id": "no_comm-i1_cyan_three_slots-s700",
    "scenario": "i1_cyan_three_slots",
    "seed": 700
  },
  "foreign_identity": {
    "accepted": true,
    "success": 1.0,
    "run_id": "success",
    "scenario": "unrelated-scenario",
    "seed": 987654,
    "request_images_verified": 3
  },
  "foreign_order_ids": {
    "accepted": true,
    "success": 1.0,
    "run_id": "success",
    "scenario": "i1_cyan_three_slots",
    "seed": 700,
    "request_images_verified": 3
  },
  "missing_terminal": {
    "accepted": true,
    "success": 1.0,
    "run_id": "success",
    "scenario": "i1_cyan_three_slots",
    "seed": 700,
    "request_images_verified": 3
  },
  "missing_image_refs": {
    "accepted": false,
    "type": "TrialError",
    "error": "request_archive req_call_0001_r1: archived request 'req_call_0001_r1': content does not hash to request_sha256; archived request 'req_call_0001_r1': tokens.images 1 != recount 0; archived request 'req_call_0001_r1': billed_tokens.images 1 != 0"
  }
}
```

## P01 legacy

main은 fake factory 1회 호출, #305는 factory 호출 전 거절.

```json
{
  "base": {
    "accepted": true,
    "factory_calls": 1,
    "map": "zone_wide_door_tags_v2_dock_v3"
  },
  "pr305": {
    "accepted": false,
    "factory_calls": 0,
    "map": "zone_wide_door_tags_v2_dock_v3",
    "exception": "ValueError",
    "error": "unknown tagged zone map: zone_wide_door_tags_v2_dock_v3"
  }
}
```

## P01 and P292

최초 검사에서는 후보 계약 계산 후, 변조 전 `zone_wide_door_tags_v2_dock_v3` resolver가 unknown tagged map으로 거절됐다. 이 실패를 A305-1로 보존했다. 후속 봉인 반례는 일반 legacy `zone_wide_door_tags_v2`를 써서 도크 오류와 분리한다.

새 registry status를 변경했는데 후보 계약은 바이트 수준으로 같았고 resolver는 실패했다. 후보의 269개 source 목록에 registry와 final catalog는 없고 Python resolver 모듈만 있다. 변조한 임시 파일은 원래 바이트로 복구했다.

```json
{
  "candidate_same": true,
  "candidate_sources": 269,
  "registry_pinned": false,
  "final_catalog_pinned": false,
  "registry_source_module_pinned": true,
  "valid_before": true,
  "after_resolver_error": "invalid unsealed environment registry"
}
```

## Merge tree

각 명령은 exit 0, 아래 tree ID를 반환했다. 텍스트 충돌 없음이며 결합된 전체 테스트/물리 통과가 아니다. #304의 빈 커밋 전후 tree는 같아서 합성 내용도 같다.

```json
{
  "merge-305-299": "c6041c2ec5f80b080dbe751f57abd0821197bc87",
  "merge-304-301": "c99d184de94888d1a09aa3b5bc43497dcecf0b9f",
  "merge-305-301": "d2bcde70af334e593a9c11c7d8637e5c7d5d80e0",
  "merge-304-305": "6c0d3ba8b85d1dc61e0066b7e0f9b306ff286573",
  "merge-304-299": "edeffba427dcb519297e41fad82b52d56cc2591f",
  "merge-303-292": "b547adb0bd277bf2b35238dbb96bf9e022556702",
  "merge-303-301": "5f644842187c6756560ba1f380d4c40cf24eb441",
  "merge-303-299": "1f9fc0a5d0fbb13f90173878695cc8fa53ed04a4",
  "merge-303-305": "ef1056cd629be3aa8cf3ed1d6a689c4798a55289",
  "merge-303-304": "c63e86e4ff35e4c52d50d719abfb03b7c64d07cf",
  "merge-305-292": "2d5126c7aacd9918ddc4bd8c36650112cf1df4fb",
  "merge-304-292": "8fbe7af6272584174905680b923a2fcfe39df061"
}
```

## CI 및 제외 범위

#303/#305 `offline-regressions`: FAILURE. #304 `247c264a`의 `offline-regressions`: QUEUED(이 검토의 마지막 조회 기준). #304의 MERGE는 코드 범위 의견이며 실제 병합은 필수 CI 통과 이후다. 전체 CI API 응답은 로컬 `pr*-final.json`에 보존했다.

반례 원본 출력 해시:
- `repro303.json`: SHA-256 `f8621437c6af748d9f3f67a84469ae80c69002c7872f18e061c2663e42b14e26`
- `repro305-legacy.json`: SHA-256 `2e709431e9877ff23d4b7679cfbac7e393ccacd428cc40bd380b264d6a8ccf8a`
- `repro305-292.json`: SHA-256 `f3cb9b0660bb090e9217144954c82090e5e7877d8f37233a87fb1ce1164ba945`

- 새 연구 cohort/물리 실행/렌더/실제 비전·LLM 호출: 0. 새 D1 감도, robot 성공, 비용 측정은 없음.
- TensorBoard는 temporary synthetic event readback만 수행. 공용 snapshot/server/UI/영상 playback은 검사하지 않음.
- report/reproducer 문서만 변경하므로 review PR은 문서 전용 CI 대상이다.
- 로컬 선별 회귀·새 반례·GitHub CI 로그를 분리해서 기록했다. 전체 결합 회귀는 실행하지 않았다.
