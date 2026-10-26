---
bump: patch
---

The dashboard refresh can no longer publish an empty activity feed when its GitHub
fetch fails: a failed fetch is now "unknown" and the published feed is kept, and
the run exits non-zero instead of reporting success.
