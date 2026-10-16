# PR #235 6차 리뷰 A/B 기준

`zone_pair_guards_1628a03f.py`는 아래 Git 소스를 바이트 그대로 보존한 테스트 fixture다.

- 커밋: `1628a03f717a4d2e35eac987507d7ac0c24c6374`
- 경로: `harness/zone_pair_guards.py`
- 크기: 9,061 bytes
- SHA-256: `fcd2aef1b7e40b591f02814d340de910bc50eed46cc3f60ff780c1b9b88292cf`
- 추출: `git show 1628a03f717a4d2e35eac987507d7ac0c24c6374:harness/zone_pair_guards.py`

`test_zone_pair_review6.py`는 해시를 확인하고 기준 `PairCommandGuard`만 교체한다.
현재 M2 드라이버·호스트·의존성과 자기 관측 입력은 양쪽에서 동일하게 유지한다.
`t=0`의 0.15초 주행과 `t=0.1`의 `σxy=0.055 m` 재관측 정지를 비교하며,
명령 이력·양쪽 종료 여부·실패 사유·드라이버 상태·`motion_until`이 같아야 한다.
Git 이력이나 네트워크 없이 실행한다. 과거 전체 실행기를 재현하거나 물리 성공을
검증하는 fixture가 아니다.
