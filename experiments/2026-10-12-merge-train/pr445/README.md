# PR445 merge-train CI repair

Generic experiment module imports collided in the full CI shard.
Exact-path loading and scoped import state preserve experiment sources.
Offline import isolation: 9 passed, including foreign module cache restoration.
Azure lifecycle tests: 50 passed, 12 skipped; no VM operations.
See summary.json for source, evidence path/hash and Python documentation.
