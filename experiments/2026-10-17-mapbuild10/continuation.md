# 진행 체크포인트

MC20 소스9fa2aad39·후처리44a29092a 완료. gcp5 coarse R1/R2/R3 수렴0/19/20, 오수렴0, OFF개선0. R3 XY61.964/73.654mm(median/p90)>OFF43.216, yaw1.365/1.951<OFF3.311. gcp3 coarse3/560수렴(세스트림각1), 오수렴0, 개선0; global0/560. 결과회수/해시검증완료, 두VM TERMINATED(11:20 KST), 자기leases삭제, gcp3.empty .warp9-claim.lock 보존(holder0). 원본VM /home/ugrp/ugrp-sim/runs/mapbuild10-mc20 (zstd raw/original hashes receipts). 파일 operations/*-mc20-*.json와README/API/summary현재미커밋부분있음; 먼저기록commit/push필요. Mac시험27PASS(1.73s), GCP5core24PASS과구분. 전체CI no checks.

최신 조정자 지시: coarse모두요구표내이고 R3가짧은회전이므로, 62mm편향원인표(자기FK/입자수/리샘플/갱신주기/이동alpha Nav2기본대조), 418뷰wallcount분포를먼저, 실제길이≥3m·회전·공개시작상자무작위출발1–2녹화의 새물리1라운드승인. 별도코호트/큐+rejection_table+current_stack 통과후 gcp5만사용. 새실행에서는 authored box를 physics spawn전에고정, 실제pose는box내uniform; controller에는범위만전달. 기존MC는평가GT로상자를무작위놓은conditional; 실제publicbox실행과합산금지. 새조건의OFFvsAMCL은같은저장프레임으로평가, 끝/최대오차요구표로판정. 계정changmin5781@gmail.com/projectugrp-sim-e-1016/gcp5. CPU VM금지. Macsim/render/train/GUI금지. modelkeysVM금지.

현재의구현은StaticAMCL.runtime_qualified=false/adopted_pose=null. 기존mapbuild7_capture가정적CSM초기등록후중단하므로 장경로기록에는새기본off진단모드가필요. 모델/카메라/접촉/외관보존하고MJWarp native noslip0 재사용. 0.5m+/-30deg 공개box·route config를정적지도에서author후루프는자기RGB+발행명령+AMCL제안만써야함. 실제GT는setup/eval만.

추가의심(아직미검증): vendorlikelihood는z_rand/data.range_max, 현재port는100을hardcode. RGBscan은4m투영guard지만Nav2node가실제LaserScan.range_max와설정100의min을쓰는지공식소스로대조필요. 현재MC(100)점수는바꾸지말것. 공개기준과명목센서범위의차이를편향표에적고새상수임의튜닝금지.

SSH gcp5는기존alias정상; gcp3alias의gcp3setup경로는없어/tmp/mapbuild10-ssh.conf가gcp5setup/configs/gcp_hosts.json+gcpctl.py의gcp3entry로임시우회. gcp5setup CLI명시host사용. VM상태확인후작업시start→lease→끝proc/GPU/otherlease검사→직접stop. gitclone은VM git-shared.git 직접--reference, transport gitbundle 방식(가중치/자격증명없음). shared.git gc/prune금지.
