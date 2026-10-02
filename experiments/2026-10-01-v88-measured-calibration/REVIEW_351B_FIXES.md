# PR #351 재검토 잔여 수정

대상 `9134d7e12de1d4748a85904dee63c12b682f2dca`에서 시작했다.
독립 재검토는 `a1ed666f212f81ba77a6f5987c5ffb4f1d50a02a`의
[REVIEW_351b.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a1ed666f212f81ba77a6f5987c5ffb4f1d50a02a/experiments/2026-10-01-v88-measured-calibration/REVIEW_351b.md)와
[PR 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/351#issuecomment-5948516471)을 기준으로 했다.

## 수정과 보존 범위

- R3b: `initial_servo_command`를 포함한 모든 명령과 pose/frame/camera label/beam/contact의
  시각을 숫자 변환·반올림·비교 전에 공통 검사한다. 숫자처럼 보이는 문자열, null, bool,
  배열·객체, 누락값, NaN·무한대와 float 범위를 넘는 정수는 `ValueError`로 거부한다.
  완료 시각, schedule 시각·명령 지속시간, 실제 명령 지속시간, motion 시작·구간 시간도 검사한다.
- 리뷰의 테스트 함수 7개·매개변수 포함 18사례를 그대로 가져왔다. 함수 본문 AST는 원본과
  같으며 strict xfail 두 표식(네 사례)만 제거했다. import는 현재 checkout의 기존 guarded
  probe를 사용하도록 바꿨고 CI 목록에 정확히 한 번 등록했다.
- 추가 시간값 검사는 각 레코드 종류의 마지막 행과 arm/look/mecanum/initial 명령을 포함한다.
  R1 입력 경로 보호, R2 하중 선별 뒤 signed amplitude/horizon 지지,
  R4 PRBS 적합 독립성·출력 전 입력 재검사는 기존 테스트와 리뷰 변형으로 확인한다.
- B·B′, r4 candidate/report, frozen validator, v88 등록·실행 설계·지도 registry 및
  `.github/workflows`를 변경하지 않았다. 파일별 바이트·SHA-256 비교는 검증 기록에 보존한다.
  두 문 합성 수집만으로 unloaded B를 승인하거나 실제 `MEASURED_SIM`을 발행하지 않는다.
- durations 원본은 그대로다. 새 테스트 파일을 추가한 뒤 측정 포함 범위는
  **407/410 = 99.27%**로 기준 **90%**를 유지한다. 새 파일에는 기존 중앙값 fallback을 쓰며
  측정 시간을 만들지 않았다. 전체 shard 합집합도 검사했다.

## 재현 환경과 범위

기존 `/opt/anaconda3/bin/python3`를 사용했다. Python 3.13.5, NumPy 2.4.4,
SciPy 1.17.1, pytest 8.3.4이며 환경 설치·변경은 없다.
BLAS/OMP thread 1, bytecode·pytest cache·외부 plugin 자동 로딩 비활성화,
별도 임시 디렉터리와 physics/render/network/model 차단을 적용했다.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=<temporary-guard>:. \
/opt/anaconda3/bin/python3 -B -m pytest -q \
  tests/test_final_pair_calibration_assembly.py tests/test_review_351.py \
  tests/test_review_351b.py tests/test_consumer_criterion_b.py \
  tests/test_final_environment_unloaded_fit.py tests/test_zone_final_pair_v3.py \
  tests/test_zone_final_pair_review_fixes.py tests/test_ci_sharding.py \
  -p no:cacheprovider --basetemp=<temporary-tests> --junitxml=<related.xml>
```

전체 suite나 물리·렌더·모델 호출은 실행하지 않는다. 공용 `outputs/`와 실제 수집 raw는
읽거나 쓰지 않는다. 새 실험 코호트가 없으므로 TensorBoard 변환·뷰어를 시작하지 않는다.
PR은 draft로 유지하고 병합하지 않는다.

## 검증 결과

- 수정 전 네 잔여 반례를 xfail 없이 실행: **4 assertion failures, 오류 0건**.
  제품 코드가 그대로인 상태에서 JSONL 입력·manifest를 바꾼 실제 반례임을 확인했다.
- 수정 후 위 8개 관련 suite 단일 실행: **604 passed**, 실패·오류·skip·xfail **0건**.
  이전 리뷰 6개와 재검토 18개, 추가 시간값 180개를 모두 포함한 수이며 중복 가산하지 않았다.
  잘못된 초기 시각의 fine 조립은 `collection_audit=FAIL`, motion 승인 없음, gain=null이다.
  세 프로필의 정상 두 문 합성 수집은 여전히 `PARTIAL`, unloaded 세 축 판정은 null이다.
- 필수 frozen fixture 3개, shard 합집합 410파일, durations 포함률 99.27%,
  `git diff --check`를 확인했다. 검증 뒤 제품·테스트 소스의 SHA-256도 동일했다.
- 원격 CI는 새 커밋 push 뒤 별도 확인 대상이다. 이전 head의 CI 성공을 승계하지 않는다.

[수정 전 JUnit](fix-351b-evidence/before.xml) ·
[최종 관련 JUnit](fix-351b-evidence/related.xml) ·
[검증 범위·환경·로그 해시](fix-351b-evidence/verification.json) ·
[동결 파일·등록·durations 검사](fix-351b-evidence/static.json) ·
[검증한 소스 해시](fix-351b-evidence/tested-source.json).

임시 archive/extraction은 만들지 않았다. 합성 테스트·guard·PR 댓글의 임시 작업 폴더는
작업 종료 전에 삭제하고 경로 부재를 확인한다. 보존한 자료는 작은 검사 로그와 JUnit뿐이며
실제 수집 raw의 복사·삭제·업로드는 없다.
