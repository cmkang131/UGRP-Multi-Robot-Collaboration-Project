# R22 · #3 원격 보관·복구에서 확인한 계약과 남은 운영 증거

**새 버그 0개, 운영 완료는 미입증이다.** #3의 완료 조건은 지원 도구가 존재하는 것을 넘어 선택한 증거를 다른 환경에서 실제로 확보할 수 있는지까지 요구한다. 이번에는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 문서와 이전 도구 감사 범위만 대조했다. 실제 `outputs/`, 원격 저장 내용, 사용자 원자료·모델·영상은 열지 않았으며 업로드·다운로드·삭제·복구를 실행하지 않았다.

공식 [#3](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/3)은 R19의 2026-10-04 09:12 UTC 조회에서 open이다. 본문은 hash만으로 원격 백업을 대신할 수 없다고 구분하고, 허가 위치 보존·읽기/hash 검증·접근 및 복구 절차·별도 환경의 대표 진단 입력 확보를 완료 기준으로 둔다. [유일한 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/3#issuecomment-5844318863)은 ignored outputs가 worktree 제거와 함께 손실된 과거 사고를 가리킨다. 이번에 사고 원본이나 현재 남은 사본을 다시 조사한 것은 아니다.

## 현재 도구가 제공하는 것

| 지원 경로 | 문서/기존 검토가 뒷받침하는 부분 | #3의 완료 증거로 부족한 부분 |
|---|---|---|
| 선택 모델 `models pack/fetch/verify` | [모델 배포 문서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/model_artifacts.md)는 등록 파일·archive·내부 hash 검사와 새 폴더 설치/재다운로드를 정의한다. R4 소스 감사 (Mac: `evidence/review-notes/round4-source-contracts.md`)는 ZIP membership/hash/type/lock의 확인 범위를 남겼다. | 선택된 weight/config/adapter의 배포 계약이다. 문서 96행도 학습 원시 데이터·영상 전체의 백업과 구별한다. 모델이 내려받아진다는 사실을 모든 과거 진단 입력의 복구로 확대하지 않는다. 이번에 Release 자산 존재·다운로드·로딩을 재검증하지 않았다. |
| Colab 실행 결과 회수 | [Colab 문서 24–52행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/colab_simulation.md#L24-L52)은 고정 source, 원격 실행별 ZIP, 로컬 회수/hash 검증을 구분한다. `verified-result.json`의 의미는 회수·무결성·프로세스 종료다. | 로컬 ZIP은 원격 백업이 아니며 VM 삭제 전 미회수 파일 수명도 별도다. 중간 물리 상태 복원을 제공한다고 쓰지 않는다. 정상 collector 경로도 지속 보관 위치·보존 기간·별도 환경의 restore를 자동 입증하지 않는다. |
| 선택 Colab/Jev checkpoint 회수 | [R9/R10 회수 감사](../round10/collection.md)는 개별 archive 검증과 기대 checkpoint 집합의 완전성을 분리했다. 완료 phase 누락을 완료로 세는 기존 조건부 반례는 그대로 참조한다. | `collection_complete` 하나로 전체 raw backup이나 복구 완료를 인증할 수 없다. 기존 반례를 새 결함으로 재계수하거나 실제 과거 손실이라고 추정하지 않는다. 이 라운드에서 수정 여부/재현을 다시 검사하지 않았다. |
| Kaggle `collect` | [Kaggle 문서 59–71행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/kaggle_simulation.md#L59-L71)은 종료 상태에서 회수하고 실패 로그를 보존하며 ZIP 부재를 완료로 표시하지 않는 계약이다. | 입력용 private Dataset, 원격 job 결과, 회수한 로컬 archive는 용도가 다르다. 일반 로컬 raw 전체를 원격 백업하는 호출자로 읽지 않는다. R4 source reuse 계보 문제는 이미 검토했으며 여기서 다시 발견으로 세지 않는다. |
| worktree 은퇴·hash 기록 | [AGENTS 53–55행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/AGENTS.md#L53-L55)은 ignored outputs를 기본 checkout으로 옮기고 파일 수/bytes/hash를 확인하는 규칙, source branch 보관과 raw 위치를 구별한다. | 같은 로컬 저장장치에서의 이동·Git source branch·hash 목록은 독립 사본의 복구 시험이 아니다. 은퇴 도구의 실제 현재 파일 처리나 원본 존재는 이번에 확인하지 않았다. |

## 보존 정책과 완료 기준을 섞지 않기

현재 [AGENTS 55행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/AGENTS.md#L55)에는 2026-10-04 사용자 결정이 반영돼 있다. 요청·응답 텍스트, 원장, 결과/trace와 제거 이미지 hash 목록은 보존한다. 이미지 원본은 진행 중 작업/열린 PR/테스트, 최근 3일, 버전별 대표 영상, 앞으로 사전 등록한 본 연구 코호트의 범주를 남기고, 범주 밖 과거 이미지 정리는 정해진 휴지통/기록 규칙을 따른다. 이 외의 raw 처리·외부 이동은 기존 등급별 결정 범위다.

따라서 오래된 #3 본문의 저장 위치 선택 전 로컬 삭제 보류 문장을, 뒤에 승인된 선별 이미지 정리까지 다시 막는 요구로 만들지 않는다. 그렇다고 승인된 이미지 정리나 hash 보존이 이미 별도 환경 복구를 입증한 것도 아니다. 복구 가능 범위는 **정책에 따라 실제로 남기기로 한 bytes**를 기준으로 설명해야 한다. hash는 남지 않은 pixel/log 내용을 되살리지 않는다. 이번에는 삭제를 요구하거나 수행하지 않았다.

[디스크 문서 4·5·9절](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/disk_management.md)은 대상 등급·선별 보존·외부 위치 기록을 안내한다. 저장 매체 후보와 가격 표가 있다는 사실은 해당 매체가 선택·구매·사용됐다는 증거가 아니다. 이 감사에서 매체를 추천하거나 현재 가격/서비스 한도를 검증하지 않았다.

| #3 완료 기준 | 이번에 확인한 상태 | 운영 완료를 확인할 때 필요한 좁은 증거 |
|---|---|---|
| 대상·기간 결정 | 선별 이미지 보존과 텍스트/log/hash 정책은 문서에 있다. 모든 raw를 무조건 복제하라는 새 요구는 없다. | 실제 대상 묶음과 해당 보존 범주의 대응. 사전 등록 코호트는 정한 기간을 연결해야 한다. |
| 허가 위치 보존 및 읽기/hash 일치 | 도구와 문서 계약만 확인했다. 현재 저장 내용을 보지 않았다. | 선택한 묶음의 위치·권한 범위와 새 읽기에서의 membership/hash 결과. credential이나 원본 내용을 리뷰에 공개할 필요는 없다. |
| 접근 위치·복구 절차 | 문서에는 모델 배포/클라우드 회수 절차가 있고, 외부 이동 뒤 새 위치를 기록하도록 돼 있다. | 대표 묶음의 안정적인 접근 경로와 실제 복구에 필요한 source/input 참조가 해당 인덱스에 연결돼 있어야 한다. 이번에 experiment 인덱스 전체를 열거나 부재를 단정하지 않았다. |
| 별도 환경의 대표 진단 입력 확보 | **미입증**. 새로운 환경·다운로드·복구를 실행하지 않았다. | 남기기로 한 대표 입력을 독립된 임시 환경에서 읽을 수 있고 예상 파일/hash가 맞았다는 기록. 이는 실제 로봇 성공 재실행이나 전체 과거 실험 재채점을 뜻하지 않는다. |

이 기준은 원래 이슈의 운영 의무를 도구 검사와 구별한 것이다. 새 백업 시스템 구축, 모든 과거 raw 공개, 전체 복구 실행이나 저장 비용 지출을 승인·요구한 것이 아니다. R4/R9/R10 및 보존 도구의 이전 발견은 기존 pin별 보고서로 유지한다. 이번 검토만으로 원격 원본이 없다고 단정하거나 #3을 해결됐다고 표시할 수 없다.
