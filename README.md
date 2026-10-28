# app-builder

**A shared build kit that turns a static web app into two offline deliverables: a portable Windows EXE and an Android APK.**

[![Landing page](https://img.shields.io/badge/landing%20page-open-2e7d32?style=flat-square)](https://drsamonline.github.io/app-builder/)
[![All projects](https://img.shields.io/badge/All%20projects-hub-2e7d32?style=flat-square)](https://drsamonline.github.io/)
[![Offline](https://img.shields.io/badge/offline-yes-2e7d32?style=flat-square)](https://github.com/drsamonline/app-builder)
[![Type: shared build kit](https://img.shields.io/badge/type-shared%20build%20kit-586069?style=flat-square)](https://drsamonline.github.io/app-builder/)
[![Tech: Python + Kotlin](https://img.shields.io/badge/tech-Python%20%2B%20Kotlin-3572A5?style=flat-square)](https://github.com/drsamonline/app-builder)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-2e7d32?style=flat-square)](LICENSE)

**Landing page:** <https://drsamonline.github.io/app-builder/> &nbsp;·&nbsp; **All projects:** <https://drsamonline.github.io/>


A small, reusable kit that turns a **static web app** into two double-clickable,
offline deliverables:

* a **single-file portable Windows EXE** (`<app>-portable.exe`) — a tiny Python
  launcher bundled with the app that serves it locally and opens the browser; and
* an **Android APK** (`<app>.apk`) — a dependency-free WebView wrapper of the
  same app.

Both work fully offline. A consuming app repo adds **one workflow file** and
gets freshly-built artifacts attached to a GitHub Release on every push.

---

## What's in here

```
exe/
  launcher.py        # serves the bundled app/ on 127.0.0.1 and opens a browser
  build.py           # PyInstaller --onefile build -> dist/<APP_NAME>-portable.exe
  requirements.txt   # pyinstaller
apk/
  settings.gradle.kts
  build.gradle.kts   # AGP 8.x + Kotlin plugin (apply false)
  gradle.properties
  app/
    build.gradle.kts            # compileSdk 34 / minSdk 24 / targetSdk 34, signed release
    src/main/AndroidManifest.xml
    src/main/java/com/drsamonline/appbuilder/MainActivity.kt
    src/main/res/values/strings.xml        # app label (placeholder, replaced by the workflow)
    src/main/assets/www/                    # <-- the app's HTML is copied here by the workflow
keystore/
  debug.keystore     # shared debug-grade signing key (see below)
tools/
  verify_exe.py      # inspects the built EXE: valid PE, executable, size budget, imports
examples/
  build-apps.yml     # the workflow a consuming repo drops into .github/workflows/
README.md
```

---

## How a repo uses the kit

Add `examples/build-apps.yml` as `.github/workflows/build-apps.yml` in your app
repo and set the three values under `with:` to match your layout:

```yaml
jobs:
  app:
    uses: drsamonline/app-builder/.github/workflows/build.yml@main
    with:
      app_name: my-app        # -> my-app-portable.exe and my-app.apk
      app_src: docs/play      # folder containing your index.html (+ any assets)
      deploy_path: docs       # folder to publish to Pages ("" = do not deploy)
```

**Call the workflow; do not copy it.** The build, release and deploy live in the
reusable workflow, so a fix there reaches every app at once. An earlier
hand-copied version of this file drifted and kept `if: always()` on the release
job, which *deleted* the published release before recreating it.

The reusable workflow runs, on every push to `main` (and on manual
`workflow_dispatch`):

1. **`exe` job** (`windows-latest`) checks out your repo **and** this kit, copies
   `app_src/` into `exe/app/`, runs `python exe/build.py`, and uploads
   `<app_name>-portable.exe`.
2. **`apk` job** (`ubuntu-latest`) checks out both, installs the Android SDK
   packages, copies `app_src/` into `apk/app/src/main/assets/www/`, and runs
   `gradle assembleRelease` to produce a signed `<app_name>.apk`.
3. **`version` job** consumes any `changes/` files and bumps `VERSION` and
   `CHANGELOG.md`.
4. **`release` job** publishes both artefacts on a single fixed-tag release
   (`app-latest`) — created **only if it is missing**, then uploaded with
   `--clobber`. It never deletes the release first, so a failed build leaves the
   previous one intact.
5. **`pages` job** deploys `deploy_path` after the release lands.

A push that touches only root docs/meta (`*.md`, `LICENSE`, `.gitignore`, …) is
skipped entirely by `paths-ignore`, so a docs-only commit does not run the
builder.

### Stable download URLs

Because the tag is always `app-latest` and is recreated each run, these URLs are
permanent:

```
https://github.com/<owner>/<repo>/releases/latest/download/<APP_NAME>-portable.exe
https://github.com/<owner>/<repo>/releases/latest/download/<APP_NAME>.apk
```

Link your landing page to those and the download always tracks the latest build.

---

## The EXE launcher

`launcher.py`:

* picks a free port on `127.0.0.1`,
* serves the bundled `app/` folder with `http.server`,
* opens the user's default browser at the URL, prints it, and
* runs until the console window is closed / `Ctrl+C`.

It resolves its bundled data via `sys._MEIPASS` when frozen by PyInstaller, and
falls back to the script directory when run as a plain script.

`build.py` builds the EXE with `--onefile`, names it `<APP_NAME>-portable`, and
bundles the app folder as `app`. It uses the correct `--add-data` separator for
the platform (`;` on Windows, `:` elsewhere). Set `APP_NAME` in the environment
before running it.

Every build **inspects the EXE before it ships it.** `tools/verify_exe.py` reads
the PE and asserts it is a valid PE, an executable, within a size budget, and
imports nothing unexpected — then prints the machine, subsystem, size and imports
to the build log, so the record shows what actually shipped. `MAX_EXE_MB`,
`REQUIRED_IMPORTS` and `FORBIDDEN_IMPORTS` (and `SIGNED_REQUIRED=1`) tune the
assertions per app.

---

## The Android APK

The `apk/` project is deliberately minimal and dependency-free (platform
framework only — **no AndroidX**):

* `compileSdk 34`, `minSdk 24`, `targetSdk 34`, AGP 8.x.
* `MainActivity` is a full-screen `WebView` with JavaScript and DOM storage
  enabled, loading `file:///android_asset/www/index.html`.
* The hardware back button navigates the WebView history first.
* `INTERNET` permission is declared (some wrapped apps fetch remote assets).

The app's HTML lives in `app/src/main/assets/www/` — the workflow copies your
`docs/play/` folder there before building. The app label comes from
`res/values/strings.xml`; the workflow replaces the `APP_NAME_PLACEHOLDER`
token with `APP_NAME`.

---

## Signing key (read this)

`keystore/debug.keystore` is a **debug-grade** key (alias `androiddebugkey`,
store/key password `android`, CN=Android Debug, validity ~10000 days).

* Its only purpose is so that **successive builds can be installed over each
  other** during sideloading/iteration.
* It is **NOT** a Play-Store signing key. Do **not** publish to Google Play
  with it. It is public in this repository, so it provides no security.
* To use your own key, add repository **secrets** and pass them through in the
  `apk` job's environment:

  | secret | meaning |
  | --- | --- |
  | `KEYSTORE_FILE` | path to the keystore file you stage in the job |
  | `KEYSTORE_PASSWORD` | store password |
  | `KEY_ALIAS` | key alias |
  | `KEY_PASSWORD` | key password |

  `app/build.gradle.kts` reads those env vars and falls back to the committed
  debug key when they are unset.

---

## Caveats

* The APK is **debug-signed** (see above) — fine for sideloading, not for Play.
* The EXE is unsigned, so Windows SmartScreen may warn on first run
  ("More info" → "Run anyway"). Code-signing is out of scope for this kit.
* Each run costs ~2 GitHub-hosted runner-minutes (Windows + Linux). A cold
  Android build is the slower half (SDK + Gradle download).
