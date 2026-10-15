# beampair8 — 빔 짝 교사 ACT 데이터 기록

기반 PR #533 `835ccef2`, 고정 교사 의존성 `26f84d0f`. gcp2 CPU만 사용한다.
확정 장면 `walls_floor_contrast_v5_indigo110_s80` + v1 바닥 + `no_mip_v1`,
`beampair_peer_yield_v1`, held 숨김, weld off를 유지한다.

교사 관문 원본40개를 다시 읽어 성공40/40·공동3초 유지·입력 감사0을 확인한 뒤에만 기록한다.
먼저8318711/8318728/8318700/8318706을 기록 on으로 재실행해 off 원본의 모든 SIM시각·발행 명령·PWM·phase·done을 정확 비교한다(허용 오차0).
동일성4/4 뒤 새200개를16동시로 기록한다. 평가용20개는 정적 지정만 한다.

ACT15/16의 단독 기록 `SoloRecorder`와 같은 native640×48010Hz·카메라 K/D·mount·FOV,
RGB4장(5.2/1.5/.5/0초)·자기 발행 명령16개를 쓴다.
고정 교사 runner의 raw는 student.v5이며, 별도 `training/`에서 schema token만 v6로 이행한다.
`pickup_site` enum 추가 외 값 변경 없이 v6 whitelist로 재검사한다.
각 로봇의 student 레코드에는 자기 RGB/자기 발행 명령·스킬·물건 종류·담당 끝·명령 시계만 있다.
상대 관측·교사/평가 정답·자유 문장은 입력에 없다.

회복 교란은 실제 발행 이력에는 남기고 학습 target에서는 제외한다. 별도 adapter의 clean 명령을 target으로 쓴다.
기존 보이는 .8m 근거리 인수 라벨부터 완료까지를 명령 단계로 잇는다. held 화물 좌표를 다시 읽지 않는다.
실패 raw는 보존하되 학습 적합도 목록에서 제외한다. raw와 학습 기록은 서로 덮어쓰지 않는다.
이미지는 같은 영속 디스크 inode에 hardlink하여 이중 저장을 피한다.

RUN_META: 실행 dev, 첫 데이터셋 milestone. 실패 직전10SIM초 자기 카메라10Hz 링은 기존 기록 전용 옵션을 유지한다.
디스크는 첫4개 실측 최대 크기를60SIM초 상한으로 환산하고 기존 storage_budget의25% 여유를 적용한다.
다른 승인 작업의 남은 기록과 x86바닥8GiB를 포함한다. Mac에는 요약·몽타주만 회수한다.

비물리 입력 격리·교란 제외·과거 명령 동기·한 PWM 차이 검출 회귀와 기존 관련 시험36개 통과.
실제 동일성·기록·적합도 결과는 실행 후 별도 JSON에 기록한다. 학생 학습·독립 실행 성공은 범위 밖이다.

## 기록 비용 점검

첫 기록 후보 `ce7438b4`는 첫30SIM초3개 중앙6.099 wall/SIM(개별5.755/6.099/6.537)로
기존6.0 차단 기준을 넘었다. 완료한 실행들은 원본 명령과 같으며 본200개는 제출하지 않았다.
동일 tick의 실패용 링·학습 카메라가 같은 자기 JPEG를 중복 렌더하는 코드를 확인했다.
기본 off `recording_capture_cache_v1`을 기록 경로에서만 켠다. SIM시각이 바뀌면 비우고
로봇·카메라·JPEG quality를 나누며, 같은 pre-command tick의 bytes만 재사용한다.
허용 입력·제어·가시 측정·물리·FOV·카메라 주기를 바꾸지 않는다.
[MuJoCo scene update 공식 설명](https://mujoco.readthedocs.io/en/stable/programming/visualization.html)의
model/data→scene→render 분리와 고정 runner의 capture→own command 순서를 근거로 했다.
최신 다른 렌더러로 바꾸지 않으며, 공식 설명만으로 바이트 동등성을 가정하지 않는다.
새 후보4개에서 원본 명령 및 uncached native JPEG SHA를 다시 비교한다.
