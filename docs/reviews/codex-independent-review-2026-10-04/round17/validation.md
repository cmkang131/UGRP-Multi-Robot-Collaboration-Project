# 17차 독립 검증

## Release

통합 검토자가 최종 script `1181cb53…1eb9d8`를 별도 stdout으로 실행해 golden `a66a5185…05ae30` 전체 byte 일치와11개 exact66ff source hash를 확인했다. 실제 tick delegation·upper queue·fixed status·issued-command hook을 연결했다. 정상/같은-segment receipt, peer abort/silence, sparse transit, open 미준비의6개 sequence와2개 entry/1개 busy-arm 대조가 범위다.

Released24.1→first reverse26.7→done30.1은 authored clock 값이다.137개 검사는 command/status sampling이며 고유 RGB137장이나 물리 접촉의 증거가 아니다. Busy arm은6초가 넘어도 후퇴를 시작하지 않는다. False synthetic view는 placed claim/log에 남고 done은 절차 완료이므로 task 성공 false positive로 판정하지 않는다. Geometry reviewer도 별도 source/command 의미를 검토했다. Full endpoint/geometry guard/lower port/physics는 실행하지 않았다.

## Completion

별도 검토자가 endpoint/status/job의5개 조건을 재실행해 golden `70cb4ac3…1aebc6` 전체 일치·3개 source hash를 확인했다. Upstream done/open은 선언한 prefix이며 실제 제어 종료와 연속된 전체 실행이 아니다. 서로 다른 두 fixture의 검증된 부분을 합쳐 full mission 성공으로 세지 않는다.

## Currentness

R8 beam ROI finding에 대해 통합 검토자가3개 pin/5개 관련 파일 중 존재하는14개 Git object hash를 직접 대조했다. 공유 edge 수락 결과를 그대로 반환하는 현재 robust wrapper와 HIGH provider/tracker 연결을 읽었다. 원 R8 evidence는 재작성하지 않았고 새 통합 RGB 실행도 하지 않았다. Source상 해소되지 않았지만 현재 공개 실행에서의 발생·영향은 미확인이다.

## Trace and precision

Trace map은 writer/record 연결에 관한 source-only 검토다. 다른 검토자가26개 exact source와 실제 직렬화 경로를 확인했다. 현재 저장되는 값과 메모리에만 있는 필드를 구분하고, 전역 unique ID가 아닌 array 순서나 logger version을 join 키로 쓰지 않는다. 실제 run artifact의 존재·완전성·현재 실패 원인을 검증한 것은 아니다.

Covariance precision의 독립 검토자는 단위·반올림 경계·현재 도달성 미입증을 source/math로 확인했으며 재실행을 추가하지 않았다. 작은 float 명령이 유지된 사실을 물리 motion으로 해석하지 않는다.

GitHub는 Markdown만, Mac은 작은 offline fixture·golden·별도 independent JSON·manifest와 상세 QA를 보존한다. Final release/done은 Python3와 exact66ff Git objects를 가진 clone에 `--repo`를 지정한다. Precision fixture는 기존 round16/evidence의 carry helper/source와 NumPy가 필요하다. 새 임시 폴더로 상대 구조를 복사해 stdout을 새 파일에 쓴다. 기존1–16차 자료와 원고13개는 보존했다.
