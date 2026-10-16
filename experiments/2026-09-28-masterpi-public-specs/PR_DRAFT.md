# 공개 자료로 MasterPi 형상·센서 사양과 미확인 범위 정리

Refs #214

실물 수작업 측정을 당장 하지 않는 조건에서 PR #249 모델과 PR #251 sim2real 템플릿, PR #248 초음파 모델이 참고할 공개 근거를 정리했다. 실행 코드·모델·번들은 변경하지 않았다. 새 번들 ID 등록/예약 없음.

## 변경

- `experiments/2026-09-28-masterpi-public-specs/README.md`: 초음파·팔·서보·카메라·차륜/차대 사양, 출처 종류·신뢰도·상충값·권고를 한국어로 정리했다. 축척값에는 기준 치수와 원본 픽셀을 남겼다.
- `public_specs.json`: #251 템플릿의 항목 경로를 보존하고 각 공개값에 단위·URL·신뢰도를 붙였다. 실측 필드는 null, `deployment_allowed=false`이며 보정 입력으로 직접 사용하지 않는다.
- `sources.md`와 `reference_manifest.json`: 실제 확인한 원문·고정 SDK SHA·접근 실패를 기록했다. 기존 참조 이미지 6개의 SHA-256을 확인했으며 재배포 허가 미확인으로 이미지는 링크만 제공했다.
- `experiments/README.md`: 조사 기록을 인덱스에 추가했다.

## 주요 판단

- 명목 초음파 높이 약62 mm·전방88 mm, yaw 전방48 mm, 어깨 높이128 mm는 공식 도면 축척값이다. 실물 정밀 측정값이 아니다.
- 공식 MasterPi SDK를 확인했다. 상완65 mm와 도면57.9 mm의 차이는 미해결이다. 전완62 mm, 닫힌 집게 목표점100 mm의 SDK 정의와 그려진 형상 끝94.3 mm를 구별했다.
- 초음파15°의 반각/전체각 정의와 실제 갱신률은 찾지 못했다. 공식 MasterPi SDK 오류99999와 별도 공식 튜토리얼 오류5000은 버전별 계약으로 분리했다.
- 순정 카메라170°의 축 정의는 미공개다. 공식 보정 NPZ의 일반5계수 K/D는 공개 샘플로만 보존하고 현재 fisheye4계수 보정에 적용하지 않는다.
- bare 차대 전장, 개체별 부품 revision·장착 변환·센서 특성은 미확인이다. 제조사 CAD/BOM/펌웨어 명세 또는 이후 실물 증거가 필요하다.

## 검증

`tests/test_real_geometry.py`: **7 passed in 0.13s**. JSON 검산 PASS: 정적 템플릿 32/32항목 포함, 공개값 객체147개, 출처44개, 도면 계산22건, 이미지 해시6개 확인. `.pytest_tmp` 정리 완료.

정확한 실행 결과와 게시 상태는 [WORK_LOG.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/masterpi-public-specs/experiments/2026-09-28-masterpi-public-specs/WORK_LOG.md)에 기록한다. 단위 테스트는 `tests/test_real_geometry.py`만 대상으로 한다. 별도로 JSON 구조·출처·단위·도면 계산·참조 이미지 해시를 검산한다.

물리/시뮬레이션/모델 호출 0회. 태그0개 전제와 weld OFF 유지. PHYSICAL 성공·배포 준비 승인을 뜻하지 않는다. 신규 실험 지표가 없어 TensorBoard 변환/서버 실행도 없다.

## 참고 자료

- [Hiwonder MasterPi 제품표·도면](https://www.hiwonder.com/products/masterpi), [발광 초음파 사양](https://www.hiwonder.com/products/glowing-ultrasonic-sensor)
- [공식 MasterPi SDK, 고정 커밋](https://github.com/Hiwonder/MasterPi/tree/11b0cb04ada14be7c391e6c865ac705f903a95e7), [공식 초음파 문서 원문](https://github.com/Hiwonder-docs/Glowing-Ultrasonic-Sensor/tree/d4def3269dcf45f59e4c8f0317cb972c7c06b54a)
- [전체 출처와 접근 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/masterpi-public-specs/experiments/2026-09-28-masterpi-public-specs/sources.md), [공개값·축척·미확인 항목](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/masterpi-public-specs/experiments/2026-09-28-masterpi-public-specs/README.md)
- 관련 [PR #249](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/249), [PR #251](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/251), [PR #248](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/248)

이 파일은 게시용 본문 초안이다. 실제 draft PR 생성 여부는 WORK_LOG에 별도로 기록한다. 병합하지 않는다.
