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

## 표준 방법 후보 (기본 off)

R1에서 질감 바닥의 흔적이 실제 자기 영상에 보이나 정적 색 경계는 여전히0–4개다. 저대비 FAST 후보 `--reloc11-low-contrast-v1`은 ORB-SLAM 공개 설정의20/7 중 낮은7을 OpenCV ORB에 적용한다. 기존800개 상한·매칭8/인라이어6·전역12·SE(2)·불확실성·3시점 확인을 유지한다. ORB-SLAM의 셀별 fallback/분배나 전체 SLAM을 복제한 구현이 아니다. 실제 관측이 부족하다고 매칭/등록 통과 기준을 낮추지 않는다.

`--reloc11-wall-field-v1`은 이미 검증된 PR507 `static_walls_v1` AMCL 거리장 모델을 정식 API로 선택한다. 자기 RGB의 벽-바닥 교선 표본만 PF 측정에 쓰고 희소 색 선분 likelihood와의 곱은 제외한다. 정적 색 지도는 기존 독립 기하·다중해·공분산·확인 관문에 계속 사용한다. PF 입자수2000·정답 금지·관문은 그대로다. 이는 새로운 거리장/AMCL 구현을 했다는 뜻이 아니라 기존 거리장 측정 모형의 별도 비교 조건이다.

- [Mur-Artal et al., ORB-SLAM, 2015 IEEE T-RO](https://arxiv.org/abs/1502.00956): 추적·키프레임·재지역화 방법의 참고 원문.
- [ORB-SLAM2 공식 TUM1 설정](https://github.com/raulmur/ORB_SLAM2/blob/master/Examples/Monocular/TUM1.yaml): 저대비 FAST20/7 설정과 설명을 확인(2026-10-15). 이 설정의 카메라 보정값은 사용하지 않는다.
- [Thrun et al., Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/): 6.4 likelihood-field 원리의 출판사 자료. 이번 열람은 도서 소개이며 본문 전체를 새로 검증했다는 뜻은 아니다.
- [Nav2 AMCL 공식 likelihood-field 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): 정적 거리장·hit/random 혼합과 score 누적을 확인. RGB 교선의 거리 센서 잡음 특성이 같다는 보장은 없다.

## 직접 확인 중간 결과

R1 4/4 원본·해시·6장씩 확인, 등록 전부0. R2도3/3 회수·검토했고 등록0이다. R2 첫30초 wall/SIM은4.005/3.920/4.524(중앙4.005), 원본 전체 특징 중앙191.5/173/174·매칭11/13/9다. R1/R2의 동시 부하는 제출 직전 각각3–17/1–2개로 달라 속도 차이를5Hz 단독 효과로 해석하지 않는다. 5Hz+FAST7의 별도 조건에서6.0 아래 실측했다는 범위다.

R2 세 번째는 제출 중 새 스크립트가 생겨 로컬 clean-source 검사에서1회 차단됐다(원격 실행0). 그 스크립트를 커밋한 `8c7586c0`로 재제출했고, 앞선 `41c0104b`와 실행 모듈9개 Git blob이 동일함을 기록했다. 실패 제출도 지우지 않았다.

carry 범위 확인 답변이 없어 공식 API 패치(`git apply --check` 통과)·22개 장면 계획·23개 실행의 **BLOCKED** 대기열까지만 준비했다. carry worktree에는 적용하지 않았다. 기존 smooth 큐는 별도 소유 작업이18:43경 `BLOCKED_CONFIRMED_DEFECT`로 갱신했다. 이 작업은 기존 큐/실행을 수정·중단하지 않았다([동시 상태](carry-concurrent-status.json), [인수 기록](carry-handoff.json)). 새 큐에는 기존 성공/회수/운영 메타데이터를 승계하지 않고 모든 실행 플래그를false로 재설정했다.
