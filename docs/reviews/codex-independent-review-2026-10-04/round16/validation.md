# 16차 독립 검증

## Posture

통합 검토자가 standalone posture fixture를 별도 JSON으로 실행해 golden SHA `72ec7633…6874f4` 전체 byte 일치와19개 exact source hash를 확인했다. 현재 HIGH b-v6g factory/policy와 실제 `PairGraspRelook.tick`의 align→parent 위임을 추가로 직접 읽었다. `PairAlignRelook.tick`가 current 분기에 연결되며 `_set_look`의 parent는 PairStudent다.

Inspect visual 선택·fresh low-sigma report·합성 clock은 명시한 입력이고 전체 selector/endpoint/host/delayed facade는 실행하지 않았다. 실제 camera key lookup·settle·failure latch·receipt reset,12 moving-frame 보류·known endpoint·known stationary hold 대조가 범위다. Geometry reviewer도11개 별도 source의 exact key/loaded-vs-unloaded settle/사전 image 검사 순서를 교차 검토했다. Worker0은 image 미도착이나 추론 crash를 뜻하지 않는다.

## Carry alignment

독립 검토자가 actual source fixture의13개 schedule/gate 대조와3개 HIGH stored-mean 갱신 분기를 재실행해 golden `ea20137e…8f03db` 일치를 확인했다.14개 fixture source hash 및10개 covariance/report/MRO 연결을 대조했다. Pure helper/부모 barrier recorder 범위이며 실제 guard·GO·physical motion·uncertainty calibration을 대신하지 않는다.

Clipping과 threshold의 binary 결정 동치 조건, strict `>` 경계, same-source finite PSD covariance의 std_xy fallback, report round8과 unrounded σ의 차이를 반영했다. 실제 VIS3 estimate override는 yaw mean을 보정하고 covariance/std는 유지한다. 본문의 conditional Gaussian 계산은 실제 로봇 실패 확률이 아니다. NIST/Kruschke 원문 선택 범위와 모델 가정은 [출처](primary-sources.md)에 있다.

## Bounded coverage

| 범위 | 독립 검증 | 보장하지 않는 것 |
|---|---|---|
| PF v3 | golden `1863981f…129792` byte 일치,7 Git source hashes,정확 RNG/zero-range/receipt 대조 | 실제 broad-yaw 발생·pose 정확도·task 효과 |
| recovery reporter | golden `d8307667…31ca5f`,6source,실제 writer/manifest | 실제 relook 소요 시간·admission·전체 runtime |
| own job end | golden `b9d67dfa…32daf3`,7source,attempt ID/outcome/단일 정리 | full command batch/dispatch 안전성 |
| column strip |7source hash,default96열/half2 producer/consumer source cross-read | 실제 이미지 정확도·추가 실행 결과 |

상세 독립 QA와 원본 JSON을 Mac evidence에 두고 GitHub는 Markdown만 보존한다. Existing R10 helper/source를 재사용하는 PF fixture는 `round10/evidence/scan-receipt-repro.py`와 그 source 폴더가 필요하다. Carry-align은 인접 `carry-align-source/`의14파일·manifest를 읽는다. 나머지 command/caller fixtures는 pinned Git objects가 있는 clone을 `--repo`로 지정한다. 새 임시 폴더에 상대 구조를 복사하고 stdout을 새 파일로 저장해 원본 결과를 덮어쓰지 않는다.

R15의 현재 attachment·fixed-veto 및 모든 이전 본문을 소급 수정하지 않았다. 검토한 source는66ff이며 whole head·CI·실제 모델/physics 실행을 완료했다고 보고하지 않는다.
