# app-builder — how to use the build kit

**Version 1.0.0 · PolyForm Noncommercial 1.0.0 · a reusable GitHub workflow**

Turns a single-file web app into a portable Windows `.exe` and an Android `.apk`, publishes both on
a fixed-tag release, and deploys the demo to Pages — from one workflow call.

## Call it; do not copy it

Add `examples/build-apps.yml` as `.github/workflows/build-apps.yml` in your app repo and set three
values:

```yaml
jobs:
  app:
    uses: drsamonline/app-builder/.github/workflows/build.yml@v1.0.0
    with:
      app_name: my-app        # -> my-app-portable.exe and my-app.apk
      app_src: docs/play      # folder containing your index.html (+ any assets)
      deploy_path: docs       # folder to publish to Pages ("" = do not deploy)
```

**Call the workflow; do not copy it.** The build, release and deploy live in the reusable workflow,
so a fix there reaches every app at once. An earlier hand-copied version of this file drifted and
kept `if: always()` on the release job — which *deleted* the published release before recreating it.

Pin a tag (`@v1.0.0`) or a commit SHA. A pin to `main` is not a pin: it changes under you.

## What the workflow does

On every push to `main` and on manual dispatch:

1. **`exe`** (`windows-latest`) — checks out your repo and this kit, copies `app_src/` into
   `exe/app/`, runs `python exe/build.py`, uploads `<app_name>-portable.exe`.
2. **`apk`** (`ubuntu-latest`) — installs the Android SDK packages, copies `app_src/` into
   `apk/app/src/main/assets/www/`, runs `gradle assembleRelease` for a signed `<app_name>.apk`.
3. **`version`** — consumes any `changes/` files and bumps `VERSION` and `CHANGELOG.md`.
4. **`release`** — publishes both artefacts on the fixed-tag release `app-latest`, created **only if
   missing** and then uploaded with `--clobber`. It never deletes the release first, so a failed
   build leaves the previous one intact.
5. **`pages`** — deploys `deploy_path` after the release lands.

A push that touches only root docs or metadata (`*.md`, `LICENSE`, `.gitignore`) is skipped by
`paths-ignore`, so a docs-only commit does not run the builder.

## Caveats worth knowing before you ship

- The **APK is debug-signed** — fine for sideloading, not for the Play Store.
- The **EXE is unsigned**, so Windows SmartScreen may warn on first run (*More info → Run anyway*).
  Code-signing is out of scope for this kit.
- Each run costs roughly **2 runner-minutes** (Windows + Linux); a cold Android build is the slower
  half because of the SDK and Gradle download.

## Licence

PolyForm Noncommercial 1.0.0. See [LICENSE](../LICENSE).
