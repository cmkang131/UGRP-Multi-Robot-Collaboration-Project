# T11 정적 검증 기록

## 실행 범위

기준 소스 `6594536b1a1afec6d9d109b35dd85a8426142d01`와 새 `audit.py`의 정적 계산이다.
자체 audit/test 코드 및 산출 파일의 SHA-256은 `data/artifact_checksums.json`에 고정한다.
`data/static.json.source_sha256`의 기존 입력 24개는 현재 파일과 기준 HEAD 바이트가 같다.
기존 s1–s6 v1/v2 12개·지도·controller·DRAFT는 수정하지 않았다.

- 로컬 SIM초0 / 물리0 / 렌더0 / 새 모델 호출0 / 학생 trial0.
- MuJoCo·모델 SDK import, 네트워크 연결, schematic 렌더를 차단한 독립 프로세스에서 audit를 실행했다.
- GitHub CI는 별도 검증이며 ACT/local-model test 실행을 허용한다. 취소·skip 요청을 하지 않는다.
- Python 실행 환경은 primary의 기존 `.venv-sim-worker-mac`을 재사용했다. 새 환경 없음.
- 원본 수치와 경로는 `data/static.json`, 관련 검사 출력과 환경·잠금 기록은 `data/validation-001.*`다.
- 기존 실험·P09의 결과를 신규 학생 성공/확증 분모에 합산하지 않는다.

## 정적 산출

명령:

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-s6-order-design/audit.py \
  --output experiments/2026-09-30-s6-order-design/data/static.json
```

exit0. 입력/source 해시는 계산 전후 동일하다. can 접근4개 proxy×360 heading,
두 pivot×양방향×두 margin의 총8 sweep(각91 자세), 초기 다른 화물을 모두 포함한
s6 화물3개 운반 경로를 남겼다. 운반3/3 `feasible`, 원본→격자 첫점 sweep3/3 true다.
이는 spawn 접근이나 학생 파지/운반 성공률이 아니다. 자세열과 README의 반례를 함께 읽는다.
차단 장치를 명시 호출로 분리한 최종 audit 코드로 `/tmp/t11-static-verify-20260930.json`을
별도 생성했고, `cmp` exit0으로 보존한 static.json과 바이트가 같음을 확인했다.

## 관련 검사

검사 대상:

```sh
python -m pytest -q \
  experiments/2026-09-30-s6-order-design/test_audit.py \
  tests/test_zone_scenario_feasibility.py
```

실제 드라이버는 공용 잠금 획득 후 `audit`의 import/network/render 차단을 먼저 설치하고
위 pytest 대상을 실행한다. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`을 사용한다.
다른 작업의 살아 있는 잠금에는 손대지 않았고, 잠금 대기 중 pytest는 시작하지 않았다.

잠금이 다른 작업으로 연속 인계되어 첫 대기 드라이버를 pytest 시작 전에 Ctrl-C로 종료했다(exit130).
잠금을 보유하지 않았고 다른 작업에 신호를 보내지 않았다. 더 짧은 잠금 확인 간격으로 재시작했다.
이 대기는 물리/시험 실패 셀이 아니며 시험 실행 수0이다.

**44 passed in 20.04s, driver exit0.** 신규 반례13개 + 기존 feasibility31개가 통과했다.
자기 PID·브랜치의 잠금만 반환했고 release 기록을 확인했다.

신규 검사는 정상·blocked 경계 반례, 접점 pivot과 중앙/차체의 구별,
non-finite 입력 거절, standability와 entry segment의 구별, structured의 지원/거절,
네 조건별 private 배치·identity binding·사건 시각·심판 변경 시 공개 payload 비간섭을 다룬다.
실행 controller를 추가하지 않았으므로 미래 controller의 안전 종료나 동작 비간섭까지
검증했다고 주장하지 않는다.

## 보존·전달

- 새 폴더 안의 작은 정적 파일만 Git에 보존한다. 파일당1 MiB·실험당5 MiB 이하.
- artifact checksum 목록은 자기 자신을 제외한다. JSON 파싱, 문서 상대 링크,
  새 파일 범위, 입력 불변, whitespace를 커밋 전에 확인한다.
- 설계 선택은 대기이며 권고를 승인으로 처리하지 않는다.
- 물리 필요성·성공·양측 실패 안전은 미측정. 후속 총 SIM 비용도 미산정이다.
- TensorBoard 변환/표시는 후속 물리 결과의 작업이다. 이번 정적 자료에 물리 성공 지표를 만들지 않는다.
- draft PR과 원격 commit/CI 상태는 PR에서 확인한다. 이 문서는 CI 완료를 미리 주장하지 않는다.
