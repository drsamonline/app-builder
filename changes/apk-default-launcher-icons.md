---
bump: patch
---

The APK template now ships its default launcher icons in the tree, so a checkout of
this kit compiles on its own. Before this, `AndroidManifest.xml` referenced
`@mipmap/ic_launcher` and `@mipmap/ic_launcher_round` but `res/` carried no mipmap -
the icons only ever existed after the "Generate the launcher icons" step had run.
Callers pin this workflow at a SHA that predates that step while the kit checkout
follows the default branch, so eighteen repositories failed on 2026-10-28 with
`AAPT: error: resource mipmap/ic_launcher not found`. The monogram defaults
(make_icons.py's own fallback tile) are committed at all five densities, the build
step still overwrites them with the app's real icon, and `tests/test_manifest_icons.py`
now asserts that every `@mipmap` the manifest names resolves straight out of git.
