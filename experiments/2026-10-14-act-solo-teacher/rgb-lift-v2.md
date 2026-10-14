# Solo RGB 들기 확인 v2 (PR #502, 2026-10-14)

사용자: "1대 교사에 같은 원리의 들기 확인을 토글 solo_rgb_lift_v2로 넣는다", "입력은 자기 RGB와 자기 명령 이력만 쓴다", "held_world_reads=0", "unknown에는 놓기를 막는 규칙을 유지한다". 기준 소스는 `b42f860a7f20aad8b612e988b19a309709617d68`다. 이번 수정의 GCP 실행과 영상 검토는 아직 0회다.

## 원장의 직접 원인

원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/solo-diag-{0..5}-b42f860a/raw`. 각 원장의 압축 파일 해시와 해제 후 해시, result/plan 해시를 manifest와 대조했다. 아래 줄은 `teacher-commands.jsonl.zst`를 해제한 JSONL의 줄이고 시각은 원장의 절대 SIM 시각이다.

| 진단 / 종류 | RGB 원장 줄 / 시각 | 판정 | 저장된 review-own 프레임 |
|---|---|---|---|
| 0 / cyan | 167–196 / 17.9–20.8 s | unknown 30/30 | 20 |
| 1 / can | 144–173 / 15.6–18.5 s | unknown 30/30 | 18 |
| 3 / cyan | 152–181 / 16.4–19.3 s | unknown 30/30 | 19 |
| 4 / can | 171–200 / 18.3–21.2 s | unknown 30/30 | 20 |

- 네 실행 모두 `reason=INSUFFICIENT_IMAGE_INFORMATION`, `v3_reason=null`, `observed=not_observed`: **120/120회** 정보량 관문에서 종료했다. `harness/zone_own_perception_v3_1.py:225`–227이 색/실루엣 검사보다 먼저 실행된다. 이 관문의 기준은 lit share ≥0.03, V의 P95−P5 ≥24, edge share ≥0.003 및 edge pixels ≥50, sharpness ≥1.30이다(`:74`–83, `:147`–157).
- `b42f860a:sim/grasp_act_solo_rgb.py:31`–37은 정보량 세부 수치를 버리고, `v3_reason`이 NOT_FRAMED일 때만 바닥 자리 검사를 허용한다. 따라서 이 네 실행의 **색 임계 검사는 미도달, 바닥 자리 호출은 0회**다. can의 예상 실루엣 0 px 문제보다 앞에서 막혔다. `sim/grasp_act_solo_teacher.py:462`–478(기준 SHA)은 yes가 1초 유지되지 않으면 3초 뒤 `rgb_lift_unconfirmed`로 끝낸다.
- tile은 41/41 yes가 두 번, 전체 임무는 2/6. cyan/can도 별도 평가의 `lift_success=true`는 4/4이고 release는 0/4다. 입력 감사 `invisible_measurements=held_world_reads=0`은 6/6이다. 평가 값은 판정 입력으로 쓰지 않는다.
- 원격 manifest에 RGB 프레임 해시가 있으므로 **프레임 미기록이 직접 원인은 아니다**. 다만 fetch-lite에는 영상이 없다. SSH 개별 회수는 `gcloud ... --project ugrp-act-train-1014`의 `credentials.db` 쓰기 제한으로 실패했다. 본 프레임 0장: 화면 가득 참/빈 화면/가림/어느 정보량 문턱이 실패했는지는 이번 작업에서 확정하지 않았다. 기존 요약의 영상 설명은 독립 확인한 사실로 승계하지 않는다.

모든 실행·해시·확인 범위는 [짧은 요약 JSON](rgb-lift-v2-offline-summary.json)에 있다.

## 수정과 재사용 경계

`--rgb-lift-mode solo_rgb_lift_v2`로 켠다(기본 off). `sim/rgb_lift_evidence.py`에 crate `422cc0ad`의 **shape, lift_commands, 색 부분별 비교**만 분리했다. 카메라/장면/물리/색 정의를 다른 브랜치에서 복사하지 않았다. solo는 기존 `zone_own_perception.hue_mask`와 fisheye 영역으로 주문 색 하나를 분리한다. crate의 손잡이+몸체 두 부분도 같은 비교 코어에 넣을 수 있다.

- close→lift의 팔 올리기 발행 전 RGB, 발행 일정 완료 후 RGB, 완료 3초 뒤 RGB를 비교한다. 640×480 진단 PNG 3장에 파일/픽셀 해시와 시각을 남긴다. 학습 입력 기록이 아니다.
- 자기 발행 명령에서 닫힌 집게 ≤1600, 바퀴 정지, 팬 유지, 창 ≥1.2초, 팔 PWM 변화 ≥20을 요구한다. 실제 관절/접촉/화물 세계 좌표는 입력 인자에 없다.
- 최소 색 면적 1%, 면적비 0.70–1.40, 중심 변화 ≤0.06, 폭/높이 변화 ≤0.10을 두 비교 모두 요구한다. 배경은 필요 없다. 소실/큰 축소는 no, 불명확한 변화/누락은 unknown. 수치는 crate에서 가져온 미보정 기준이며 solo GCP 성능은 미측정이다.
- 3초 샘플을 기다리도록 v2 verify 제한만 5초로 잡고, 기존 yes 1초 연속 확인 및 hold 3초를 유지한다. hold의 매 틱 최신 RGB와 명령을 다시 검사해 소실 또는 unknown이면 lower/open을 허용하지 않는다. 과거 yes를 영구 캐시하지 않는다.
- 기존 v3.1 관문은 유지하며 off 경로 원장에는 `image_information`을 추가해 다음 원인 확인에 세부 수치를 남긴다.

crate 브랜치를 수정하지 않았다. [crate 최소 이관 패치](crate-shared-evidence.patch)는 `422cc0ad`의 기존 v1/색 마스크/관측기를 보존하고 v2만 공용 함수를 호출하도록 바꾼다. 공용 모듈을 같은 커밋에서 가져온 뒤 `git apply --unidiff-zero`로 적용할 수 있다. 향후 두 PR은 이 공용 파일을 다시 만들지 않고 동일 소스를 공유한다. crate 이관 적용·런타임 재검증은 아직 하지 않았다.

## 먼저 확인한 표준 방법

[QT-Opt (2018), Appendix D p.19 Fig.12](https://arxiv.org/pdf/1806.10293)는 놓기 전후 영상 차분으로 성공 보상을 만든다. [Levine et al. (2016), Appendix B p.12](https://arxiv.org/pdf/1603.02199)는 측정 집게 닫힘 위치와 놓기 전후 영상 비교를 사용한다. 원문 해당 절을 확인했다. 발행 행동 전후 시각 증거를 비교한다는 원칙만 참고하며, 측정 집게 위치와 놓기 이후 보상을 놓기 허가 입력으로 가져오지 않는다. 두 논문이 위 색 덩어리 동행 규칙/수치 문턱을 검증했다고 주장하지 않는다.

## 검증과 운영 인계

기존 Python 3.12 환경, 관련 **3개 파일만 50 passed**: `test_grasp_act_solo_run_path.py`, `test_grasp_act_solo_rgb.py`, `test_grasp_act_solo_teacher.py`. 합성 화면의 6종 색/무배경/검은 화면/오색/소실/이동, 불충분 명령·시간·팬·바퀴, crate 두 부분 비교, 가짜 백엔드의 실제 run 루프에서 세 PNG 해시·3초 대기·held 입력 차단·unknown 놓기 차단·새 관문 계획을 확인했다. Mac 물리/렌더/모델 호출 0, 새 GCP 실행 0. 스텁의 감사 0/0은 새 GCP 감사 결과가 아니다.

대기열은 `outputs/e2e18-admin/vm3-queue/20261014-solo-<sha8>.json`: 기존 진단 76900–76905를 재현하고 **6/6 성공+감사 0/0+RGB yes+영상 검토** 후에만 새 관문 79500–79539로 간다. main과 열린 PR 17개의 등록부 및 10/14 실험 계획/설정의 정확한 시드 사용을 확인했다. 79000–79039는 등록부 밖 봉 관문에서 발견되어 제외했다. 관문은 38/40 이상, 종류별 n/N과 HOST_ERROR 포함 전체 40 분모를 보존한다. 속도는 같은 gcp1 n4-highcpu-64, 계획 동시 수에서 확인하고 비용 정지·8시간·유휴 장치를 유지한다. 운영 담당자가 제출한다.

RGB가 자기 명령과 함께 유지돼도 팔이 실제로 움직이지 않은 상황을 완전히 구별할 수 없다. 새 GCP 진단에서 평가 전용 들림과 RGB 판정의 오탐/미탐/unknown을 분리해야 한다. 원본 영상 재회수, solo 실제 성공률/입력 감사/속도, 전체 CI와 crate 이관은 남아 있다.
