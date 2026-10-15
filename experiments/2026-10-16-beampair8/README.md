# beampair8 — 빔 짝 ACT 데이터185쌍 READY

성공185쌍(로봇별370개 기록, 학습66,931행)을 기존 ACT 로더로 검증했다.
새200회 성공률은 **185/200=92.5%**다. 기존 관문40/40과 합산하지 않았고, 새≥95% 교사 관문 통과로 판정하지 않았다.
실행 소스 `72c0e83d`, 교사 의존성 `26f84d0f`, 기반 PR #533 `835ccef2`다.

[요약](summary.json) · [데이터 적합도](data-audit.json.zst) · [전체 시도/원본 재계수](cohort-summary.json.zst) · [후보/프레임/이벤트 관문표](cohort-rejection_table.json.zst) · [회수 검증](retrieval-final-verified.json) · [PR #537](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/537).

|검증|결과|
|---|---:|
|기록off 교사 관문 원본 재계수|40/40|
|기록on 전 명령 궤적/SIM시각/PWM/phase/done 정확 일치|4/4, 허용 오차0|
|캐시 전후 native 자기 JPEG 동일|2,984/2,984|
|새 기록200회|성공185, 교사 실패9, cap_end6, HOST_ERROR0|
|입력 감사|invisible_measurements0, held_world_reads0|
|raw/adapter 원본 파일 해시 검증|173,603파일|
|자기 카메라|640×480,10Hz, RGB139,176프레임|
|학습 대상|66,931행, 로봇별370개|
|전체 명령16개 이력/RGB4장 lag 선택/다음 명령 동기|185쌍 전부 일치|
|10Hz 주기 오차 최댓값|4.775×10⁻¹³초|
|학습 대상 끝 가시 비율|43,981/66,931=65.71%|
|보류 평가 세트|20시드 지정, 기록0|
|아카이브 실제 로더/해제 바이트 해시|로더66931행, 내부1,483파일 전체 일치|

가시 비율은 기존 평가 기준인 맡은 끝≥5 visible probes다. 평가 전용이며 데이터 선택이나 학생 입력에 사용하지 않았다.
접근·정렬 후 pick에서는 빔 본체가 자기 화면 대부분을 가리는 것을 실제 몽타주에서 확인했다.
[새 기록 몽타주](montages/montage-8328000.jpg), [다른 역할/시작 상태](montages/montage-8328013.jpg).

## 입력·기록 범위

ACT15/16의 `SoloRecorder`와 같은 native 카메라 K/D·mount·FOV·해상도·주기,
자기 RGB4장(5.2/1.5/.5/0초)과 자기 발행 명령16개를 사용했다.
로봇별 파일/청크를 분리하고 입력 텐서는 `observation.images.own_history`, `observation.state`만 제공한다.
스킬·물건 종류·담당 끝·명령 시계를 고정 토큰으로 담았다. 상대 카메라/명령/내부 상태, 정답 위치, 측정 관절, 접촉, 자유 문장은 입력에 없다.
자기 영상에 자연스럽게 보이는 상대 로봇은 원본 픽셀 그대로다.

고정 runner의 raw `student.v5`는 보존하고 별도 `training/`에서 schema token만 `student.v6`로 옮겨 다시 검증했다.
추가된 목적 구역 enum 이외 값 변경이 없고 이 데이터의 목적 구역은 `none`이다.
원래 보이는 .8m 인수 라벨부터 자기 명령 단계 완료까지 기록한다. held 화물 좌표는 읽지 않는다.
회복 교란은 실제 자기 발행 이력에 남기며, 교란 구간은 학습 목표에서 빼고 별도 원장의 clean 교사 명령을 사용한다.
기존 ACT 전처리/데이터셋 스키마를 사용했다. 정규화는 새 성공185시드만으로 계산했다.

## 시드·실패·검토

학습 시도8328000–8328199, 보류8329000–8329019다.
[원래 v7 certified 설정 생성기](operations/prepare_plans.py)를40개씩5묶음으로 사용했다.
[실제 학습 계획](train-plan.json.zst), [보류 계획](heldout-plan.json), [예약](seed-reservation.json).
배치별 원래 층화를 유지했고 관문/보류/기존 실행과 겹치지 않음을 확인했다.

cap_end6 중5개는60SIM초 상한,1개(8328188)는 고정 의존성의 상위 `PlanningSafetyCap` wall 안전 상한이다.
이1개는 종료 메타데이터에 weld 필드가 없다. 값을 OFF로 채우지 않고 unknown으로 남겼으며 모든 실패15회를 학습에서 제외했다.
[분석기 첫 시도 오류/분포](operations-errors.json)에 원인을 보존했고, 수정은 분석기에만 적용했다. 물리를 재실행하거나 raw를 고치지 않았다.
후보 거부 사유·물체명·틈 누락은0이다. 새200회 중 실패/상한도 원장과 전체 해시 목록에 남아 있다.

실패8328015/8328010과 성공8328003을3배속 개요+r1+r2 영상으로 만들었다.
전체2Hz192시점, 실패 마지막10SIM초10Hz202시점을 파일로 직접 보았다.
[시간순 관찰/직접 검토 범위](visual-review.json), [실패1](videos/8328015-3x.mp4), [실패2](videos/8328010-3x.mp4), [성공](videos/8328003-3x.mp4).
자기 화면은 실제10Hz native RGB이고 개요만 저장 qpos로 만든 평가 영상이다. Mac GUI·MuJoCo 물리/렌더0, 재생 메타데이터는 ffprobe로 확인했다.

## 저장·재사용

gcp2 C MuJoCo3.12 CPU, 장면 `walls_floor_contrast_v5_indigo110_s80` + v1 바닥 + `no_mip_v1`이다.
`beampair_peer_yield_v1`, held 숨김을 유지했다. 성공185쌍의 weld OFF를 확인했다.
[환경/분석 코드 해시](environment.json), [기록 모듈11개 동결 확인](recording-code-hashes.json).

- 데이터: `/home/ugrp/ugrp-sim/ops-reviews/beampair8/dataset-v1/dataset.tar.zst`
- 크기: 3,605,985,004 B
- SHA-256: `739a9faeaf35cd0cf3d8c73b05bdab76ccb8866b1b55dc81d1bb9e9e05fae251`
- 내부 manifest SHA-256: `87a1b09461a6816e5fbd3cf4a3963959e2ac5482c842509cdd76a38f5c412fb9`
- 전체316,434파일 SHA 목록: `/home/ugrp/ugrp-sim/ops-reviews/beampair8/dataset-v1/SHA256.jsonl.zst`
- SHA 목록 파일의 SHA-256: `9fbbd3052f3ca47737b8df8b2a11aa2fdf0a240d6b257ae96fefd8628dd3e063`
- 원본: `/home/ugrp/ugrp-sim/runs/beampair8-record-<seed>-72c0e83d/`

아카이브의 모든 해제 파일을 압축 전 SHA와 비교한 후 변환용 비압축 사본만 제거했다.
[아카이브 내부 파일 목록](dataset-archive-members.json.zst), [최종 독립 SHA 재검산](final-validation.json).
실행은 dev였고 첫 데이터셋 및 사용한 원본185개와 대표 실패2개는 milestone으로 보존했다.
raw 내부/명령/프레임은 변경하지 않고 바깥 보존 메타데이터만 승격했다([보존 원장](evidence-retention.json.zst)).
전체 raw·아카이브는 gcp2 영속 디스크에 있으며 별도 전체 백업은 없다. Mac에는 요약·몽타주·검토용 작은 영상/띠만 회수했다.

```sh
# gcp2, 새 빈 디렉터리에 복원
mkdir /NEW_EMPTY_DIRECTORY
tar --zstd -xf /home/ugrp/ugrp-sim/ops-reviews/beampair8/dataset-v1/dataset.tar.zst -C /NEW_EMPTY_DIRECTORY
cd /home/ugrp/ugrp-sim/src/72c0e83dab384b4f7d4bb73e37e440e0d1b248f6
PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -c "from harness.grasp_act_data import GraspDataset; d=GraspDataset('/NEW_EMPTY_DIRECTORY/dataset','train'); print(len(d), d[0].keys())"
```

실행 후 큰 계획/JSON은 해제 SHA 일치를 확인하고 압축했다([압축 원장](operations-compression.json)).
과거 대기열의 원래 `train-plan.json` 바이트가 필요하면 `train-plan.json.zst`를 해제해 복원한다.

## 자원·검증 한계

디스크는4개 기록 실측 최대를60SIM초로 환산하고 기존25% 여유,200회, 변환/압축 동시 공간, 타 작업 잔여 쓰기21GiB를 예약했다.
예상 여유158.54GiB, 최종 검증 당시 여유280.66GiB, 바닥8GiB였다([예산](storage-budget.json)).
16동시 본실행의 첫30SIM초 중앙4.8508 wall/SIM으로3.5 경고,6.0 차단 미만이다.
처음 uncached 기록은6.099로 본실행을 보류했다. 기록 전용 기본off `recording_capture_cache_v1`은 같은 pre-command tick의 같은 자기 JPEG만 공유한다.
[MuJoCo scene update 공식 설명](https://mujoco.readthedocs.io/en/stable/programming/visualization.html)과 고정 runner의 순서를 확인했고, 실제4시드 명령/픽셀 동일성으로 수용했다.

관련 비물리 회귀41개 PASS. 실제 데이터 로더의 모든 파일 검사와 첫/중간/마지막 샘플의 키·유한 값 검사를 통과했다.
학습·학생 독립 실행·운반/놓기·실물 성공은 미측정이다.
자기 실행0을 확인하고 임대를 해제했다. 다른 reloc18 임대와4개 실행 프로세스가 남아 VM 정지는 시도하지 않았다([정리 확인](lease-released.json)).
PR은#533 위의#537이며 병합은 수행하지 않았다.
