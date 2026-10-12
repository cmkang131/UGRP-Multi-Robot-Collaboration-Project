# 10/11 저장 규칙·도구·서버 적용

도구 소스 `d075136a0116d94dc4bbb4f2965d770c2c90e71d`, 정책 소스 `6750615d`. 사용자 요청에 따라 dev의 무거운 원본 수명을 PR 병합·종료에 연결하고 milestone/study·대표 증거·텍스트·명령·요약·해시를 보존한다. 물리·렌더·모델 실행은 하지 않았다. 실제 원본 prune은 실행하지 않았다. 전체 결과와 한계는 [summary.json](summary.json), 작업 기록의 해시는 [records-hashes.tsv](records-hashes.tsv)다.

## 확인한 것

- 기존 Mac 환경에서 바뀐 모듈의 시험 두 파일만 실행: `tests/test_storage_tools.py tests/test_ugrp_session.py`, **37 passed, 0 skipped, 2.09초**. 실제 zstd 압축/해제, 잘못된 해시·원본 크기 미확인·활성 실행·다른 열린 PR·대표 증거 보호를 확인했다. `bash -n`·`git diff --check`도 통과했다. 새 시험은 기존 CI 목록에 등록했다.
- 최초 `.venv-dev`에는 pytest가 없어 기존 `.venv-sim-worker-mac`을 재사용했다. 첫 시험에서 zstd 옵션 순서 오류 2건을 찾고 수정했다(31통과/2실패 → 최종 37통과). 환경을 새로 만들지 않았다.
- 36회 × 512 MiB(raw), Mac 5 MiB(fetch-lite) 예산 검사가 **x86 부족으로 exit 1**을 냈다. 이 예는 예산 검증이며 배치를 새로 제출하지 않았다. [검사 JSON](budget-36-final.json).
- x86 `/usr/local/bin/ugrp-auto-archive`를 실제 교체했고 기존 10분 timer를 재사용했다. 이전 파일은 `/usr/local/bin/ugrp-auto-archive.before-20261011-storage`에 남겼다. 초기 배포 해시 `cc026aa3...`의 자동 작업이 완료 배치 `egomap70-wave1`을 처리했다: 큰 JSON/JSONL **159파일 1,872,433,498 → 218,715,490 bytes**, 해제 SHA-256·rsync -c·전체 파일 SHA-256 대조 뒤 ARM 보관과 x86 링크 전환 완료. [원장·검증](x86-final-verification.txt).
- 최종 배포 해시 `e0184f81...`에는 평가 결과/표시 확인과 원본 불변·사용 중 재확인이 추가됐다. 이 버전으로 **합성 자료 105,000 → 61 bytes**를 압축·검증·실제 ARM 복사했고 ARM에서 다시 해제해 원본 해시를 확인했다. 요약·명령·전체 해시·메타데이터를 함께 확인했다. 첫 합성 시도는 실제 자동 작업의 배타 잠금 때문에 그대로 남았고, 그 작업 완료 후 성공했다. [첫 시도](x86-archive-smoke.txt), [최종 시도](x86-archive-smoke-final.txt), [ARM 확인](arm-final-verification.txt).
- 두 서버와 Mac의 설치 파일 전체 SHA-256이 저장소 파일과 일치했다. [비교 결과](deployment-integrity.json), [소스 해시](source-hashes.json).
- 세 호스트에 5분 여유 공간 경보를 실제 설치했다. x86·ARM은 user systemd, Mac은 LaunchAgent다. 모두 직접 시작해 exit 0과 활성 timer/300초 간격을 확인했다. x86에는 로그아웃 후 감시 유지를 위해 `loginctl enable-linger ubuntu`를 적용했다. ARM은 원래 linger=yes다. [x86 감시](x86-watch.txt), [ARM 감시](arm-watch.txt), [Mac 설치 구성](mac-watch.plist), [지속 설정](x86-watch-persistence.txt). ARM stock-bot 폴더·crontab은 조회·수정하지 않았다.

## PR 정리 dry-run과 남은 것

- 실제 GitHub 상태로 #424 MERGED와 같은 브랜치의 열린 PR 부재를 확인했다. Mac `outputs/`, x86 `~/ugrp-sim/runs`, ARM `~/ugrp-archive/runs` 모두 **삭제 후보 0 bytes**였다. 과거 실행에 RUN_META가 없으며, ARM의 새 합성 자료 한 건은 PR 미정이라 제외됐다. 0은 원본이 없거나 디스크가 비었다는 뜻이 아니다. [Mac](mac-pr424-dry-run.json), [x86](x86-pr424-dry-run.json), [ARM](arm-pr424-dry-run.json).
- #405는 OPEN이라 CLI가 정리를 거부했다. [거부 결과](open-pr-refusal.txt). 앞선 #430 상태 확인과 dry-run도 기록 파일에 남겼으며 실제 정리는 전혀 하지 않았다.
- 원격에는 gh가 없어 Mac의 실제 gh 결과를 사용하고 서버에서는 같은 `plan` 함수를 읽기 전용으로 호출했다. 서버에서 standalone prune CLI를 쓰려면 gh 설치·해당 서버의 인증이 별도로 필요하다. 토큰을 Mac에서 복사하지 않았다.
- RUN_META는 표준 `ugrp_session.py`의 옵션을 켠 새 배치부터 쓴다. 기존 scratchpad/기존 실행에는 소급 적용하지 않았다. 과거 PR·등급 분류, 모든 실행기에서 새 토글을 사용하도록 배치 명령 변경, 실제 PR 종료 시 prune은 남아 있다.
- 예산 도구는 전역 원자적 예약 큐가 아니다. 동시에 승인한 작업의 남은 쓰기를 합산해야 한다. 저용량 알림의 Mac 실제 화면 표시는 발동시키지 않았으며 낮은 공간의 종료 코드 1은 단위 시험으로 확인했다. 서버/절전 중 경보 부재는 제출 전 직접 검사로 보완한다.
- CI는 사용자 지시로 조회·폴링하지 않았다. PR의 CI·검토·병합은 아직 확인하지 않았다.

## 운영 위치·복구

- 서버 도구: `~/ugrp-storage-tools/scripts/`, x86 아카이브의 고정 의존성은 `/usr/local/lib/ugrp-storage/scripts/`. 감시 service/timer 원본은 `configs/storage_watch/`. x86 drop-in은 `~/.config/systemd/user/ugrp-storage-watch.service.d/host.conf`다. worktree 은퇴 뒤에도 설치 파일은 남는다.
- Mac 도구: `~/Library/Application Support/ugrp-storage-tools/`, LaunchAgent `~/Library/LaunchAgents/com.ugrp.storage-watch.plist`, 표준 출력 `logs/watch.jsonl`, 경보 `logs/watch.log`.
- 감시 중단은 본 작업의 timer만 `systemctl --user disable --now ugrp-storage-watch.timer`, Mac은 해당 plist만 `launchctl bootout`한다. 기존 다른 service/프로세스는 건드리지 않는다. x86 아카이브 롤백은 보관한 이전 파일을 원래 경로로 설치하면 된다. ARM의 옛 `compress-json.sh`와 기존 원본·압축본은 임의 정리하지 않았다.

## 참고 자료

[Zstandard 공식 CLI](https://github.com/facebook/zstd/blob/dev/programs/zstd.1.md)의 무손실 압축·기본 원본 보존과 [rsync 공식 매뉴얼](https://www.samba.org/ftp/rsync/generated-files/rsync.1.html)의 내용 체크섬 비교를 그대로 사용하고 해제 SHA-256·전체 파일 비교를 추가했다. [DCC 보존 자료 선택 지침](https://dcc.ac.uk/guidance/how-guides/five-steps-decide-what-data-keep)의 재현/재사용 필요에 따른 선택을 참고했다. 구체적 등급·PR 수명·여유 바닥은 10/11 사용자 결정이다. 확인하지 않은 인용은 없다.
