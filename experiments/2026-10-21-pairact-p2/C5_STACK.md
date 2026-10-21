# pairact P2 -c5 스택 (수집용 최종 스택)

-c4 스택에 teacher 녹화 승인 수정(c3 admission `c6626187b`, 수집 사전 등록 v3의 FROZEN_CORE/FROZEN 인정)만 더한 스택입니다. 경로 계획·운반 코드는 -c4와 같습니다. 실행 순서는 `C4_RUN.md` §3과 같고 SHA만 아래로 바꿉니다.

| tree | 브랜치 | SHA |
|---|---|---|
| teacher | `dsh/pairact-p2-carrypath-c5` | `75929e7719ad98a089e3dda5251f4249d8bae511` |
| adapter | `dsh/pairact-p2-carrypath-a-c5` | `3779d9615ef6dc8e38f57ab968a14a9e45189ecc` |
| root | `dsh/pairact-p2-carrypath-r-c5` | 이 문서가 든 커밋 (`git rev-parse origin/dsh/pairact-p2-carrypath-r-c5`) |

-c4와 다른 점:
- teacher: `5d6dab139` = `c6626187b` cherry-pick(충돌 없음). `collect_recording_admission`이 수집 prereg 스키마 v2를 인정하고, 녹화 probe는 FROZEN_CORE/FROZEN, 데이터 녹화는 FROZEN만 받습니다. 이어서 `75929e771`은 테스트만 고칩니다: 녹화 승인 바이트 동일 테스트가 -c3/-c4의 `carry_route` 키워드 삽입 3줄을 허용합니다(-c4에서 이미 실패하던 테스트, 런타임 변경 없음).
- adapter: `DEPENDENCY_SHA` 1줄. root: `ADAPTER_SHA`·`TEACHER_SHA` 2줄.

검사(로컬, mujoco 없는 venv): teacher `test_pairact_p3_collect_admission.py test_grasp_act_admission.py test_pair_carry_route_c4.py test_pair_carry_detour.py test_pair_carry_teacher_warp.py` 88 passed, adapter `test_pairact_p2_adapter.py` 9 passed, root `test_pairact_p2_root.py` 12 passed.
