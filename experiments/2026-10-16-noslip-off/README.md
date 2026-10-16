# nsoff — 새 실행 기본 noslip 0

사용자(2026-10-16): "noslip은 다 끈 상태로 되게 해". 기본 off 후보가 아니라 새 실행의 기본값을 변경한다.

- 접촉 실행 번들 `noslip-off-v445` ([번호 조회](reservation_scan.json)). CPU `cargo_native_v1`, MJWarp `warp_native_contact_v1`. CPU 새 프로필 및 과거 재생 예외는 (조정자 해석, 사용자 미확인).
- 공용 Warp backend는 선택한 프로필의 noslip 값과 실제 모델 값을 비교한다. frozen teacher/beam/release adapter는 생성자 초기 step 전에 프로필을 적용한다. weld OFF 검사는 유지한다.
- CPU drive v1–v7, zone cargo/최종 v3 장면, owncam/짝/지도/E2E 새 실행 기본을 native로 한다. 계약은 native도 받되 시나리오와 episode의 프로필이 같아야 한다.
- 버전이 붙은 configs·prereg·은퇴 번들·과거 실험은 수정하지 않았다([보존 확인](preservation.json)). 기록된 프로필 입력은 명시 재생이며 과거 소스 SHA와 함께 쓴다. 새 시나리오 템플릿은 `configs/*_native_v445.json`; 과거 템플릿을 덮어쓰지 않았다. 역사적 collection registry/consumer 판정기는 원본 프로필을 검증한다. 새로 만드는 final-pair/solo/S3/pair-LLM 계약은 native 기본값과 별도 contact_execution_bundle_id를 기록하며, collection 실행 계약은 새 프로필도 받는다.
- MJWarp CLI `--contact-profile legacy_noslip10`은 과거 재생 전용이다. 새 native와 noslip10, CPU와 MJWarp, 서로 다른 VM 결과는 합산하지 않는다. 물리 성공·속도 개선은 여기서 측정하지 않았다.

[진입점 표](entrypoints.md), [실제 로드 영수증](compile_receipts.json), [관문표](rejection_table.json), [원본 참조 분포](baseline_inventory.md), [전체 요약](summary.json).
Mac에서 실제 모델 14경로를 컴파일했으며 step/forward/render는 예외로 차단했다. World 초기 reset도 실행하지 않았다. 직접 CLI·GPU 변환·물리 관문은 확인 안 됨으로 표시했다. VM·GUI·모델 호출·학습은 사용하지 않았다.

로컬 검증은 변경 모듈 관련 파일만 대상으로 3라운드 안에 마쳤다. 1차 221 passed/3 failed(enum 변환, 소스 해시, 과거 절대경로), 2차 19 passed/1 failed(추가 소스 해시), 3차 해당 회귀 1 passed. 나머지는 PR CI에서 확인한다. `tests/test_zone_cargo.py`의 native/legacy 변경은 CI에서만 실행한다(이 파일의 기존 World 테스트는 Mac 적분을 수반).

재현 명령:

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.check_noslip_defaults
```

## 참고 자료

- [MuJoCo noslip_iterations](https://mujoco.readthedocs.io/en/stable/XMLreference.html#option-noslip-iterations): NoSlip 후처리 반복 옵션. 0은 이 후처리를 사용하지 않는다. 2026-10-16 원문 조회.
- [MuJoCo preventing slip](https://mujoco.readthedocs.io/en/stable/modeling.html#preventing-slip): elliptic/impratio와 NoSlip의 모델링 차이. 성공률을 보장하는 근거로 사용하지 않는다.
- [MJWarp](https://mujoco.readthedocs.io/en/latest/mjwarp/): 현재 공식 API/기능 제약. 현재 문서와 고정된 2026 실험 빌드는 별개이며, 소스 지원 여부는 해당 빌드에서 재검증해야 한다.
- [warpfit PR #562](https://github.com/kcm0127-dotcom/ugrp/pull/562), `origin/codex/warpfit:experiments/2026-10-16-warpfit`: 사용자 승인 v1 출처. vendor `sim/warp_native_contact.py` SHA-256 `a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`, 바이트 그대로 보존. v1의 noslip0/elliptic/implicitfast/impratio5와 원래 Newton/LS80/50을 사용하며 신규 판정 상수는 없다.
