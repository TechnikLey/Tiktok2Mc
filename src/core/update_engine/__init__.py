"""Versioned-directory update engine (P3a).

Provides the building blocks for the Omaha-style update architecture:

- :mod:`core.update_engine.pointer` — ``current.json`` pointer management
  (reads/writes/rollback/prune, versioned ``app-<ver>/`` directory scanning).
- :mod:`core.update_engine.manifest` — signed release manifests
  (``manifest.json`` + Ed25519 detached signature + per-file sha256).

Design rule: every function operates on **explicitly passed paths** so the
logic stays testable without depending on ``core.paths`` (which depends on
this package at runtime; avoid a cycle).
"""

from __future__ import annotations

__all__ = ["manifest", "pointer"]
