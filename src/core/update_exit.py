"""Updater exit codes — single source of truth.

Both the updater binary (``src/python/update.py``) and the supervisor
(``src/python/start.py``) need the numeric exit codes and their
human-readable messages.  They run as separate processes, so the codes are
shared here in ``core`` (which both import) rather than duplicated.

Numeric values are stable API and are asserted by the updater E2E harness
(``tools/update_test/run_update_test.py``) against the compiled binary —
never renumber them.
"""

from __future__ import annotations

from typing import Final

EXIT_OK: Final[int] = 0
EXIT_UNEXPECTED: Final[int] = 1
EXIT_NO_UPDATE: Final[int] = 5
EXIT_API_ERROR: Final[int] = 10
EXIT_NO_ASSET: Final[int] = 11
EXIT_MISSING_CHECKSUM: Final[int] = 12
EXIT_CHECKSUM_MISMATCH: Final[int] = 13
EXIT_DOWNLOAD_FAILED: Final[int] = 14
EXIT_INSTALL_FAILED: Final[int] = 15

EXIT_MESSAGES: Final[dict[int, str]] = {
    EXIT_OK: "Update installed successfully.",
    EXIT_UNEXPECTED: "Unexpected error while updating.",
    EXIT_NO_UPDATE: "No update needed.",
    EXIT_API_ERROR: "Could not reach the update server.",
    EXIT_NO_ASSET: "No update file found for this platform.",
    EXIT_MISSING_CHECKSUM: "Checksum file is missing.",
    EXIT_CHECKSUM_MISMATCH: "Checksum verification failed — file may be corrupted.",
    EXIT_DOWNLOAD_FAILED: "Download failed.",
    EXIT_INSTALL_FAILED: "Could not install the update (files locked or read-only?).",
}
