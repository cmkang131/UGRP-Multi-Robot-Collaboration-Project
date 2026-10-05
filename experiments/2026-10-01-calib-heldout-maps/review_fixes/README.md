# PR #352 검토 수정 기록 (2026-10-02)

대상 `d92efd8d7381a270ff266c01d7534dc8ab1c89f8`, 독립 검토
`f5eb5636343525f41728ce6c4932c25e6ec3a273`의 P1/P2를 한 묶음으로 수정했다.
재개 시 main `11e9aa26954d3f1ce58c5116ddd14ec2b2738037`의 병합이 진행 중이었고,
충돌 없이 staging된 기존 검토 기록 37개를 보존했다. 수정은 해당 병합과 함께 커밋한다.

- P1: v88 contract·clearance·runner·backend 네 파일을 main과 바이트 동일하게 복원했다.
  v90에는 별도 cases, clearance admission, teacher runner, backend 생성자를 두었다.
  runtime interlock·수집 메서드는 기존 v88 backend에서 상속하며 전역 교체는 하지 않는다.
  v88 세 profile의 전체 plan/bundle JSON 바이트가 독립 기준 해시 여섯 개와 일치한다.
  각 v88 bundle의 소스 239개 모두 현재 main Git blob과 동일하고, 실제 SHA-256과도 일치한다.
  v90 두 bundle의 247/248개 소스 해시도 현재 파일과 일치한다. 과거 해시 대입은 없다.
- P2: 테스트 기대 역할을 생산 `ROLE`과 분리한 `HELD_OUT_VALIDATION`,
  `training_eligible=false`, `teacher_only=true`로 고정했다. plan/bundle/사례 result/
  전체 result를 검사한다. 코드·등록 JSON을 함께 TRAINING으로 바꾸거나 두 boolean을
  뒤집어도 원래 계획 검사가 실패하는지 확인한다.
- 리뷰어 반례 파일을 옮기고 strict xfail 일곱 개를 제거했다. v88 검사는 기준값을
  유지했고, v90 검사는 분리된 진입점을 호출한다. 기존 v88 진입점의 held-out 거부와
  새 backend admission/생성 실패 정리도 native world 생성 이전의 fake 검사로 확인했다.

현재 관리 진입점은 `zone-final-pair-heldout-v90` **3.2.0**, 번들은
`zone-final-pair-v90`이다. main과 열린 PR 6개 원격 브랜치의 `git grep`에서 충돌이 없었다.
기존 `scripts.run_final_pair_v3`는 계속 두 문 calibration 전용이고,
v90은 `scripts.run_final_pair_heldout`으로 실행한다. 인계의 두 workflow 명령은 유효하다.

## 이번 실행의 검증

| 범위 | 결과 |
|---|---:|
| held-out + 리뷰 반례 | 65 passed |
| 기존 v88 + clearance 회귀 | 68 passed |
| CI sharding + workflow의 읽기 전용 계획 3개 | 71 passed |
| 중복 없는 합계 | **204 passed, 0 failed, 0 skipped, 0 xfail** |

명령·파일별 소스/로그 해시는 [verification.json](verification.json),
전체 바이트·소스 일치 확인은 [preservation.json](preservation.json)에 있다.
`guarded_pytest.py`는 공용 outputs 접근을 거부한다. native MuJoCo·모델/네트워크는
기존 offline fixture가 차단하고, backend 생성 검사는 world builder를 fake로 교체한다.
전체 테스트 suite는 실행하지 않았으며, frozen fixture 3개의 존재도 확인했다.

`scripts/refresh_ci_durations.py`로 이번 첫 두 JUnit 보고서의 파일 합계를 산출했다.
기존 측정값은 낮추지 않고 누락 세 파일의 측정값만 CI 시간표에 추가했다.
측정 coverage는 **371/409 = 90.709%**이고, 새 두 테스트 파일은 8개 shard 중
각각 정확히 한 번 포함된다. [durations_changes.json](durations_changes.json)을 따른다.

물리·렌더·모델 호출·공용 outputs 작업은 하지 않았다. `.github/workflows`도 변경하지 않았다.
임시 extraction 디렉터리를 만들지 않았으므로 남은 추출 폴더는 없다.
이 기록은 오프라인 코드 회귀에 한정하며 수집·학습·평가 결과가 아니므로
TensorBoard 변환·뷰어 작업은 하지 않았다.

PR은 draft로 유지하고 병합하지 않는다. 수정 커밋의 독립 재검토와 GitHub CI는 별도이며,
실제 수집·안전·fit·criterion B 연결·학생/실물 성공은 이번 검증 범위에 포함되지 않는다.
