# 저장공간 자동화 — 2026-10-11

사용자 승인: “저장공간 문제도 알아서 해결해주라”. 과거 메타데이터 소급,
종료 PR DEV와 PR 없는 7일 지난 DEV 정리, Mac 휴지통/ARM 삭제, 자동 일정과
압박 단계, 공통 실행 종료 경고/압축을 구현한다. 기준 main은 PR #435
`7c97ef2a755a036ea71ea23cfd32374d0802af2e`이며 구현 실행 SHA는 summary.json에 남긴다.

삭제 후보를 SHA-256 포함 dry-run으로 검토한 뒤 1회 execute한다.
새로운 소급 메타데이터는 과거 실행이 당시 등록됐다는 뜻이 아니다.
class/pr/branch/SOURCE_SHA/note를 기록하고 원래 RUN_META와 EXIT는 덮어쓰거나
만들어내지 않는다. 명시적인 study/milestone과 부모 등급은 보존한다.

대표 mp4와 관련 data, 영구 텍스트·요약·명령·원장·모든 파일 해시, 열린 PR,
실행/테스트 사용, 최근24시간 변경 자료를 보호한다. 알 수 없는 과거 자료도
class=dev/pr=null/note로 등록해 완료·7일·사용 여부에 따라 정리한다.
초기 1회는 --include-orphans, 매일은 종료 PR DEV, 압박이 지속되면 PR 없는 DEV다.
완료 EXIT 없는 자료와 .incoming 복사본은 완료로 간주하거나 정리하지 않는다.

구현과 설치는 [디스크 관리](../../docs/disk_management.md#8-사용자-승인-자동-정리-2026-10-11-후속)에 있다.
Mac 사용자 LaunchAgent가 매일/5분 여유 검사로 Mac·ARM SSH 작업을 조정한다.
Mac 수면/로그아웃 중에는 동작하지 않는다. Mac 휴지통 이동은 공간 회수를 보장하지 않으며
자동 비우기는 하지 않는다. 휴지통 10GiB 초과와 조회 실패/바닥 미달은 알림 파일로 남긴다.

ARM의 gh 부재는 Mac의 실시간 PR API 목록을 SSH stdin으로 전달해 해결했다.
목록은5분만 유효하고 삭제 직전에도 확인한다. 4분이 지나면 같은 SSH 파이프로 Mac API 재조회를 요청한다. 인증정보는 서버에 복사하지 않는다.
ARM stock-bot·crontab·기존 systemd 설정을 변경하지 않는다. 첫 execute는 ugrparch 소유 하위 디렉터리의 쓰기 권한으로 ARM이 중단되어 기록했다. 후속은 sudo -n으로 이 UGRP 작업만 수행하며 기존 파일의 chmod/chown·그룹 변경은 하지 않는다.
Azure용 --host azure와 적용 명령만 준비했으며 Azure/x86 접속·시작·중지는0회다.

검증은 변경 영역의 시험3파일이며 CI 조회·폴링·병합은 하지 않는다.
실제 공통 래퍼에 작은 합성 JSON1개를 넣고 종료·실제 lsof 사용 검사·zstd·해제 SHA-256·
명령 자식 종료를 확인했다. 물리·렌더·모델 호출은0회다.
원본 목록/개별 해시는 호스트 cleanup-records와 각 실행 ALL-hashes/PRUNED-hashes에 보존하고,
Git에는 짧은 요약/원본 경로/크기/해시만 남긴다. Google Drive는 사용하지 않는다.

참고 자료:
- [Apple launchd 공식 문서](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html):
  StartInterval/StartCalendarInterval의 표준 주기 실행을 따랐다. KeepAlive 없이 사용자 작업으로 설치한다.
- [Zstandard 공식 CLI](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md):
  기존 -3/-T1/압축 해제 경로를 재사용하고 별도 전체 SHA-256 복원 검사를 유지했다.
- systemd.timer 공식 페이지는 이번 조사에서 열람 실패했다. 이 작업은 ARM timer를 추가하지 않고 Mac launchd+SSH를 사용한다.

일정·7일·24시간·300MiB·각 바닥은 연구 표준 수치가 아닌 사용자/프로젝트 결정이다.

대량 프레임의 기존 진행 영수증이 후보 목록 전체를 매번 다시 쓰는 문제를 발견해 append+flush+fsync JSONL journal로 바꿨다. 부분 삭제 실패를 주입해 남은 파일·전체 해시·완료 journal이 보존되는지 검증한다. 근거는 [Python os.fsync](https://docs.python.org/3.12/library/os.html#os.fsync)와 기존 검증된 압축 manifest writer이며 판정/원본은 바꾸지 않는다.

최종: Mac1,627곳·ARM573곳의 새 RUN_META를 전체 읽기/해시로 확인했다. Mac 한 곳은 소급 후 PR 없음에서 실제 #433으로 정정되어 현재 값을 그대로 보존했다. 최종 실행은 양쪽 오류0·삭제 후보0B이며 열린/최근/미완료 자료를 보존한다. 여유는 초기 dry-run Mac124.453/ARM92.135GiB에서 최종 execute 후124.244/92.119GiB다. 동시 호스트 활동이 포함되어 저장공간 회수로 표현하지 않는다.

최종 시험53개·2subtests 통과, 실제 SSH의 만료 PR 목록 재조회와 두 호스트 report.json.zst의 해제 SHA-256을 확인했다. LaunchAgent를 실제 kickstart하여 종료0과 ARM 연결 오류 없음도 확인했다. 자체 요약 JSON도 종료 직후 검증 압축하므로 정리 기록 자체가 큰 JSON으로 계속 쌓이지 않는다. CI/독립 정책 검토·병합은 남아 있으며 조회·폴링하지 않았다.
