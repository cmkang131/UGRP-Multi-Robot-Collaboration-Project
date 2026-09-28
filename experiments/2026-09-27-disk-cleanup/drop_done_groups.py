#!/usr/bin/env python3
"""Drop fclones groups already cloned by the 2026-09-26 dedupe (all paths in its manifest, same size/mtime).

Usage: drop_done_groups.py <old-manifest.tsv> <fclones-group.json> <out.json>
"""
import json, os, sys
old_manifest, groups_in, out = sys.argv[1:4]
done = {}
with open(old_manifest, encoding="utf-8") as handle:
    next(handle)
    for line in handle:
        _g, path, size, digest, _mode, mtime_ns = line.rstrip("\n").split("\t")
        done[path] = (int(size), digest, int(mtime_ns))
data = json.load(open(groups_in))
kept, dropped = [], 0
for group in data["groups"]:
    same = True
    for path in group["files"]:
        prev = done.get(path)
        if prev is None or prev[1] != group["file_hash"]:
            same = False
            break
        try:
            st = os.lstat(path)
        except OSError:
            same = False
            break
        if st.st_size != prev[0] or st.st_mtime_ns != prev[2]:
            same = False
            break
    if same:
        dropped += 1
    else:
        kept.append(group)
data["header"]["prefiltered_by"] = "drop_done_groups.py: groups whose every path was in the 09-26 dedupe manifest"
data["groups"] = kept
json.dump(data, open(out, "w"))
print(json.dumps({"groups_in": len(kept) + dropped, "dropped_already_cloned": dropped, "kept": len(kept),
                  "kept_redundant_bytes": sum(g["file_len"] * (len(g["files"]) - 1) for g in kept)}))
