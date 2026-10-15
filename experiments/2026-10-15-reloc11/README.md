# reloc11 — 질감 장면 정적 등록 (진행 중)

사용자 결정: 자기 카메라 위치 추정 selfmap/carry의 주 장면은 PR #511의 `floor_light_textured_v1`이다. smooth는 seed93571 기준 1회만 비교하며 장면·소스·호스트 결과를 합산하지 않는다. 새 장면/동작 토글은 기본 off다.

## 남아 있던 변경 판단

이전 작업의 미push 병합 `4b1ab996`은 origin/main과 PR511 `db0a6858`을 포함한다. 미커밋 `sim/own_map_closed_loop.py`, `sim/solo_cyan_v106.py`, `sim/wall_parallax_strafe.py`는 복제/전역 factory 교체 대신 공식 `render_profile_selection.for_name()`을 쓰는 변경이어서 보존·계속 사용한다. 병합과 수정 내용을 버리지 않았다. nearclip은 병합된 공식 `audit(model, base_profile=...)`를 사용한다. 질감은 기존 검증된 이미지·manifest를 그대로 사용하며 마찰/물리·색 범위·카메라·인공 마커를 바꾸지 않는다.

## 검증 계획

GCP 기존 gcp1 / ugrp-act-train-1014 / n4-highcpu-64, dev PR506, 최대3라운드·자기 동시4·전체40 이하·90 SIM초 이하. 1라운드 seed93571 texture/smooth + 신규2 texture. 이후 smooth는 반복하지 않는다(사용자 추가 지시의 기준1회 우선). 입력 감사 0/0·top 촬영0. 원본 특징·매칭·인라이어·PF·등록·평가 전용 오차와 첫30초 wall/SIM을 재계산한다. `--reloc11-timing-v1`은 기본 off 계측이며 특징 추출/추적·구조 추출·PF·등록·렌더/물리 시간을 기록한다. 중첩 시간은 합산하지 않는다.

carry worktree 수정은 사용자 범위 확인 대기 중이며 기존987d033f 실행/대기열은 수정하지 않는다. 원본과 기록은 이 worktree 안에 보존한다.

## 참고 자료

- [PR #511](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/511): 공식 자연 질감 profile/nearclip API와 고정 이미지.
- reloc10 원본: `/Users/changmin/projects/ugrp-wt/map-carry-zone/experiments/2026-10-15-reloc10/README.md`, `registration-diagnostics.json`, `original-diagnosis.json`.

## 속도 옵션

R1 첫30초 texture93571 wall/SIM6.820. 같은 구간 특징 추출1.923s·PF2.478s(2000입자)·렌더/capture33.302s·물리64.564s·전체 제어100.711s(중첩 포함)다. PF 축소보다 영상·제어 호출 빈도 영향이 크다. `--reloc11-half-rate-v1`은 별도 5Hz 진단 조건이며 기본off(기존10Hz), 원본 선정 주기의 모든 JPEG·원장·제어 입력을 유지한다. 학생 학습 자료가 아니며 10Hz와 행동/성능 동등성을 주장하지 않는다. LK 허용 간격0.25s 안인0.2s를 사용한다. Fake-clock·실제 제어기 단위시험에서 종료시각·6/6 프레임·0/0 감사를 확인했다(관련19통과).
