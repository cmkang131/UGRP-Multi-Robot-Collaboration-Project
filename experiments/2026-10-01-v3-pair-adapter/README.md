# 최종 v3 공동 운반 어댑터 — 오프라인 구현 기록

번들 `zone-final-pair-v88`, workflow `zone-final-pair-v3` 3.1.0, **DRAFT_UNSEALED**.
세 최종 v3 지도에서 b-v6h1 계열 공동 운반을 연결하고 unloaded/loaded/fine 운동·자세별
카메라 자료를 수집할 관리 경로를 추가했다. 물리·렌더·실제 모델 추론은 실행하지 않았다.
P01 reset 관찰, v2 재생 성적 또는 fake 검사를 P03·파지·운반 성공으로 승계하지 않는다.

## 소스와 번호

- 작업 시작 main: `5ba853ddc5b0e300e45f8361e98e7f9f16e08c18` (#338).
- b-v6h1 참고: #292 `266118d2c2337bbf1cff507690da131c63e2db11`.
- P01 관찰: #341 `339d281e05d80ff19bb1a78a4a9c020c9653eff6`.
- [최초 전체 PR 조회](reservation_scan.json): 관련 번들 최댓값 v86 (#339),
  zone workflow 2.19.0, 전체 workflow 3.0.0.
- [커밋 전 전체 재조회](reservation_final.json): main + 열린 PR 15개,
  관련 번들 v87 (#342/#343), zone workflow 2.20.0, 전체 workflow 3.0.0.
  이 후보는 실행 기록이 없으므로 커밋 전 v88로 바꿨다. workflow는 3.1.0.
- 검사 시점 파일별 SHA-256·환경·명령은 [검증 기록](verification.json)에 남긴다.
  실행 원시 자료는 없으며, 추후 실행기는 실제 커밋 SHA와 번들 전체 closure를 고정한다.

## 구현 범위

기존 `sim_cli`/workflow manager의 추가 catalog 기능과 표준 `FinalV3Scene`/`Scene`을 쓴다.
`configs/simulation_workflows.json`, 기존 번들·봉인 소스·봉인 테스트·`.github/workflows`는
그대로다. `scripts/run_ci_tests.py`에는 새 오프라인 테스트 파일만 등록했다.

등록된 b-v6g 코드 객체와 pair dispatch·rendezvous·status·입학 조건을 인스턴스별로
감싸고 b-v6h1 계열 margin/loaded yaw gate/p2f를 연결한다. v3 FK·실측 camera transform·
운동 gain/lag/deadband·하중 불확실성·beam yaw fit을 쓰는 새 변형이다.
v2 0.948 보정, v2 자세별 camera/FK, v2 운동 fit은 주입하지 않는다.

학생 입력은 자기 RGB·정적 지도·자기 발행 명령·전달된 enum 메시지뿐이다.
입자 초기화는 정적 dock 영역으로 한 번 수행하고 seeded robot→row 배치를 쓰지 않는다.
P03는 같은 PF를 보존하며 old fix receipt를 무효화한 뒤 정지 관찰·RGB 재정렬·재파지를
잇는다. 0.16 SIM초 지연을 유지한다. geometry가 없는 blank scan은 fix를 갱신하지 않는다.

collection은 고정 명령만 실행한다. loaded 수집의 teacher station·실제 관절·접촉·빔 궤적·
camera transform은 평가 파일에만 남는다. fixed grasp 실패/낙하/정지 표본도 보존한다.
수집 완료는 `COLLECTED_UNQUALIFIED`이며 실측 fit이나 실제 하중의 승인이 아니다.
요청 schedule·own JPEG·발행 명령·평가 trace·artifact hash를 함께 저장한다.

실측 파일이 없거나 해시/지도/render/필수 자세 coverage가 틀리면 학생 실행을 거부한다.
각 사례는 reset 최대 5초와 check 120초로 제한한다. P03 분모는 checkpoint 3개,
collection/운반 분모는 지도 3개이며 HOST_ERROR 뒤의 미시도 사례도 남긴다.
ENOSPC, 중단, worker 정리 실패를 성공으로 처리하지 않는다.

## 검증과 독립 검토

새 fake/offline 테스트는 모델·network·MuJoCo import를 차단한다. 세 지도 route/Scene,
GT mutation 뒤 명령 동일성, 120초 cap/분모, ENOSPC/worker 정리, 실측 계약 mutation,
PF 동일성/지연/latent resampling, 실제 pair controller 구성, per-pose 수집 coverage,
informative/blank scan, partner deadband·축별 lag 반례를 검사한다.

독립 검토에서 찾은 다음 문제를 반영했다.

1. standoff 관측에도 실측 camera projection을 연결했다.
2. 도달 불가능했던 v3 파지 반경을 정적 station 반경 0.2032 m로 수정했다.
3. 문 뒤 checkpoint를 전체 pair envelope와 5 cm 여유로 계산했다.
4. 보정되지 않는 연속 IK 대신 유한한 파지 자세와 unloaded hover 수집을 사용한다.
5. partner 명령에도 자기 명령과 같은 deadband를 적용해 pair yaw 평균을 계산한다.
6. 정렬·이동 시간 계산에도 PF와 같은 축별 lag를 적용한다.

최초 관련 검사: 268 통과/3 실패. 새 workflow 테스트 목록 누락 2건은 수정했다.
나머지 `test_parent_exit_cleans_background_child`는 샌드박스가 `ps` 실행을 거부했다.
테스트를 약화하거나 skip으로 바꾸지 않고 로컬 선택에서만 제외했다. 정상 CI에는 포함된다.
최종 재검사 수치와 독립 검토 판정은 `verification.json`을 따른다.

## 물리 담당자에게 남은 작업

[PHYSICS_HANDOFF.md](../../PHYSICS_HANDOFF.md)에 loaded/fine/unloaded 세 수집과
P03 3×120 SIM초의 잠금·세션·표준 workflow 명령을 적었다. collection→raw 판정→v3 fit·
필수 자세 보정→독립 검토 후 P03와 E2E carry를 실행해야 한다.

새 밝은 바닥에서 기존 인식망의 정확도, 무보조 파지·하중 유지, 축별 lag의 실제 적합성,
동기화·시간 예산 내 checkpoint 도달은 미검증이다. p2f는 움직인 뒤 새 fix가 없으면
정체 baseline을 잡지 못하는 기존 한계가 있으며 이 PR이 이를 해소했다고 주장하지 않는다.
명령 receipt인 `SEQUENCE_OBSERVED_UNQUALIFIED`도 물리 성공 판정이 아니다.

새 실험/영상/모델 산출물이 없으므로 TensorBoard 변환·모델 Release는 만들지 않았다.
실제 결과를 회수한 담당자가 새 snapshot과 표시를 확인해야 한다. Drive는 사용하지 않았다.
`/private/tmp`에 수동 extraction directory를 만들지 않았고 fake 테스트 임시 폴더는 자동 정리했다.

## 참고 자료

- [P01 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)
- [기본 관리 경로 #338](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/338)
- [밝은 P01/unloaded 경로 #342](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/342)
- [등록 b-v6h1 계열 #292](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/292)
- [P03 #312](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/312)
- [실행 버전 관리](../../docs/execution_versioning.md)
