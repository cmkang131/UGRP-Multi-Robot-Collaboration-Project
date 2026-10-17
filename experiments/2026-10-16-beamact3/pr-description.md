beamact2에서 wheel3값을 연속 회귀하고 자기 wheel/pulse 이력을 가린 문제를 actdiag 권고대로 비교했습니다. 기본 off인 wheel3분류+최근5개 자기 명령 이력을 구현하고, 같은 데이터·분할·seed20261015로 A(이력 보존)/B(마스크 유지)를 각각 final20000까지 학습했습니다. **학생 A0/20·B0/20, 둘 다 NOT_READY**여서 기본 경로로 전환하지 않습니다.

| 검증 지표 | A | B | raw persistence |
|---|---:|---:|---:|
|전체 wheel MAE|0.022876|0.030805|0.023129|
|8틱 재추론 wheel MAE|0.020701|0.030093|0.022809|
|안정 구간 wheel MAE|0.011423|0.021875|0|
|전환 wheel MAE|0.126417|0.111537|0.232231|
|학생 성공|0/20|0/20|폐루프 미실행|
|접근→정렬→READY→파지→3초들기|16→0→0→0→0|13→1→1→0→0|—|

recent5 길이는 TRAIN wheel same-sign run8293개의 중앙5틱에서 정했습니다(p25=1/p75=18). A/B의 차이는 최근 wheel/pulse40scalar 마스크뿐이고, act16a 계획의 whole-history dropout0을 유지했습니다. 데이터185episode, TRAIN166seed/60023행·validation19seed/6908행, 보류20seed8329000..8329019와 실행기는 beamact2와 같습니다. 고정 최종 checkpoint를 사용했고 검증 성능으로 선택하지 않았습니다. A/B·과거·호스트 결과를 합산하지 않습니다. 이 보류 세트는 이미 본 비교 세트입니다.

번호표만 바꾼 같은 cold-start40개에서 첫wheel 변화 A3/40·B2/40, pulse-weighted 발행명령 방향 반전 A1/40·B0/40입니다. 별도 validation 첫 접근29개의 정확한 wheel 축합 방향 반전은 둘 다0입니다. A의 과거 float 투영 잔차1건은0으로 정정했고 원본·정정 asset을 함께 보존했습니다. 영상에서는 A8329001이 배정된 끝에 각각 접근했지만 B8329001의 파랑 담당r1은 청록 끝을 택했습니다. 낮은 번호표 민감도를 role 완전 무시로 단정하지 않습니다.

원본 재계수: A cap_end20/B cap_end19·정렬실패1, HOST_ERROR 각0. 실패 단계 A정렬16/접근4, B정렬12/접근7/파지1. A35620/B34701 raw파일과 전체 자기 RGB 참조 SHA, A24000/B23292 입력·명령 행을 확인했습니다. forbidden/teacher/invisible/held_world/top=0, 명령/이력/프로토콜 재생 불일치0, 교사 행동·정답 보정0,weld off입니다. 각 실패2회의 전체2Hz·tail10Hz를 직접 보고6장 이상 원해상도 프레임과 타임라인을 남겼습니다. 학생 성공이 없어 별도 교사8328003 성공 영상은 비교로만 사용했습니다.

실패 모델도 [A Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-a-v1)·[B Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-b-v1)에 보존했습니다. 각각 공개 ZIP 재다운로드·10파일 전체SHA·새 reference clone CPU worker ready:true, 번호표 audit sideasset 재다운로드를 확인했습니다. configs/model_artifacts.json에 URL/크기/해시/소스를 등록했습니다. 원본 RGB·optimizer·checkpoint를 보존하고 큰 JSON은 무손실zstd 검증 뒤 압축했으며 raw파일 전체를 다시 확인했습니다.

실행은 gcp2만 사용했습니다. 공유 L4 main wall A10120.58초/B12782.31초이며 속도 비교로 쓰지 않습니다. B1498step cap_end 뒤 같은 optimizer/sampler/RNG로 재개했습니다.8h·idle20분·budget-stop을 유지했고 다른 작업을 정지하지 않았습니다. 종료 시 CPU는 다른 임대/실행0을 재확인하고 TERMINATED, L4는 다른 임대3개·실행7개가 있어 RUNNING으로 유지했습니다. Mac 물리·렌더·학습·GUI/모델 키 전달0입니다.

검증: Mac 짧은 비물리16pass/2skip,GCP2 L4·CPU 각17pass/1skip, workflow dry-run3pass, core6fdcbf010 전체CI 통과. 후속 기록/중계 커밋 CI는 GitHub 러너 배정 대기이며 최신 통과로 보고하지 않습니다. 모델 registry 조회와 최종 JSON/AST·diff 검증도 통과했습니다.

학습 source4747c4144a972e348a9ae4c7bbcc769ad116106d / 오프라인·학생 source5ad43e1e096822d7a4ed2e7ce720c2900e7f5ff6 / 후처리·패키지 source67dd59df03ce5b84a695494bc83a0a0bc3c179f7 / validation 축합 감사 source6f4fe4b3c1701cff7071f31e5bcdfc34b94938e9. 전체 결과·퍼널·거부 사유·원본 위치/SHA·영상·운영 기록은 `experiments/2026-10-16-beamact3/README.md`와 `summary.json`에 있습니다. 남은 연구 문제는 끝 선택과 정렬/파지 진입입니다.
