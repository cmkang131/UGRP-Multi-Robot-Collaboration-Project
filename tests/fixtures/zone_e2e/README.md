# P03 composition fixture

`vision_loc_provider_p03.json` is the unchanged P03 file from PR #312,
commit `919f78ef6ebaf2495633338bcb1b9510f46399bd`, at
`configs/vision_loc_provider_p03.json`.

`vision_loc_worker_p03.json` is the unchanged `configs/vision_loc_worker.json`
from that same commit, referenced by the P03 pin. Its description differs from
main, so the temporary composition includes both files. The pinned current-tree
worker is never edited.

P07 uses it only in a temporary source tree to reproduce C311-1. It is not a
runtime registration or execution approval. Tests copy the referenced local
source assets and never load the candidate checkpoint or start a provider.
