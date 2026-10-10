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
