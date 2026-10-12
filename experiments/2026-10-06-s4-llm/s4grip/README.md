# s4grip — 저장 자기 RGB의 집게 이탈 판독 감사

2026-10-10 감독 지시. **물리 0 · 렌더 0 · 모델 호출 0, research_result=false.**
기존 raw만 읽는다. 접촉 라벨은 평가 전용 파일에만 쓰며 제어기에 연결하지 않는다.
PR #425 DRAFT 유지. 감지기·프롬프트·카메라·임계값은 수정하지 않았다.

## 현재 S4 감지기와 측정 한계

`harness/s4_pair_stage.py:PROMPT`의 opt-in `mutual_go_v1`은 자기 RGB를 본 LLM이
`held/grip_lost/unknown`을 답한다. `s4_pair_handshake.py:record`도
`LLM own RGB judgement; unvalidated`라고 기록한다. 별도의 고정 RGB 분류기가 아니다.
선택한 S3 bundle의 모델 호출 수는 모두 0이며 이 프레임에 대응하는 S4 모델 응답이 없다.
따라서 이번 금지 범위 안에서는 **현재 S4 LLM의 정탐·오탐·지연은 미측정(null)**이다.
앞선 s4live4의 합성 응답 시험을 영상 판독 정확도에 합산하지 않는다.

비교 참고용으로 기존 `zone_pair_highpose_grip.relation`을 바이트 그대로 재계산한다.
이는 제어에서 사용하지 않는 `log_only_v96` 함수이며 `False`의 원래 의미는
`GRIP_RELATION_LOST_OR_UNOBSERVABLE`이다. 미관측을 이탈 정답으로 바꾸지 않는다.
`ok`를 held, `False`를 lost로 강제 이진화했을 때의 오류는 별도 진단 수치일 뿐
S4 모델의 오탐률도, 배포된 이탈 정지의 성능도 아니다.

## 고정 입력·라벨

[inventory.json](inventory.json)은 로컬
`/Users/changmin/projects/ugrp/outputs/oracle-runs/s3fix10*`부터 `s3fix15*`까지
접촉 로그가 있는 279개 하위 raw의 경로·SHA·설정·로그 해시를 고정했다.
그 중 cyan 작업 92개를 제외한 빔 작업 187개를 검사한다.
진행 중일 수 있는 s3fix16과 다른 작업의 새 파일은 자동 추가하지 않는다.
영상 없는 진단·로그 없는 orphan JPEG·중단 실행을 성공이나 이탈 음성 표본으로 채우지 않는다.
이 목록은 개발 자료를 사후 고정한 것이며 새 확증 코호트의 사전 등록이 아니다.

각 r1/r2의 `robots/<rid>/frames.jsonl`에서 자기 카메라 ID·이미지 SHA-256·자기 발행
servo 명령을 읽는다. 같은 raw의 `eval_only/contacts.jsonl`을 SIM 시각 소수점 9자리까지
**정확히 일치**시켜 결합한다. 최근접/보간·다른 로봇 영상은 쓰지 않는다.
JPEG를 디코딩하는 것은 저장 영상 판독이며 MuJoCo 장면 생성/렌더가 아니다.

- `held_contact`: 해당 로봇의 좌·우 finger와 `cargo_beam_1__*`가 모두 접촉(`dist_m<=0`).
  접촉력·마찰 여유가 없는 기록이므로 **접촉 기반 집기 대리 라벨**이며 안정 파지/운반 성공은 아니다.
- `partial_contact`: 한 손가락 접촉. 완전 이탈 또는 안정 파지로 강제 분류하지 않는다.
- `lost_contact`: 앞서 양쪽 접촉이 있었고, 닫기 명령(1500)이 계속된 상태에서 양쪽 접촉이 모두 사라짐.
  반복 무접촉 프레임은 하나의 접촉 이탈 episode로 센다. 재접촉 뒤 다시 놓치면 새 episode다.
- `not_held`: 집기 전 등 위 조건이 없는 무접촉. **이탈 정탐의 분모에 넣지 않는다.**
- 여는 명령·명령 이력 없음·접촉 로그 0.25초 초과 공백은 이전 집기 이력을 끊는다.
  같은 시각의 명령은 프레임 취득 뒤 발행되므로 직전 명령을 쓴다.
  단일 접촉 표본의 전이를 보존하며 물리적 미끄러짐의 원인/지속성을 확정하지 않는다.

CV 함수의 인수는 `(저장 JPEG bytes, commanded_servo)` 둘뿐이다. 라벨·정답 위치·측정 관절은
들어가지 않는다. 실행 프로세스는 MuJoCo/Torch/HTTP 클라이언트 import와 socket 연결을 차단한다.
라벨·예측·각 이미지 SHA 목록은 기본 체크아웃 `outputs/s4grip-offline/`에 보존한다.

## 표본 가용성에서 먼저 확인한 결과

영상과 정확히 짝지은 표본은 **49,232 프레임**: held_contact 184, partial_contact 4,
not_held 49,044, lost_contact **0**이다. 이미지 해시 중복을 제거하면 각각 92/2/47,608개다.
held 영상은 아래 두 nominal 진단 raw뿐이며 두 raw의 r1/r2 프레임 목록과 접촉 로그가
**파일 SHA까지 동일**하다. 따라서 184개 프레임을 184개 독립 grasp로 해석할 수 없다.

- `s3fix14-diagnostics-r1/cohort/s3fix14-capture-r1-yaw1-r1/raw/trial-12`
- `s3fix14-diagnostics-r1/cohort/s3fix14-capture-r2-yaw1-r1/raw/trial-12`

각 raw는 12 SIM초, 자기 RGB 간격0.2초, 로봇당61장(held46/partial1/not_held14)이다.
이들은 정답으로 초기 상태를 배치한 **평가용 fixed tape 진단**이다. S3 학생 정렬 성공이나
S4 LLM 공동 운반 성공으로 승계하지 않는다. 다른 baseline/정렬 실행은 집기 전 표본뿐이다.

접촉만 있는 기록에는 완전 접촉 이탈 전이47개가 있으나 **영상 대응0/47**이다.
그 시계열의 lost_contact 표본7,745개를 영상 감지기의 정탐 분모에 넣지 않는다.
7개 raw(14 robot series)의 중복·역행 시각은 전체 시계열을 제외했다. 그 raw에는 영상도 없다.
관측 가능한 이탈 사례는0개로, 이탈 정탐률·지연 평가에는 **자료가 부족하다**.
이탈 지연은 0프레임으로 표시하지 않고 미측정으로 둔다.

| 기록 그룹 | not_held | partial | held_contact | 영상 있는 이탈 |
|---|---:|---:|---:|---:|
| s3fix10 | 5,388 | 0 | 0 | 0 |
| s3fix11 | 14,400 | 0 | 0 | 0 |
| s3fix13 | 14,600 | 0 | 0 | 0 |
| s3fix14 | 56 | 4 | 184 | 0 |
| s3fix15 | 14,600 | 0 | 0 | 0 |

## 현재 판독 결과의 해석

집기 접촉184장에 기존 CV `ok=True`는 **0/184**, `LOST_OR_UNOBSERVABLE`은 **184/184**다.
해시 중복 제거 후에도 집기 수락0/92, 거부92/92다. 거부를 이탈로 강제 해석하면
집기 중 거짓 경보184/184지만, 원래 반환값은 unknown을 포함하므로 이 수치를
배포된 S4 이탈 오탐률로 부르지 않는다. loss 영상0이므로 CV 이탈 정탐0/0·지연은 미측정이다.
집기 전 표본에서 거짓 held 수락0/49,044, 거부49,044/49,044였다. 부분 접촉4장도 모두 거부다.
49,044개의 집기 전 음성 표본이 지배하는 전체 정확도를 안전 성능으로 요약하지 않는다.

한 반례는 첫 번째 nominal raw의 r1 frame16, 5.35 SIM초,
이미지 SHA `629fec2987979b8344b92a4242c1d443034cbe3b31e02f5eb1c3bb57f8055154`다.
같은 시각 좌·우 손가락 접촉이 있으나 `ok=False`, coverage0.7555, IoU0.1668(<0.50),
edge slope 차이0.001339를 반환한다. 이 한 장의 IoU 탈락만으로 전체 오류 원인을 확정하지 않는다.

**현재 S4 모델 자체**는 집기 영상에 대한 응답 가용성0/184이고, 이탈 영상·응답0이다.
정탐/오탐은 채점할 응답이 없어 미측정, 지연은 이탈 영상과 응답이 없어 미측정이다.
`research_result=false`; 영상만 보고 집게 이탈을 검증했다는 판정은 **not-ready**다.

## 표준 방법 조사와 제안만 남기는 토글

아래 제안은 **미구현·기본 off**이며 현재 결과에 적용하지 않았다. 네 통신 조건에 같은
센서·판독기·주기·unknown 정책을 적용해야 하며, 통신별 튜닝으로 판독 차이를 만들지 않는다.

| 자료 | 확인한 방법과 우리 입력 제한 | 제안만 하는 토글 |
|---|---|---|
| Marx et al., *Frame-Based Slip Detection…*, Applied Sciences 2023 [논문](https://doi.org/10.3390/app13158620), [저자 대학 PDF](https://ris.utwente.nl/ws/portalfiles/portal/419033722/applsci-13-08620-v2.pdf), §2.2–2.3, §4 | 그리퍼 기준 물체 optical flow, 배경 제거, 픽셀 투표, 여러 시간 간격 비교. RGB-D/그리퍼 metadata를 쓰며 무늬 부족·가림·조명 변화의 한계를 설명한다. 우리에게 없는 depth/측정 관절은 가져올 수 없다. | `grip_temporal_rgb_v1=off`: 자기 RGB에서 보이는 그리퍼와 빔의 상대 변화만 추적. 시간 영상 비교는 별도 입력 조건으로 등록. |
| Li, Dong, Adelson, ICRA 2018 [논문](https://arxiv.org/abs/1802.10153) | 손 카메라와 GelSight를 결합한 시퀀스 분류. 촉각 영상은 현재 RGB와 다른 센서다. 해당 논문 수치를 우리 정확도로 전용하지 않는다. | `grip_sequence_prompt_v1=off`: 향후 허용될 때 같은 자기 RGB 시퀀스를 LLM에 주는 별도 비교. 현재 한 프레임 경로와 분리. |
| Dong et al., ICRA 2019 [논문](https://arxiv.org/abs/1810.13381), [저자 코드](https://github.com/siyuandong16/Incipient_slip_detection_with_GelSlim_sensor), [MIT 설명](https://mcube.mit.edu/research/gelslim.html) | GelSlim 접촉 표면의 marker motion으로 incipient slip을 판정. 촉각 센서·marker 패턴이 없는 현재 손목 RGB에 그대로 적용할 수 없다. | 센서 추가는 이번 제안 범위 밖. `grip_observable_v1=off`: 가림/근거 부족을 loss와 분리해 unknown으로 기록하는 계약을 먼저 평가. |

첫 논문의 optical-flow 알고리즘 설명과 한계는 본문을 확인했다. 저자 전용 실행 코드는
찾지 못해 미확인이다. GelSlim 공개 코드는 저장소 존재·목적을 확인했으며 실행하지 않았다.
추가 개선 후보는 `grip_static_projection_v2=off`: 기존 relation의 고정 near plane 약22.2mm와
raw의 `floor_light_nearclip_v1` 차이, 발행 명령으로 계산한 camera pose와 하중 중 실제 영상의
불일치를 분리해 점검한다. 정답 extrinsic·접촉으로 보정하지 않고, 정적 보정/자기 영상만 허용한다.
이 차이가 이번 모든 오류의 원인이라고 확정하지 않는다.

향후 판정은 held/lost/unknown 혼동표와 coverage, **이탈 episode 수**, 이탈 이후 최초 감지까지의
저장 프레임 수·SIM 시간, 미감지/관측 종료를 함께 보고한다. 시퀀스/동일 초기 조건을 나누어
튜닝·평가하고, 같은 실행의 인접·중복 프레임을 독립 표본으로 계산하지 않는다.


## 재현·보존·검증

평가기 코드: `fa2caa75eb3b557d7d20beb94e30b81c69f63977`.
[report.json](report.json)에 n/N과 null 판정, [verification.json](verification.json)에 코드·출력·시험 해시,
[inventory.json](inventory.json)에 원본 파일 해시를 보존했다.
전체 자세한 실행별 집계/접촉 이탈 목록은 로컬 `outputs/s4grip-offline/replay-v2/summary.json`,
프레임별 평가 라벨·CV 출력·이미지 해시·S4 예측(null)은 `eval-only-frames.jsonl`이다.
25개 영상 raw, 50개 로봇 시계열, 49,232개 이미지 해시를 검증했고 입력 로그985개를 종료 뒤
재대조했다. 원본은 수정하지 않았다. Git의 요약·해시는 원본 이미지 원격 백업이 아니다.

관련 `tests/test_s4_grip_raw.py` **6 PASS**, CI 수집 목록 등록 확인.
다른 cargo/robot/양의 거리 접촉 제외, pregrasp/partial/loss/재접촉 분리, 의도적 개방·명령 없음,
capture/command 동시각 순서, 로그 공백, 중복 시각 거부를 검사했다. 제어기 회귀나
실제 모델·물리 검증으로 범위를 넓히지 않는다. `git diff --check` 통과.

첫 오프라인 분석은 영상 없는 진단 로그의 중복 시각에서 중단(exit1)했다.
[실패 기록](replay-v1-failure.json)과 부분 출력·당시 분석 코드를 raw 폴더에 그대로 보존했다.
모호한 robot series14개를 명시적으로 제외한 v2가 완료됐으며 v1의 부분 표본을 합산하지 않았다.
이는 분석 실패이며 새 SIM 실행 또는 SIM 실패가 아니다.

```sh
P=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$P -m pytest -q tests/test_s4_grip_raw.py
$P -m scripts.evaluate_s4_grip_raw \
  --manifest experiments/2026-10-06-s4-llm/s4grip/inventory.json \
  --output /Users/changmin/projects/ugrp/outputs/s4grip-offline/replay-NEW
$P experiments/2026-10-06-s4-llm/s4grip/summarize.py \
  /Users/changmin/projects/ugrp/outputs/s4grip-offline/replay-NEW \
  --output /Users/changmin/projects/ugrp/outputs/s4grip-offline/report-NEW.json
```

`replay-NEW`는 존재하지 않는 경로여야 한다. 출력은 평가 자료이며 제어 입력으로 사용 금지.
기존 이미지·로그가 있어야 재현할 수 있다. 새로운 모델/물리 실행 권한을 뜻하지 않는다.

## TensorBoard

새 native snapshot `1010-s4grip-offline`의 dataset / legacy-cv / s4-llm-unmeasured
3개 run, scalar24개를 EventAccumulator와 실행 중 HTTP 응답으로 대조했다.
S4 정확도·이탈 지연·응답 시간은 미측정이므로 0으로 채우지 않았다.
현재 CV와 S4 모델을 run별로 분리하고 표본 가용성·오프라인 호출0만 표시한다.
새 영상은 만들지 않았으므로 등록할 영상이 없다. 다른 작업의 서버·기존 snapshot은 유지했다.

[저장된 TensorBoard 보기](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fheld_frames%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flost_frames%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcontact_loss_episodes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fheld_accept%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fheld_reject%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Frecorded_predictions%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fphysics_runs%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E1010-s4grip-offline%2F#timeseries) · [변환·검증 기록](tensorboard.json).

Chrome 강 프로필의 S4 전용 탭에서 세 run 선택·held184/lost0·8개 핀을 확인했다.
HParams는 case/policy/outcome/source_sha 4열과 model_calls 지표를 적용했다(전역 표; Time Series는 새3run 필터).
