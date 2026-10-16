# beamact3 — wheel 분류·compact history A/B 재학습 완료

**A0/20·B0/20, 모두 NOT_READY.** actdiag 권고를 구현하고 두 조건을 final20000까지 학습·평가·Release 검증했다. 기본 off를 유지한다. 기존 beamact2(PR540) 위 PR545의 비교 후보이며, 수제 근거리 경로·persistence 대체·정답 보정을 넣지 않았다.

| 지표 | A: 최근 자기 wheel/pulse 보존 | B: 같은 history 마스크 유지 | persistence |
|---|---:|---:|---:|
|검증 전체 wheel MAE|0.022876|0.030805|0.023129|
|8틱 재추론 wheel MAE|0.020701|0.030093|0.022809|
|안정 구간 wheel MAE|0.011423|0.021875|0|
|명령 전환 wheel MAE|0.126417|0.111537|0.232231|
|학생 성공|0/20|0/20|폐루프 미실행|
|접근→정렬→READY→파지→3초들기|16→0→0→0→0|13→1→1→0→0|—|
|종료|cap_end20|cap_end19·정렬실패1|—|

A는 B보다 전체·안정 구간 오차가 작고, B는 전환 구간 wheel 오차가 A보다 작다. pulse/PWM은 둘 다 persistence보다 크다. 오프라인 wheel 개선은 학생 파지 성공으로 이어지지 않았다. 전체 TRAIN/validation·재추론·안정/전환·단계별 지표는 [오프라인 표](offline-comparison.md)와 각 A/B-offline-summary.json에 있다. 원본20개씩을 재계수했고 HOST_ERROR는 각0이다. 실패 단계 A=정렬16/접근4, B=정렬12/접근7/파지1. [요약 JSON](summary.json), A/B-student-summary.json, A/B-rejection-table.json에 원본 경로·SHA·재현 명령·누적/거부 수가 있다.

동일 beampair8 dataset-v1(185episode·370shard), TRAIN166seed/60023행·validation19seed/6908행·seed20261015를 사용했다. archive SHA739a9fae…e251, split SHAa0f5d8a1…8d6cd. 보류20seed8329000..8329019와 plan SHA5b04be7e…28f7도 beamact2와 같다. 이미 본 비교 세트이며 새 독립 확증 자료가 아니다. A/B·과거 결과를 합산하지 않는다. [데이터 식별](data-identity.json), [actdiag 원문](actdiag-reference.md).

A/B 모두 wheel별 실제 이산값−0.35/0/+0.35의3분류 head, 연속 pulse/PWM, 기존 balanced completion BCE·CVAE KL10을 사용한다. 기존 wheel L1 네 항을 제거하고 유효 class label CE 평균(계수1)을 쓴다. 같은 ImageNet 초기화·batch8·chunk8·10Hz·학습 step20000(300smoke 포함)이며 검증/보류 성능으로 checkpoint를 고르지 않았다. compact history는 최근5개 자기 명령을 남긴다. 근거는 TRAIN same-sign nonzero wheel run8293개의 중앙5틱(0.5초),p25=1/p75=18이다. 원16개 중 오래된11개의 normalized14차원은 TRAIN mean0으로 가린다. B는 최근5개의 wheel/pulse40scalar만 추가로 가린다. PWM/age·고정 번호표·시계·자기 RGB는 A/B가 같다. act16a 계획의 해당 whole-history dropout은0이며 동일하게 유지했다. 기본 state252차원·카메라/FOV·학생 실행기는 바꾸지 않았다.

[번호표 검사](role-comparison.md): 같은 저장 cold-start40개에서 번호표만 교환하면 첫wheel class 변화 A3/40·B2/40,8틱chunk 변화 A6/40·B4/40, pulse-weighted 명령 방향 반전 A1/40·B0/40이다. 별도 validation 첫 접근29개에서 wheel 변화 A1·B0, 정확한 방향 반전은 둘 다0이다. A의 과거 float 순수 회전 잔차를 방향 반전으로 센1건은 정수 단위0.35/4로 재계수했고 원본·정정 sideasset을 모두 보존했다. 두 문맥/단위를 합산하지 않는다. 첫 접근 방향의 번호표 민감도가 낮지만 role을 완전히 무시한다고 단정하지 않는다.

[영상 A](A-playback-review.md)·[영상 B](B-playback-review.md): 각 실패2회 전체2Hz12장·마지막10초10Hz10장·실패 원해상도6장 이상을 직접 읽었다. GCP2에서 생성·ffprobe 확인한3배속 영상은 각8MB 미만이며 Mac 화면 앱을 열지 않았다. 성공 학생이 없어 별도 교사8328003 성공 영상도 직접 보되 학생 분자에 넣지 않았다. A8329001은 배정된 파랑/청록 끝에 각각 접근했다. B8329001은 파랑 담당r1이 청록 끝에 접근했고 r2는 빔을 놓친 뒤 반복 회전했다. B8329000은 r1 끝 근처의 작은 반복·r2 몸체 가림/정체가 지속됐고 파지는 없었다. 이 사례를 전체 실패의 단일 원인으로 넓히지 않는다. 각12장 실패 프레임, 전체 strip·원본 hash·타임라인을 보존했다.

입력 감사: A24000/B23292 자기 입력·명령 행의 forbidden/teacher/invisible/held_world/top=0, 명령/자기 이력/프로토콜 replay 불일치=0. 교사 행동·정답 보정0,weld off. A35620/B34701 raw파일과 A96000/B93168 자기 RGB참조 해시를 확인했다. [감사](input-audit-summary.json), A/B-integrity.json. 완료된64KiB 초과 JSON/JSONL은 무손실zstd·decoded SHA·manifest 후 보존했고 압축 뒤 raw 전체 해시를 다시 확인했다. 원본 RGB·가중치·optimizer·git-shared는 보존했다.

학습은 gcp2 기존L4(g2-standard-8)를 공유했다. main wall A10120.58초/B12782.31초, smoke A309.48초/B126.76초 별도다. shared-load이므로 속도 비교 근거로 쓰지 않는다. B는 기존 VM 창의1498step에서 cap_end로 저장·재로딩하고8시간 정상 종료 뒤 optimizer/sampler/torch/CUDA RNG를 이어 최종20000까지 완료했다. VM8h·idle20분·budget-stop 유지, 다른 작업 중단0,gcp1 접근0. 보존 공간 확보를 위한 L4 디스크100→140→180GB 온라인 확장은 자원 기록에 남겼다. Mac 중계의 일시 네트워크/API 종료 후 A 완료 결과를 재검증·재사용하고 살아 있는 B에 재연결했다(새 A 시뮬·새 B 학습0). [복구](relay-recovery.json), resource-plan.json, A/B-managed-* 기록, controller-state.json.

학습 source4747c4144a972e348a9ae4c7bbcc769ad116106d, 오프라인/학생 source5ad43e1e096822d7a4ed2e7ce720c2900e7f5ff6, 후처리/콜드 검사/패키지 source67dd59df03ce5b84a695494bc83a0a0bc3c179f7, validation 축합 감사 source6f4fe4b3c1701cff7071f31e5bcdfc34b94938e9. 후보 head/학습/actor 코어는 첫 학습 SHA 이후 바꾸지 않았다.

실패 모델도 [A Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-a-v1)·[B Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-b-v1)에 보존했다. 각각 공개 ZIP 재다운로드·10파일 전체SHA·새 reference clone의 CPU worker ready:true를 확인했다. configs/model_artifacts.json에 URL·크기·SHA·소스를 등록했고 기존 asset을 덮어쓰지 않았다. A 정정/B 정확한 축합 audit sideasset도 공개 재다운로드했다. A/B-release-verification.json 참조. 이는 추론 자산 배포 검증이며 새로운 물리 성공이나 raw 데이터 전체 백업은 아니다.

짧은 비물리 검증 Mac16pass/2skip,GCP2 L4·CPU 각17pass/1skip, workflow dry-run3pass. core commit6fdcbf010의 전체CI는 통과했다. 후속 기록/중계 커밋의 최신CI는 GitHub 러너 배정 대기라 통과로 보고하지 않는다. PR545는 DRAFT이며 기본 off·NOT_READY를 유지한다. 남은 연구 문제는 정렬/파지 진입과 번호표에 따른 접근 선택이다. 새 학습·추가 물리 실험은 제출하지 않았다.

참고: [PyTorch CrossEntropyLoss](https://docs.pytorch.org/docs/2.14/generated/torch.nn.CrossEntropyLoss.html), [ACT 원 논문](https://arxiv.org/abs/2304.13705), 고정 LeRobot ACT89236ea0f4f81a81ca566081e20dd1ff5f823cbe의 설치 원문을 L4에서 직접 확인했다. 이 자료는 구조·loss 구현의 근거이며 우리 학생 성공을 보증하지 않는다. 자료는 로컬 프로젝트·GitHub에 보존한다.

정리: 자기 임대·중계·caffeinate가 종료됐고 CPU는 다른 임대/실행0을 재확인한 뒤 정상 정지해TERMINATED를 확인했다. L4는 다른 임대3개·실행7개가 있어RUNNING을 유지했다. [정리 확인](cleanup-observation.json).
