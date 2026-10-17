beamact2의 안정 명령 구간 회귀 잡음과 자기 wheel/pulse 이력 마스킹을 점검하기 위해, 기본 off ACT에 wheel 3분류와 최근5개 명령 이력을 넣었다. A(이력 유지)·B(wheel/pulse 마스크)를 같은 beampair8 데이터·분할·seed20261015로 최종20k씩 비교한다.

- **A 완료: 학생0/20 NOT_READY**, cap_end20·HOST_ERROR0. 누적 퍼널은 접근16→정렬0→READY0→파지0→3초들기0이다. 검증 wheel MAE0.022876 vs persistence0.023129, 전환 지점45.6% 개선이다. pulse/PWM 오차와 폐루프 성공은 개선됐다고 주장하지 않는다.
- 번호표만 바꾼 동일40개 cold-start 입력에서 첫 wheel 변화3/40·chunk 변화6/40. 8329001은 배정 끝까지 접근했지만 정렬 조정을 반복한다. 낮은 초기 민감도만으로 번호표 무시를 확정하지 않는다.
- A 공개 Release: ZIP·전체10파일 SHA·새 reference clone CPU `ready:true` 확인. B는 smoke300 저장/재로딩 뒤 기존 VM 창 step1498에서 상태를 저장했고,8h 종료 뒤 같은 optimizer/RNG로 이어간다. B 결과는 미완료다.
- 학습 소스 `4747c4144a972e348a9ae4c7bbcc769ad116106d`, 평가 소스 `5ad43e1e096822d7a4ed2e7ce720c2900e7f5ff6`. 보류20은 기존에 본 비교 세트이며 A/B·이전 코호트를 합산하지 않는다. 원본24000입력/명령·35620파일·96000 RGB참조를 확인했다.
- Mac 비물리16pass/2skip, GCP2 L4/CPU 각17pass/1skip. core/후속 도구6fdcbf010 CI 성공; 최신 기록 커밋의 CI는 진행 중이다.
- gcp2 L4 shared-load·임대·8h/idle/budget-stop 유지, 다른 작업 중단0. 원본/체크포인트 보존을 위해 디스크180GB(당시 여유50G)로 온라인 확장했다. CPU16동시·호스트합계40이하. 기본 채택·수제 파지 대체·Mac 물리/렌더/학습/GUI·LLM 호출은 없다.

[실험과 재현](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/beamact3/experiments/2026-10-16-beamact3/README.md) · [A 원본 재계수](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/beamact3/experiments/2026-10-16-beamact3/A-student-summary.json) · [A Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-a-v1).
