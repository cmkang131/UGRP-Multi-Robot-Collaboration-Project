# 선택 gcp2b 재현 준비

실행 VM은 아직 생성하지 않았다. 전체 GPU 할당량1/사용1이므로 무부하 대기열을 유지한다. 이는 새 VM/측정 완료 기록이 아니다.

Mac에서 물리/렌더 없이 committed Git 객체만 pack했다. metadata와 필요한3개 tree blob만 포함하며 과거 blob/로컬 설정/자격 증명은 복사하지 않았다. 953419471B pack은 로컬 임시 폴더에만 있고 Git에 넣지 않는다. network upstream 없는 canonical에서3소스 checkout과 clean 상태를 검증했다. 실제 VM에서는 `/home/ugrp/ugrp-sim/git-shared.git`을 canonical로 만들고 모든 소스 사본은 이 저장소를 직접 `git clone --reference ... --no-local --filter=blob:none` 한다. canonical gc/prune/삭제나 사본 reference 사슬은 금지다.

controller f0db, teacher6f057f7e, warm2b99를 사용한다. 고정 compiled model의 절대 roller STL 경로를 보존하려고 teacher는 실제 clone을 `/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e`에 둔다. symlink는 Path.resolve로 XML hash를 바꾸므로 대체하지 않는다. warm 작업 디렉터리는2b99 소스 루트다.

CPU 영속 디스크의 `/home/ugrp/ugrp-sim/runs/warp3-bootstrap/warp-env-and-reference.tar.gz`는323783726B, SHA256 c919277d10ad6d7be117a4d7be25c5b82e54e9d944074701769357379923308c다. 동일 절대 prefix에 복원할 Linux 환경과 compiled-312.json/compiled-geometry312.npz만 포함한다. **compiled-geometry312.npz.json도 따로 필요하다**. 현재 Mac 임시 metadata 사본은57876B이며 source XML SHA856f16e5c3c13cf3d12d9cb2c0e2b0ae0f9d0351ec7ec2d6423dc24c37c93a69, NPZ SHAa080744a3b145af3475cdbc837b2e5d2ff678dfb41179aa266fd93a9a0211113를 명시한다.

VM 생성/재시작 직전 quota·budget-stop·실제 정지 원인을 다시 확인한다. 다른 작업/VM을 중단해 quota를 비우지 않는다. gcp2b도8h/idle20분/budget-stop과 lease 규칙을 유지하고, N64와N256을 같은 boot에서 측정한 뒤 다른 lease/process가 없는지 확인하고 정지한다.
