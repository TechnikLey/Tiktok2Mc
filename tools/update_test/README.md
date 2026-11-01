# Updater end-to-end test harness (`tools/update_test/`)

Runs the **compiled** updater (`update.exe` / `update.bin`) against a
GitHub-compatible local mock server, so the real production code path of
`src/python/update.py` is exercised end to end. The flow is the P3a
Omaha-style state machine:

```
CHECK → FETCH → VERIFY_SIG → VERIFY_SHA → STAGE → FLIP → PRUNE → NOTIFY
```

- **CHECK** version resolution (`current.json` pointer → `version.txt`)
- **FETCH** platform archive + `manifest.json` + `manifest.json.sig` assets
- **VERIFY_SIG** detached Ed25519 signature against the embedded key
  (test-only override: `T2M_SIGNING_PUBLIC_KEY`)
- **VERIFY_SHA** archive `.sha256`, then per-file sha256 vs. the manifest
- **STAGE** verified `app-<ver>/` moved into the install root
- **FLIP** atomic `current.json` pointer update (records `previous_app_dir`)
- **PRUNE** old `app-<ver>/` dirs (newest rollback generation kept)
- **NOTIFY** progress file + `--auto` relaunch

The updater **never touches running processes** and does **not** copy
whitelisted files or migrate the user config anymore — the launcher does
that at the next boot (`resolve_app_base`,
`swap_pending_launcher_binaries`, first-start config hook; covered by the
`launch_maintenance` / `config_migration_parity` scenarios).

* `mock_github.py` — local server that mimics the GitHub Releases API
  (release JSON + archive + `.sha256` + `manifest.json`/`.sig` asset
  serving). Stdlib only.
* `run_update_test.py` — the harness: builds a realistic old installation,
  assembles a P3a release (app dir, pointer, signed manifest — mirroring
  `build.py`'s assembly), serves it and runs the compiled updater against
  it. The only simulated part is the HTTP source; everything else is the
  real binary.

## Requirements

* A compiled updater: `python build.py app --only update`.
* The control-plane port `29185` must be free — the harness binds it to
  reserve the port (and keep the legacy kill-signal endpoint alive for
  pre-P3a updater binaries) and refuses to start if a real Tiktok2Mc
  instance is running.

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

## Test-only env overrides (compiled binary hooks)

Both hooks live in `src/python/update.py::_init()`; production never sets
these variables:

* `TIKTOK2MC_UPDATE_SOURCE` — point the updater at the local mock instead
  of the hardcoded GitHub URL:

  ```python
  API_URL = os.environ.get("TIKTOK2MC_UPDATE_SOURCE") or API_URL
  ```

* `T2M_SIGNING_PUBLIC_KEY` — make the updater trust the harness's per-run
  Ed25519 key (raw 64-byte hex). The harness signs the release manifest
  with its own generated key (`Harness.release_key`); scenarios that test
  signature failures sign with `Harness.bad_key` instead.
* `T2M_DATA_HOME` — isolate the *user data home* (``core.paths``): scenarios
  that exercise launcher-side maintenance (``config_migration_parity``) set
  it to the scratch install, so the first-start config hook reads/writes the
  scratch config and runtime marker instead of the developer's real
  ``config/`` and ``core/runtime/``.

See `tests/test_core/test_update_e2e.py::TestUpdateSourceOverride`.

## Exit codes

`src/python/update.py` exits with one of these codes; `src/python/start.py`
records them via `set_last_update_result()` so the dashboard can show the
failure reason (`GET /api/v1/updates/result`).

| Code | Meaning |
|------|---------|
| `0`  | Update staged + pointer flipped successfully |
| `1`  | Unexpected error (crash / bad startup config) |
| `5`  | No update needed (also beta declined / auto-skip) — benign |
| `10` | API / network error while checking for updates |
| `11` | No release asset (or no `manifest.json` asset) for this platform |
| `12` | Archive `.sha256` companion asset missing |
| `13` | Checksum verification failed (archive or per-file manifest) |
| `14` | Download failed |
| `15` | Install failed (files locked / read-only) |
| `16` | Manifest signature verification failed — update rejected |

The harness scenarios assert these codes (see `run_update_test.py`).

## Scenarios

| Scenario | What it pins |
|----------|--------------|
| `success` | legacy flat install → assembled release: app dir staged, pointer flipped, launcher binaries queued, config untouched |
| `versioned_update` | stale target dir wiped/re-staged, previous generation kept as rollback, ancient dirs pruned |
| `up_to_date` | exit `5`, install untouched |
| `missing_asset` | no platform archive → `11` |
| `missing_manifest` | no `manifest.json` asset → `11` |
| `missing_sig` | no `.sig` asset → `16` |
| `sig_fail` | manifest signed by an unknown key → `16`, nothing installed |
| `bad_checksum` | archive `.sha256` mismatch → `13` |
| `tampered_file` | packaged file differs from the signed manifest → `13` |
| `invalid_version` | malformed release tag → benign `5` |
| `api_error` | HTTP 500 → retried, then `10` |
| `download_error` | archive 404 → `14` |
| `abort_download` | kill mid-download → nothing installed |
| `self_update` | updated `update` binary queued as `update_new` for the next boot |
| `locked_file` | locked stale target dir → `15`, pointer intact (Windows) |
| `retry_after_failure` | failed run then clean success |
| `beta_prompt` | beta decline/accept |
| `launch_maintenance` | launcher boots: `resolve_app_base` + `swap_pending_launcher_binaries` choreography, stable afterwards |
| `config_migration_parity` | updater leaves config alone; launcher first-start hook migrates with user values preserved |

## Known Windows Defender false positive

Windows Defender may flag a freshly built, unsigned `update.exe` as
`Behavior:Win32/DefenseEvasion.A!ml`. This is **not** caused by the
`TIKTOK2MC_UPDATE_SOURCE` / `T2M_SIGNING_PUBLIC_KEY` test hooks — the
heuristic simply reacts to a new, unsigned executable that spawns and
replaces files. It is a false positive: build artifacts from `build.py`
are always reproducible from this repository's sources, and CI releases
are built in a clean environment. Do not work around this in code; run
the uplifted binary from inside the scratch dir and keep Defender on.
