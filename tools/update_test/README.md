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

* A compiled updater: `python build.py app --only update`.
* The control-plane port `29185` must be free — the harness binds it to
  simulate the app's kill-signal endpoint and refuses to start if a real
  Tiktok2Mc instance is running.

## Usage

```bash
python tools/update_test/run_update_test.py --list            # scenarios
python tools/update_test/run_update_test.py success           # one scenario
python tools/update_test/run_update_test.py all               # all scenarios
python tools/update_test/run_update_test.py all --clean
```

Build the updater separately first (`python build.py app --only update`);
the harness no longer builds it itself, because running a freshly built
unsigned `update.exe` immediately (as `--build` did) reliably triggered
the Windows Defender heuristic false positive (see below).

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

## Exit codes

`src/python/update.py` exits with one of these codes; `src/python/start.py`
records them via `set_last_update_result()` so the dashboard can show the
failure reason (`GET /api/v1/updates/result`).

| Code | Meaning |
|------|---------|
| `0`  | Update installed successfully |
| `1`  | Unexpected error (crash / bad startup config) |
| `5`  | No update needed (also beta declined / auto-skip) — benign |
| `10` | API / network error while checking for updates |
| `11` | No release asset for this platform |
| `12` | Checksum file is missing |
| `13` | Checksum verification failed |
| `14` | Download failed |
| `15` | Install failed (locked / read-only file) |

The harness scenarios assert these codes (see `run_update_test.py`).

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
