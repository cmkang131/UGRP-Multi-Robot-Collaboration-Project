# S4 Azure first batch — execution blocked before VM start
Requested: 16 DEV cases from `93ebf735`, Gemma/Gemini × event on/off × four English conditions, seed603.
Result: 0/16 started; 16 BLOCKED_PRESTART, no robot failure or HOST_ERROR observed.
The plan has 16 null execution commands; the CLI rejects `--execute` with `AZURE_AND_OWN_MAP_ADMISSION_REQUIRED`.
Azure is authorized; own-map runtime integration remains absent. The authored-route fallback was not used.
No physics, rendering, model request, proxy or tunnel was started; carry/B placement are unmeasured.
`azctl stop` returned Already deallocated; status confirmed D16as_v5 / PowerState/deallocated in subscription 88b7ee7f.
This task VM use 0 h / compute $0; authorized cap 5 h / $4.24. Disk/IP charges excluded.
Evidence, hashes and all 16 cases: summary.json; raw `/Users/changmin/projects/ugrp/outputs/azure-s4-first-batch-20261011`.
Next implementation: executable own-map S4 adapter and frozen commands; preserve the preparation plan and historical cohorts.
