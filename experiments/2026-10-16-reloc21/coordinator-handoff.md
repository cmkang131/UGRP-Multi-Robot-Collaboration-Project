
## 2026-10-16 12:1x coordinator note — user decision
User: "모두 MJWarp로 바꿔서 하게" (all simulation flows move to MJWarp). Finish the current CPU round R1 and record it as CPU diagnostics (never pooled). Do NOT start R2/R3 on CPU. Write your R1 root-cause table and the fixes you'd make into the record, push, and report "reloc21: CPU_R1_DONE …" on ops-alert. The MJWarp continuation of localization (selfmap + carry) is done by job warp5, which will read your record.
