# 최종 환경 v87 — 밝은 무그림자 렌더 등록

2026-09-29 사용자는 연구 코호트에 `floor_light_v1`을 쓰고 그림자가 있는 과거
결과와 합산하지 않기로 결정했다. 코디네이터가 이번 작업에서 이 결정을 재확인했다.+[P01 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)의
`339d281e05d80ff19bb1a78a4a9c020c9653eff6` 기록은 v84가 기본 렌더에 고정되어
어두운 자기 영상을 수집했다고 밝혔다. 이 기록을 새 밝은 조건의 결과로 재분류하지 않는다.

**새 물리 결과가 아니라 실행 등록과 가짜 백엔드 검사다.** 소스 기준은
main `5ba853ddc5b0e300e45f8361e98e7f9f16e08c18`(#338 병합), 작업 브랜치는
`codex/final-env-floor-light`다. 폴더 이름 `integ-final-env-v86`과 실행 번들 번호는 다르다.

## 번호와 보존

- 선택 전 main + 열린 PR **16개 전체**를 조회했다. #339가 `zone-target-v86` 및
  `zone-target-checks` **2.19.0**을 이미 쓰고 있어 **v87 / 2.20.0**을 선택했다.
  RGB RUNNABLE_ID도 함께 조회했으며 전체 관련 bundle 최대는 v86이다.
  별도 M1 memory-v3 workflow의 3.0.0은 통합 2.x 계열과 구분했다.
  [원래 조회](reservation_scan.json), [main + 열린 PR 13개 재확인](reservation_recheck.json).
- `zone-final-environment-v87` / `zone-final-environment-floor-light-check` **2.20.0**은
  별도 catalog fragment에 등록했다. v84의 `zone-final-environment-check` **2.17.0**은
  원래 ID·파일·내용 그대로 재현용으로 보존한다. 추가 항목 때문에 전체 catalog 해시는 변한다.
- v84의 3지도 × 3 check 생성 번들 **9개**와 소스/보호 파일 **162개**의 해시를
  [보존 기록](v84_preservation.json)에 남겼다. 해당 소스·등록부·원래 보정 계약·측정 계획은
  수정하지 않았다. 봉인된 두 테스트와 `.github/workflows`도 수정하지 않았다.

## 변경 범위

새 어댑터는 v84의 지도, masterpi_v3, cargo_noslip_v1, weld OFF, 초음파 OFF,
카메라 배치/FOV/해상도, 물체 외관, reset, 고정 명령 궤적과 관찰 주기를 재사용한다.
`sim.render_profile.install`로 기존 `floor_light_v1`을 장면에 적용하고,
`verify_model`로 적용된 그림자·반사·광원·바닥 텍스처를 검사한다. 실패하면
HOST_ERROR로 닫고 생성한 world를 정리한다. 장면 manifest와 eval-only 적용 기록에
프로필 이름·정의 hash·실제 적용값을 남긴다. 프로필 자체의 정의·값은 바꾸지 않았다.

새 보정 계약 `configs/calibration/zone_final_v3_floor_light_contract.json`은 원래 계약에서
render_profile만 바뀐다. 측정값은 모두 null로 남는다. 새 번들의 provider 항목은
v84/default P03의 미활성 메타데이터로 보존하며 밝은 조건의 provider로 바꿔 부르지 않는다.
P03는 보정 파일 인자가 있어도 v3 chain adapter 부재로 실행을 거부한다.
학생/provider/LLM은 이 수집 경로에서 생성하지 않는다. 허용 학생 입력은 자기 RGB,
정적 지도, 자기 발행 명령 이력, 전달된 메시지만이다. GT는 eval_only 보정 표적에만 남긴다.

[PHYSICS_HANDOFF.md](../../PHYSICS_HANDOFF.md)에 코디네이터가 실행할 두 명령을 적었다.

| 수집 | 지도/상한 | 분모·기록 |
|---|---|---|
| P01 | 3지도 × 정지 30 SIM초 + reset 각 ≤5초, 총 **≤105 SIM초** | 3지도, COLLECTED_UNQUALIFIED |
| unloaded 보정 | 같은 3지도 × 120 SIM초 + reset 각 ≤5초, 총 **≤375 SIM초** | 고정 `configs/final_environment_measurement_v1.json`, 원시 자료만 |

unloaded 수집은 loaded/fine 측정·fitting·MEASURED_SIM 생성·P03 연쇄를 완료하지 않는다.
두 수집은 별도 output으로 실행하고 과거 raw를 덮어쓰지 않는다. 실제 실행 전 소스를
커밋하고 SHA를 고정하며 코디네이터의 소유 잠금 아래 실행한다.

## 검증

- 첫 새 경로/v84/검토 회귀: **62 passed**. 호스트 잠금 없는 fake/offline pytest다.
- [변조 검사](mutation_check.py): **11/11 검출**, 각각 목표 pytest exit 1 확인,
  수정 파일 전부 바이트 복원. [결과](mutation_results.json).
- 렌더 적용 누락, 적용 검사 우회, 렌더 기록 누락, 생성 실패 정리 누락,
  물리 조건 변경, 어두운 보정 계약, P03 허용, 기존 어두운 백엔드 호출,
  unloaded 수집을 30초로 축소, workflow/CI 등록 누락을 검사했다.
- 변조 복원 뒤 새 경로·manager·봉인/pinning·P01/P03·CI shard·순수 XML 검사:
  **271 passed, 1 failed**. 유일한 실패는 기존 manager 자식 정리 검사의
  `ps` 실행이 sandbox에서 `PermissionError: Operation not permitted`로 거절된 것이다.
  해당 테스트는 변경하지 않았으며 일반 CI에서는 제외하지 않는다.
  manager의 나머지 경로를 별도 실행하여 **17 passed, 1 deselected**를 확인했다.
- frozen fixture 사전 검사 3개 존재, 8개 CI shard 목록에서 새 테스트 파일 정확히 1회 포함.
- handoff bash 블록 5개의 `bash -n` 검사 통과. SIM 명령은 실행하지 않았다.

최종 관련 회귀·소스 해시·환경은 [verification.json](verification.json)에 기록했다.
검사별 수치는 중복을 포함하므로 합산하지 않는다.
물리/SIM/렌더/실제 worker/모델/학습은 **0회**이며 v87의 실제 영상 밝기,
실제 reset/수집 완주와 코디네이터의 자료 판정은 남아 있다. 새 실험 코호트가 없어
TensorBoard 변환/화면을 만들지 않았다. 코디네이터가 실제 결과를 회수한 뒤
새 snapshot을 만들고 실제 로딩을 검증한다. Drive는 사용하지 않는다.

## 참고 자료

- [P01 #341 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/339d281e05d80ff19bb1a78a4a9c020c9653eff6/experiments/2026-10-01-p01-final-env-check/README.md)
- [#338 원래 인계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/5ba853ddc5b0e300e45f8361e98e7f9f16e08c18/PHYSICS_HANDOFF.md)
- [9/29 렌더 정의·기록](../2026-09-29-render-profile/README.md): 당시 opt-in이라는 설명은
  기록 당시 범위다. 이번 코디네이터가 전달한 연구 코호트 결정을 대체하지 않는다.
- [실행 버전 관리](../../docs/execution_versioning.md)
- [#339 범위/번호 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/339#issuecomment-5918078824)
