# ACT16w native 재기록·학습 결과

`nativecontact-ack`, `resume-ack`. **상자 1대 근거리 ACT 최종 평가는 A 0/40, NOT_READY**다.
91620–91659를 한 번 평가했고 색별 cyan/red/green/yellow가 각각0/10이다. 같은 색 아무 물체 성공도0/40이다.
원본 점수 재계수40개가 모두 일치했고 HOST_ERROR0·resource cap0, 명령 종료16·90SIM `cap_end`24다.
[확정 요약](summary.json), [전체 단계 관문표](all-stages-rejection_table.json), [최종 원본 재계수](native-final40-independent.json).
실행·학습·분석·렌더는 소유 gcp2 L4에서 수행했다. Mac은 소스/요약/이미지 확인만 했고 화면 앱은 열지 않았다.

| 후보 | 바꾼 조건 | VAL8 | 안정 들기 | 명령 종료 / cap_end |
|---|---|---:|---:|---:|
| A | 전체 발행 이력, h4/h5 off | 0/8 | 0/8 | 4 / 4 |
| B | 과거 바퀴·펄스128열 TRAIN 평균 마스킹 | 0/8 | 0/8 | 2 / 6 |
| C | A + h4 TRAIN 시작 커리큘럼 | 0/8 | 0/8 | 5 / 3 |
| D1 | C + h5 1회 | 0/8 | 0/8 | 1 / 7 |

각10000스텝·동일 초기화 시드20261015·batch8·chunk8·0.1SIM초·temporal ensemble off다.
A/B/C는 D0 동일 해시이며 D1도 D0 입력 정규화와 VAL3026행/8시드를 그대로 썼다.
훈련/추론의 이력 변환이 일치하고 네 모델 모두 저장/재로딩 예측 일치를 확인했다.
[h4 비교](native-h4-comparison.json), [h5 비교](native-h5-comparison.json)의 관찰 성공률 차이는0pp다.
이8회로 일반적인 효과 없음을 증명하지 않는다. [실제 학습 곡선](native-abcd-learning-curves.png)의 손실 감소를 임무 성공으로 해석하지 않는다.
[학습 완료/해시](native-ABCD-training-receipt.json).

모든 후보의 VAL 성공률과 기하 진단이 동률이라 사전 규칙의 A/off를 유지했다.
[선택 고정](native-final-selection.json)은19:36:21.857988Z이며 최종 평가 시작19:39:12.719358Z보다 이르다.
최종 결과를 본 뒤 체크포인트·입력·허용치·평가 시드를 바꾸지 않았다.

| 최종40 물리 관문, 누적 | 통과 | 직전 관문에서 탈락 |
|---|---:|---:|
| 채점된 실행 | 40 | 0 |
| 양손 하중 관찰 | 2 | 38 |
| 안정적 들기 | 1 | 1 |
| 안정적 내려놓기 | 0 | 1 |
| 임무 성공 | 0 | 0 |

[물리 순서 관문표](native-final-physical-funnel.json)는 명령 종료16회와 구분한다.
명령 종료16회에는 안정 들기가 없고, 유일한 안정 들기91637은 grasp900스텝 동안 완료를 내지 못해 cap_end였다.
그 실행의 최대 안정 들기 지속은73.1초다. [불일치 표](native-final-stage-disagreement.json).
기하 정렬 진단은40/40 미통과였지만91637은 안정 들기에 성공했다. 따라서 이 진단은 실제 파지 성공의
검증된 필요조건이나 전체 실패 원인이 아니다. [반례](native-alignment-diagnostic-counterexample.json)를 보존하고 임계값을 사후 조정하지 않았다.
[최소 틈·물체 이름을 보완한 표](native-rejection-table-final40-enriched.json)는 저장 자세의 기하 질의이며,
GPU 접촉력·실제 막은 물체·CPU 물리 견고성의 증거로 확대하지 않는다.
시작 프레임에서 같은 색2개 이상이 보인 실행은6/40이다.

실패91620·91621과 부분 들기91637의 전체0–90SIM초2Hz181장씩, 끝80.1–90초10Hz100장씩을 직접 보았다.
91620은 약7초,91621은 약14초부터 대상이 사라진 뒤 바닥 화면에 머물렀다.
91637도14초 이후 바닥 화면이지만 원본 물리 원장은 안정 들기73.1초를 기록했다. 영상만으로 들기를 판정하지 않았다.
[91620](native-final-91620-playback-review.json), [91621](native-final-91621-playback-review.json), [91637](native-final-91637-playback-review.json).
[몽타주](native-final-montage.png)의 세 번째 행은 **교사 성공 참고87429이며 ACT 성공이 아니다**.
학생 임무 성공 예는0개다. 영상 원본은 gcp2에 남기고 최종 Mac 회수는 프레임 띠·몽타주·요약으로 제한했다.
각 영상은 gcp2에서 ffprobe 확인·8MB 미만이며 전송한 모든 이미지/메타 파일 SHA가 일치했다.
생성기의 환경·이전 기록 형식·완료 출력 오류는 [후처리 기록](native-final-montage-postprocess-note.json)에 남겼다.
마지막 출력 예외 전에 생성된 PNG/JSON은 원 실행 소스 해시·파일 해시·직접 이미지 검토로 확인했다.

native 교사 관문87220–87259는40/40, 별도 기록87420–87459도40/40이다.
원시 Score40개씩 재계수와 원본 파일8254+8315개 SHA 검사가 일치했다.
18046개 native640×480/10Hz JPEG·발행 이력·교사 표적이 정합했고 선택된14886행은 TRAIN11860/32시작·VAL3026/8시작이다.
[관문](native-gate-independent.json), [기록](native-record-independent.json), [데이터 수신](native-dataset-receipt.json).
정식 teacher queue 없이 실행돼 원본 gate_eligible=false였음은 [조정자 측정 관문 수용 기록](coordinator-native-gate-recount.md)에 명시했다.
원본 장면의 적용 전 noslip10 표기는 [별도 주석](native-provenance-annotations.json)이 보완한다. 원본 flag/score/253파일은 바꾸지 않았다.
실제 최종7그룹40세계의 CPU/GPU noslip0과 warpfit 파일 해시는 [실행 설정 기록](native-final-contact-receipts.json)에 있다.

h5 TRAIN20 접두 궤적5427관측에서290 h0 라벨을 얻었다. 비초기270개는7시작에만 있고13시작은 초기 라벨뿐이다.
마지막 유효 시각12SIM초, 미래7표적 padding, D0 정규화 동일, held/invisible/교사 행동 실행0이다.
[자료 범위](native-h5-data-receipt.json), [파일242개 감사](native-dagger-dataset-files-independent.json).
전체 스킬/회복 교사 성공을 검증한 자료가 아니며, 이 TRAIN 접두 궤적의 cap_end14개를 학생 최종 분모에 넣지 않는다.
h1/h2/h3는 off·미구현·미평가다. 현재 RGB/작은 이동 후보도 후속 미실행 제안이며 이번 결과가 아니다.
후속 모델을 개발하더라도 이번 최종40을 새 독립 확증처럼 재사용하지 않는다.

교사 라이브러리6f057f7e → MJWarp controller f0db6b1a → 녹화API0362037을 구분한다.
실제 학습/평가 소스는c27a9d537, 후속 실행기37a8c8336, 사후 분석34d53cfa다.
warpfit df5a1f86a 프로필 파일 SHA256 `a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`는 byte 그대로다.
공용 backend/장면 수정0, weld off, 손으로 짠 근거리 학생 보정0, LLM/API 호출0이다. ACT forward 호출은 별도 계수되지 않았다.
첫30SIM 그룹 규모 가중 지연 중앙값39.98 wall/SIM은 속도 관문 미통과다. 시작/컴파일을 포함한 그룹 지연이며
일찍 끝난 그룹은 제외했다. 명시한 속도 예외로 평가했고 속도 통과로 보고하지 않는다
([명령·지연](native-final-first30-statistics.json), [종료 원본과 구간 해시 일치](native-final-first30-prefix-final-check.json)).

[모델 Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-act16w-native-v1)에
A/B/C/D1을 각각 보존했다. 공개 재다운로드·전체76파일 SHA·새 공개 태그805a3b440 체크아웃 CPU 로딩4개를 확인했다
([모델 확인](native-public-model-verification.json)). 기존 ACT 환경이며 새 가상환경/물리 성공/전체 원시 데이터 백업 확인은 아니다.
태그 생성 당시 staged 상태는 공개 verified catalog와 현재 `configs/model_artifacts.json`의 확인 기록이 보완한다.
원 실행기의 정적 업로드/검토 대기 표기도 [완료 후 별도 주석](native-delivery-status-annotations.json)이 실제 영수증에 연결한다.
[공개 최종 결과](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/models-20261016-act16w-native-v1/native-final40-results-v1.json)도
익명 재다운로드와 해시 일치를 확인했다([영수증](native-final-results-public-verification.json)).
noslip10 A0/5·B0/5와 그 두 모델은 별도 비교 자료이며 native와 합산하지 않는다.

타 임대0·타 Python/MuJoCo/ffmpeg0·GPU0%/0MiB를 확인한 뒤 소유 L4만 정지했고 **TERMINATED**를 확인했다
([정지 전](owned-VM-final-stop-check.json), [정지 후](owned-VM-terminated.json)). idle20·budget-stop 유지, wall 상한 없음, CPU VM 시작0이다.
[비용 기록](native-cost-accounting.json): 인수 관찰 구간5.965시간의 VM 계산비 추정$6.54, 전체 VM8.002시간은$8.77이다.
전체 VM에는 인수 전 사용이 포함된다. 저장된 Seoul g2-standard-8 단가$1.096224308/h를 썼고 실청구·크레딧 잔액·디스크/네트워크 비용은 조회하지 않았다.
A/B가 병렬이므로 각 optimizer wall 시간을 합쳐 GPU 임대 시간으로 보고하지 않는다.

원본은 `/home/ugrp/ugrp-sim/runs/act16w-native-{gate-r2,record-r1,dataset-r1,training-r1,experiment-r1}`와 관련 reference 디렉터리에 보존한다.
재현은 원본 JSON의 `reproduce`와 이 폴더의 `final-delivery.py`, `finalize-native-results.py`를 따른다.
단계별 당시 진행 기록은 [stage-history.md](stage-history.md)에 보존했다. PR #539, Refs #523은 draft이며 독립 제어/사전등록 검토가 남아 있다.
