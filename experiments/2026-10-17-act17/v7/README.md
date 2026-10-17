# v7 재관문·재기록 사전 설계

조정자의 `ops-alert.md` 답변에 따라 v4 비교 예외를 쓰지 않는다. 기존 v4 진단·모델·원본은 보존하고 합산하지 않는다.
[프로토콜](protocol.json), [계획 스택 검사](current-stack-plan-check.json)는 물리 실행 전에 고정했다.
스택 선언 검사는 pass이며 실제 관문 성공·실행 XML·입력 감사는 별도 확인한다.

| 항목 | 기존 v4 | v7 고정 값·근거 |
|---|---|---|
| 종류·시연 시작 | 4종류×TRAIN8 + VAL2 =40기록 | 4종류×TRAIN50 + VAL10 =240기록. ACT/ALOHA 통상50시연/과제와 대비해 조건별 표본을 확보하는 설계 선택이며50/색의 필요성·성공을 입증한 값은 아님 |
| 관문 | native40/40, v4 | 별도40(각 종류10), ≥38/40, 학습용 카메라 OFF. 기존 ≥95%·최소40 기준 그대로 |
| 정렬 비중 | TRAIN740/11860=6.24%, VAL193/3026=6.38% | 원시 기록은 실제10Hz 그대로. M/F는 원 ACT의 episode 균등·episode 안 시각 균등. S만 접근(초기 접기 포함)/정렬(재관측 포함)/파지/놓기 네 층을1/4씩 뽑는 TRAIN 표집 후보 |
| 영상 | 4개 과거 시점을 각각320×240로 줄여640×480 montage, 현재 영상은1/4 | M은 같은 montage 비교. F/S는 원 ACT처럼 현재 자기 영상640×480 전체 사용. 실제 카메라·화각·자세·10Hz·자기 RGB 이력 계약은 유지 |
| 영상 정규화 | ImageNet mean/std | RGB/255와 같은 mean/std를1회. crop·물체 정답·타 카메라 추가 없음 |
| 행동 정규화 | TRAIN 고유 h0 평균/std, std최소.01 | 동일 방법으로 새 TRAIN200 시작에서만 다시 적합. wheel비율/duration÷.15/PWM좌표계 유지. 검증·관문·패딩 미사용 |
| ACT 설정 | batch8/chunk8/10000updates | 첫 라운드 세 후보 모두 같은 seed·batch8·chunk8·10000updates. β10·lr1e-5·balanced done BCE 유지. 연장 학습은 기본off, 결과 표를 본 뒤 별도 라운드 |
| 기록 저장 | JPEG+확장 uint8 NPY | 원본 JPEG 참조와 작은 압축 tensor만 보관하는 loader 준비. 중복25GB NPY 생성 금지. 관문 뒤4개 pilot로 실제 bytes/SIM을 재서240개 쓰기가 disk8GiB 바닥을 지키는지 먼저 검사 |

균등 episode 표집은 [ACT 공개 Dataset](https://github.com/tonyzhaozh/act/blob/main/utils.py)의
episode 단위 Dataset에서 무작위 시작 시각을 뽑는 방법이다. F의 현재 영상도 같은 구현을 따른다.
S의 네 단계 층화는 우리 설계 후보다. [Mobile ALOHA](https://arxiv.org/html/2401.02117)의
동일 비중 source sampling과 관련되지만, 이 논문이 단계별25%의 효과를 검증했다고 주장하지 않는다.
행동 std최소.01은 공개 ACT와 고정 ACT 라이브러리의 기존 값이며 새 물리 허용치가 아니다.
done BCE의 skill별 prior는 같은 TRAIN 표집 확률로 계산한다. M/F는 episode 균등·episode 안 시각 균등,
S는 단계 균등 확률을 반영하며 VAL은 쓰지 않는다. 행동 정규화 통계는 표집과 별개로 고유 TRAIN h0에서 계산한다.
새 JPEG loader와 추론 adapter의 실제 capture 전처리를 첫 gradient 전에 배열 단위로 대조한다.
각 후보는 최종 weights만 저장하고 다시 로드해 동일 입력 예측을 비교한다. 모델·원본 삭제로 디스크를 확보하지 않는다.

[ACT 논문](https://arxiv.org/html/2304.13705)은 대부분50시연/과제, Velcro100과 실제25평가를 보고했다.
[Diffusion Policy](https://arxiv.org/html/2303.04137v4)의 실물 Push-T136시연·20평가, pouring/spreading50시연 중90% TRAIN도 대비했다.
다른 카메라·로봇·과제의 보고값을 우리 성공률로 옮기지 않는다.

새 seed는 gate88320–88359, record88600–88839(종류별60개 중6번째마다 VAL), final91800–91839다.
고정 소스가 받는 기존 train/heldout 범위 안에서, main과 모든 fetch된 열린 작업 브랜치의 명시적 seed registry/10월 protocol에 숫자 충돌이 없음을 확인했다.
VAL8은 VAL40의 처음 두 시작/종류다. 이후 기록·학습·평가에서 같은 split을 쓴다.
진행은 새 v7 관문→기록 pilot4·직접 확인/디스크 예측→나머지 기록→M/F/S 학습→같은 VAL8 순서다.

관문 실행은 `be39af6fc`, 원본 XML·Score 재계산은 `5160938e5`다. 40/40(종류별10/10),
학습카메라 OFF, 입력 감사 위반0이며8,226개 manifest 파일 해시를 확인했다.
[성공 시연 직접 검토](playback-review.json)는0–45.5 SIM초 전체2Hz와35.6–45.5초10Hz,
3배속 mp4의 ffprobe 검증을 기록한다. 이는 교사 결과이며 학생 평가가 아니다.
최신 main `efc484ad5`의 스택 검사도 통과했다. 추가된 시작구역 prior는 위치추정 경로 규칙이며
이 근거리 ACT 후보에 정확한 시작 좌표나 새 입력을 추가하지 않는다.

공개 ACT [README](https://github.com/tonyzhaozh/act/blob/main/README.md)는 sim 예제2000 epochs,
실물은 최소5000 epochs 또는 loss plateau 뒤3–4배 학습을 권한다. epoch은 episode 표집 단위이므로
우리 update10000과 같다고 하지 않는다. 첫 라운드는 위 세 후보10000으로 고정하고,
추가 학습은 loss·개루프·VAL8 결과와 예산을 본 뒤 최대3라운드 안의 별도 후보로만 다룬다.
`act17_train_batch.py`와 `act17_val_batch.py`는 각각 공통 queue에 스택 검사·원인 표를 묶는다.
VAL 대기열은 세 모델을 모두 마친 뒤 같은8시작을 비교한다. `--split final`은 실제 완료 VAL 보고서 해시와 선택 동결을 따로 요구한다.
현재 FINAL40 진입 코드의 'VAL8 통과'는 여덟 과제 판정이 모두 성공(8/8)이라는 조정자 해석이다.
사용자는 통과율 숫자를 별도로 정하지 않았다. 이는 교사95% 기준을 학생에 옮기거나 모집단 성공률을 보장한다는 뜻이 아니다.
모델 결과를 보기 전에 이 유한 개발 관문을 명시하며, 수정 시 결정 근거와 새 동결 기록을 남긴다.
여러 후보가8/8이면 고정 우선순위 F→M→S로 하나를 고른다. F는 원 ACT의 현재 전체 RGB·episode 표집에 가장 가깝고,
M은 이력 baseline, S는 단계 표집 가설이라는 설계상 선호다(성능 우열을 미리 주장하지 않음).
`act17_selection.py`는 실제 세 후보24행의 VAL seed·성공 수·보고서 해시를 묶어 동결한다. FINAL 결과로 재선택하지 않는다.

최신 진행·저장공간 승인과 준비 실패/재시도는 [진행 기록](progress.md)에 있다. 남은236회는 제출했으나 연구학습·학생평가는 아직 미실행이다.
