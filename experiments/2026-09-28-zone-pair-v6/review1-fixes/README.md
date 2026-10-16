# PR #246 검토 1 수정 기록

기반 HEAD `837a110ae15e46a45291100f161b3a33c83eb3d9`, 브랜치 `codex/zone-pair-beam-relative`.
사용자가 지정한 `codex-246-review1.md`의 P1 3건과 P2 의존성 목록을 다룬 미커밋 코드 변경이다.

## 변경과 반례

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 접근 이동 | PF σxy=1 cm로 `.12 × .15 s` 전진을 통과시켰다. 동일 위치 `(1.83,-1.8,0)`의 전역 σxy=6 cm로 현재 여유는 19.619 mm이나 이동 경로는 위험하다. | approach/reapproach에도 전역 envelope를 반환해 실제 motion guard가 `hold`+abort한다. arm sweep도 동일 envelope를 받는다. |
| yaw 도달 범위 | 명령 없는 0→90° informative receipt가 anchor와 `fix_t`를 교체하고 σyaw=.01을 유지했다. | 원형 yaw 거리와 명령 회전 bound+양쪽 불확실도를 검사해 첫 점프를 거부한다. XY 밖 재획득에도 정지·compact informative fix 3회 일치 검사를 요구한다. |
| 부분 시야 정렬 | 표식 없는 이상적 빔의 grip 33 cm에서 bound=4.062 cm. 정상 `.08 × .3 s` 이동 뒤 30.6 cm에서 search bound=7.917 cm, p45에서도 8.044 cm여서 준비되지 못했다. | 기존 `search→p45` 전환 뒤 관측 가능한 가까운 끝과 paired edges로 grip=30.707 cm, bound=3.649 cm를 측정하고 다음 production 정렬 명령을 발행한다. |

[반례 전후 JSON](counterexamples.json)은 `reproduce.py`가 기반 SHA의 Git blob을 메모리에서 읽어
현재 코드와 대조한 결과다. 원본 소스를 checkout/복원하거나 기존 기록을 덮어쓰지 않았다.
RGB는 고정 wrist ray와 바닥 위 600×40 mm 빔 평면을 해석적으로 투영한 영상이다.
물리 궤적·완주·센서 정확도 측정 또는 전체 PF/RNG episode 재생이 아니다.

부분뷰 갱신은 이미 전체 형상으로 식별한 같은 segment, 보이는 가까운 끝, 먼 쪽 FOV clip,
기존 폭 조건, 4개 이상 paired-edge strip과 6 cm span, 기존 association 검사를 모두 요구한다.
5 cm/3° 준비 임계값, 단안 depth bias, 15 mm/1° 바닥값은 유지한다. 부분뷰는 전체 형상 식별의
30초 수명을 연장하지 않으며 단순 clipped/occluded 지지 관측은 bound를 줄이지 않는다.
미식별·다른 segment·만료·이동한 빔·가려진 끝·중복 프레임을 검증한다.

전역 재획득은 서로 다른 receipt 시간 3개, 첫/마지막 0.3초 이상, 인접 1초 이하,
첫 후보 대비 XY 3 cm/yaw 3° 일치를 요구한다. 명령·비정보 관측·불일치·긴 공백은 재시작한다.
중복 읽기는 횟수가 아니며, 명령으로 도달 가능한 회전과 ±π 경계의 원형 거리는 허용한다.
이 검사는 개발용 일관성 가설이며 절대 위치 정확도 보정은 아니다.

P2는 `a+b`에서 목표 장애물 제외에 full-shape fallback을 추가했다. `allow_shape_identity`는
기존 A 플래그에서만 나온다. 두 끝이 보이는 전체 형상과 기존 주문 association·색·성분 전체 지지
조건을 만족해야 하며 잘못된 목표와 혼합 장애물은 제외하지 않는다. v5h/b-only 동작은 유지한다.
실제 tag provider와 post-close band 의존성은 [상위 README](../README.md#tags_temporary-전용-의존성)에
목록화했다. 실제 markerless provider는 #216 트랙이며 형상 grip/hold receipt의 물리 검증도 남는다.

## 검증 방법

`run_tests.py`는 요청된 8개 glob 전체 75개 파일을 수집한다. `test_zone_own*.py`도 포함한다.
기존 Mac 환경, `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 사용하고 finally에서 임시 폴더를
삭제한다. `tests.pose_provider_no_physics`가 물리 step·실제 비전 worker·네트워크를 차단한다.
실제 물리가 필요한 기존 host 테스트 2개는 이 플러그인 사용 시 명시적으로 skip한다.
Python 자식에는 기존 `source-regression/step_tripwire.py`를 sitecustomize로 상속한다.
잠금은 사용자 허용에 따라 획득하지 않았다. 결과는 `pytest.log`, `pytest.xml`, `test_execution.json`,
최종 무결성 대조는 `validation.json`에 남긴다.

초기 좁은 회귀는 47 passed / 3 deselected(해시 갱신 전 DRAFT prepare 3건 제외)였다.
첫 새 테스트 작성 단계의 실패 4건은 약 19 mm 여유의 소수점 기대값 2건, 읽기 전용 policy property
fixture 1건, occluded support-only 관측의 기존 동작 기대값 1건이었다. fixture를 바로잡았으며
production 안전 임계값은 바꾸지 않았다. 최종 확대 회귀에는 DRAFT prepare도 포함한다.

재실행(기존 로그는 보존하고 record 경로를 새로 지정):

```sh
mkdir -p /private/tmp/v6-review1-no-physics
cp experiments/2026-09-28-zone-pair-v6/source-regression/step_tripwire.py /private/tmp/v6-review1-no-physics/sitecustomize.py
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
V6_STEP_AUDIT=/private/tmp/v6-review1-step-audit.log \
PYTHONPATH=/private/tmp/v6-review1-no-physics:. \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
experiments/2026-09-28-zone-pair-v6/review1-fixes/run_tests.py
```

프로젝트 Git 커밋·push·PR 수정·병합은 하지 않는다. 기존 registry 테스트는 삭제되는 basetemp의
임시 테스트 저장소 안에서만 commit fixture를 만든다. 작업 시작 시 fetch는 공유 FETCH_HEAD 쓰기
제한으로, gh PR 조회는 네트워크 제한으로 실패했다. 원격 최신 상태는 이번에 확인하지 못했다.
기본 main은 읽기만 했으며 갱신하지 않았다. UGRP 예외에 따라 Drive를 사용하지 않는다.
이번 결과는 코드 회귀이므로 물리/학습/평가용 TensorBoard snapshot은 새로 만들지 않는다.

추가 코드 점검에서 provider가 현재 정보가 없는 프레임에도 `last_fix_quality`를 보존함을 확인했다.
재획득 후보는 이 이전 receipt만 보고 연속성을 유지하지 않도록 현재 품질의 명시적 거부도 검사한다.
미래/누락 receipt도 후보를 끊으며, 정지 여부는 수신 시각 대신 fix 자체의 시각과 명령 종료+0.2초로
검사한다. 보완 전 retained/future/missing 반례 3개를 직접 재현했고, 보완 후 정지 유예 반례까지
4개가 통과했다. 보완 전 소스를 이미 로딩한 1차 전체 회귀는 `first-pass/`에 보존하고,
최종 소스의 전체 75개 파일을 별도로 다시 실행한다.

## 최종 결과

**75개 파일, 2695 passed / 0 failed / 2 skipped, 382 subtests passed** (pytest 318.82초).
Skip은 위의 실제 물리 host 테스트 2개뿐이다. 물리 step·실제 비전 worker·네트워크 sentinel은
모두 0이며 Python 자식 step tripwire 호출도 0이다. `.pytest_tmp`는 삭제했다.

`verify.py`로 현재 등록 소스 65개·scene 계약, 6회 모두의 DRAFT 실행 거부, 이전 등록들과
frozen M2/tag provider 원문 14개 불변, HEAD 유지(`837a110ae15e46a45291100f161b3a33c83eb3d9`)를
대조했다. [최종 검증 JSON](validation.json), [전체 로그](pytest.log), [JUnit](pytest.xml)을 따른다.
미커밋 로컬 수정이며 원격 CI/PR 갱신·물리 준비/완주 판정은 이 결과에 포함하지 않는다.
