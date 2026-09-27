# Pair dev 실행 승인과 v5f 등록

PR #240 후속(v5f)은 `dev11/907`, `dev12/908`의 미실행 코호트다. 판정 임계값,
화물·주문·개입, SIM/wall 예산, `cargo_noslip_v1`, weld OFF는 v5e와 같다.
과거 등록은 보존하며 변경된 소스에서는 해시 불일치로 거부한다.

`--execute` 자체는 승인이 아니다. 기본 실행은 prepare-only이며 사전등록의
`execution_authorization`이 없거나 null이면 물리 실행을 거부한다. 이슈 번호에
묶인 하드코딩 보류는 제거했다. 코디네이터가 실제 실행을 승인한 **이슈 댓글**을
참조하여 실행 직전에 아래 필드를 추가한다. 이번 구현 작업은 승인을 생성하지 않는다.

```json
{
  "execution_authorization": {
    "by": "coordinator",
    "ref": "https://github.com/kcm0127-dotcom/ugrp/issues/<number>#issuecomment-<id>",
    "source_sha": "<실행할 커밋의 40자리 SHA>",
    "registration_sha256": "<사전등록의 registration_sha256>",
    "sha256": "<이 객체에서 sha256만 뺀 canonical JSON의 SHA-256>"
  }
}
```

등록과 승인 해시는 `scripts/zone_pair_authorization.py`의 `digest()`를 사용한다
(`sort_keys=True`, `separators=(',', ':')`, `allow_nan=False`).
`registration_sha256`의 대상은 사전등록 전체에서 **`registration_sha256`와
`execution_authorization` 두 키만 제외한 내용**이다. 승인 안의 `source_sha`도
등록 해시 밖에 있으므로 소스와 등록을 커밋한 다음 실제 HEAD를 적을 수 있다.
기존 최상위 `execution_source_sha: null`은 보존용이며 실행 권한을 부여하지 않는다.
실행 권한의 SHA는 승인 객체 안의 `source_sha` 하나다.
`execution_readiness.coordinator_decision`은 과거 도크 배치 결정의 출처이며,
이번 코호트의 `execution_authorization`을 대신하지 않는다.

실행 직전 검사:

1. 등록 본문의 해시, scene/grasp/profile/input 원본 해시 및 기존 판정 규칙을 검증한다.
2. 승인 객체의 닫힌 키 집합, `by`, 저장소 이슈 댓글 URL, 승인 해시를 검증한다.
3. 승인 `registration_sha256`은 현재 본문과, `source_sha`는 `--expected-source-sha`
   및 실제 HEAD와 같아야 한다.
4. 선택한 사전등록은 현재 checkout의 추적 파일이어야 한다. HEAD의 등록 본문과
   현재 파일 및 index의 등록 본문과 저장된 등록 해시가 같아야 한다.
   본문은 canonical JSON 해시로 비교하므로 `1`/`1.0` 같은 타입 변경도 거부한다.
   **그 파일의 승인 객체 변경만**
   dirty 예외다. 다른 수정·미추적 파일·rename은 모두 실행을 거부한다.
5. 기존 `sim_cli` 관리 자식, 살아 있는 owner/branch 잠금, task worktree,
   기본 checkout `outputs/` 아래의 새 절대 출력 경로 요구는 그대로다.
6. prepare manifest는 등록 해시, 승인 객체, 전체 사전등록 파일 해시와 원본 바이트를
   보존한다. 준비 중·실행 진입 직전 파일 바이트 및 소스를 다시 확인한다.

해시는 내용 무결성과 결합을 확인한다. 코디네이터 신원이나 GitHub 댓글 작성자에 대한
암호학적 인증은 아니다. 댓글의 실제 승인 여부는 코디네이터의 책임이며 러너는
네트워크로 댓글을 조회하거나 승인 메시지를 게시하지 않는다.

승인 추가 후 commit하면 HEAD가 달라져 승인 SHA가 맞지 않는다. 먼저 소스와 등록을
커밋하고, 그 HEAD에 대한 승인 객체만 마지막에 작성한다. 실행 이후 승인 원본은
manifest와 복사된 prereg에 남는다. 소스/등록 본문을 변경하면 재등록·재승인이 필요하다.

현재 `prereg_v5f.json`의 승인은 null이며 물리 실행은 하지 않았다.
