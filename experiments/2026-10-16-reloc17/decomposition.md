# 분해/폐루프 재집계

|조건·시드|상태·종료|등록 프레임|절대 주행 xy 중앙/p95|동일 주행 명령만 xy 중앙/p95|명령만 전체 xy 중앙/p95|
|---|---|---:|---|---|---|
|a_command_only 93584|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|0|미측정 N=0|0.0475/0.1066 (N=132)|0.0382/0.0956 (N=301)|
|a_command_only 93583|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|0|미측정 N=0|0.1278/0.2129 (N=113)|0.0488/0.2256 (N=301)|
|b_old_reloc15 93584|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|216|0.0444/0.1082 (N=45)|0.0404/0.0602 (N=45)|0.0345/0.0605 (N=301)|
|b_old_reloc15 93583|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|219|0.0853/0.1102 (N=33)|0.0870/0.0915 (N=33)|0.0456/0.0876 (N=301)|
|c_new_reloc15 93584|HOST_ERROR {'status': 'HOST_ERROR', 'category': 'selfmap4_relocalization_exhausted', 'reason': 'selfmap4_relocalization_exhausted', 'elapsed_sim_s': 53.400000000000006, 'supervisor_stop': {}, 'code_vs_host': 'controller_budget_exhaustion'}|0|미측정 N=0|0.0423/0.0607 (N=18)|0.0198/0.0487 (N=268)|
|c_new_reloc15 93583|HOST_ERROR {'status': 'HOST_ERROR', 'category': 'selfmap4_relocalization_exhausted', 'reason': 'selfmap4_relocalization_exhausted', 'elapsed_sim_s': 48.400000000000006, 'supervisor_stop': {}, 'code_vs_host': 'controller_budget_exhaustion'}|0|미측정 N=0|0.0035/0.0035 (N=1)|0.0310/0.1072 (N=243)|
|d_new_reloc16 93584|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|0|미측정 N=0|0.0740/0.1358 (N=107)|0.0552/0.1668 (N=301)|
|d_new_reloc16 93583|RECORDED {'status': 'RECORDED', 'category': 'cap_end', 'reason': 'sim_time_cap', 'elapsed_sim_s': 60.0, 'supervisor_stop': {}, 'code_vs_host': 'see_reason'}|0|미측정 N=0|0.1035/0.2073 (N=140)|0.0458/0.1962 (N=301)|
