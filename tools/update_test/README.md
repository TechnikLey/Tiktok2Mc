# Updater end-to-end test harness (`tools/update_test/`)

Runs the **compiled** updater (`update.exe` / `update.bin`) against a
GitHub-compatible local mock server, so the real production code path of
`src/python/update.py` is exercised end to end: version check, asset
selection, download, checksum verification, extraction, updater
self-update, whitelisted file copy, config migration and exit codes.

* `mock_github.py` — local server that mimics the GitHub Releases API
  (release JSON + asset download + `.sha256` companion asset). Stdlib only.
* `run_update_test.py` — the harness: builds a realistic old installation,
  serves a fake release and runs the compiled updater against it. The only
  simulated part is the HTTP source; everything else is the real binary.

## Requirements

* A compiled updater: `python build.py app --only update` (or `--build`).
* The control-plane port `29185` must be free — the harness binds it to
  simulate the app's kill-signal endpoint and refuses to start if a real
  Tiktok2Mc instance is running.

## Usage

```bash
python tools/update_test/run_update_test.py --list            # scenarios
python tools/update_test/run_update_test.py success           # one scenario
python tools/update_test/run_update_test.py all               # all scenarios
python tools/update_test/run_update_test.py all --build --clean
```

`--clean` removes the scratch directory afterwards; without it the scratch
dir is kept (with `logs/<scenario>.log`) so you can inspect the updater's
output. The test installation, release archive and both mock servers live
exclusively in the scratch dir — nothing in `src/`, `config/` or `data/`
is touched.

## Update source override

The compiled updater reads `TIKTOK2MC_UPDATE_SOURCE` (set by the harness)
to point at the local mock instead of the hardcoded GitHub URL. The hook
lives in `src/python/update.py::_init()`:

```python
API_URL = os.environ.get("TIKTOK2MC_UPDATE_SOURCE") or API_URL
```

Production never sets this variable, so the default GitHub URL is used
unchanged. See `tests/test_core/test_update_e2e.py::TestUpdateSourceOverride`.

## Known Windows Defender false positive

Windows Defender may flag a freshly built, unsigned `update.exe` as
`Behavior:Win32/DefenseEvasion.A!ml`. This is **not** caused by the
`TIKTOK2MC_UPDATE_SOURCE` test hook.

Investigation summary (Aug 2026, `Behavior:Win32/DefenseEvasion.A!ml`):

* PyInstaller builds are **non-deterministic**: three builds of the
  identical source produced three different binaries (different sizes and
  SHA-256 hashes). Each build therefore gets a fresh ML verdict.
* The apparent A/B "trigger" did not reproduce: three fresh builds *with*
  the hook were all clean and ran fine, while the original flagged build
  was the first binary Windows Defender ever saw from this pipeline.
* `!ml` verdicts on unsigned PyInstaller onefile executables are a known
  heuristic false-positive category; the first build is sometimes flagged,
  subsequent builds of the same source are not.

This is an environment/reputation issue, so the fix belongs in the
environment, not in code: code-sign the updater or add a Defender
exclusion for `build/` (and the scratch directory). Do not modify the
hook or the harness to work around it — any rebuild produces a new binary
and a new ML verdict.
