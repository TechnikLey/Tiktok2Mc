#!/usr/bin/env python3
"""Central startup configuration gate.

Single entry point the supervisor uses ONCE at startup to load and validate
``config.yaml``. It replaces the previous pattern of several independent
loaders (``core.utils.load_config`` at import time in ``start.py`` plus
``validate_config_exists`` inside ``run_startup_validation``) with one result
object that carries the parsed config, every issue found, and a fatal flag.

The gate itself never exits the process: it reports issues via the
``CrashManager`` (structured codes), logs them, and lets the caller decide
what to do with :attr:`ConfigGateResult.fatal`.

Error codes used (see ``core.error_codes``):
- ``CONFIG-0001`` — file missing/unreadable (fatal).
- ``CONFIG-0002`` — YAML syntax error (fatal), with line/column when the
  YAML parser provides a problem mark.
- ``CONFIG-0004`` — schema/type validation problem or a top-level
  non-mapping document. Schema mismatches are non-fatal warnings; a
  non-mapping document is escalated to fatal because downstream ``cfg.get``
  calls would crash otherwise.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml.error import MarkedYAMLError, YAMLError

from core.error_codes import CONFIG_0001, CONFIG_0002, CONFIG_0004, Severity
from core.validation_framework import validate_config_schema
from core.yaml_utils import create_yaml_rt

log = logging.getLogger(__name__)


@dataclass
class ConfigIssue:
    """One configuration problem found by the gate.

    Attributes:
        error_code: Stable code string, e.g. ``"CONFIG-0002"``.
        message: Human-readable description of the problem.
        path: File system path of the offending config file, if known.
        line: 1-based line number, when the YAML parser provides a mark.
        column: 1-based column number, when the YAML parser provides a mark.
        fatal: Whether this issue alone prevents startup.
    """

    error_code: str
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    fatal: bool = False

    def format(self) -> str:
        """Render the issue as one user-friendly summary line.

        Returns:
            ``"[code] message (path:line:column)"`` with the location part
            omitted when unknown.
        """
        loc = self.path or ""
        if self.line is not None:
            loc = f"{loc}:{self.line}"
            if self.column is not None:
                loc = f"{loc}:{self.column}"
        return f"[{self.error_code}] {self.message}" + (f" ({loc})" if loc else "")


@dataclass
class ConfigGateResult:
    """Outcome of a single run of the startup configuration gate.

    Attributes:
        config: Parsed configuration document (a mapping), or ``None`` when
            the file could not be loaded at all.
        ok: ``True`` when no issue of any kind was found.
        fatal: ``True`` when at least one issue prevents startup; the caller
            must not continue booting in that case (``config`` is ``None``).
        issues: Every issue found, fatal and non-fatal, in check order.
    """

    config: dict[str, Any] | None
    ok: bool
    fatal: bool
    issues: list[ConfigIssue] = field(default_factory=list)


_SEVERITY_LOG_LEVELS: dict[Severity, int] = {
    Severity.DEBUG: logging.DEBUG,
    Severity.INFO: logging.INFO,
    Severity.NOTICE: logging.INFO,
    Severity.WARNING: logging.WARNING,
    Severity.ERROR: logging.ERROR,
    Severity.CRITICAL: logging.CRITICAL,
    Severity.FATAL: logging.CRITICAL,
}


def _report(
    issues: list[ConfigIssue],
    *,
    error_code: Any,
    message: str,
    path: str | None,
    line: int | None = None,
    column: int | None = None,
    fatal: bool = False,
    crash_manager: Any | None = None,
    detail: str = "",
) -> ConfigIssue:
    """Create one :class:`ConfigIssue`, log it and report it to the crash manager.

    Args:
        issues: Issue list to append the created issue to.
        error_code: The ``ErrorCode`` definition from ``core.error_codes``.
        message: Occurrence-specific problem description shown to the user.
        path: Config file path, if known.
        line: Optional 1-based line number.
        column: Optional 1-based column number.
        fatal: Whether the issue prevents startup (decides the log level and
            the issue's ``fatal`` flag; the code's nominal severity is kept
            for the crash report).
        crash_manager: Optional ``CrashManager`` — the issue is reported via
            ``report_error`` when one is provided.
        detail: Extra occurrence-specific detail for the crash report.

    Returns:
        The created and appended issue.
    """
    issue = ConfigIssue(
        error_code=error_code.code,
        message=message,
        path=path,
        line=line,
        column=column,
        fatal=fatal,
    )
    issues.append(issue)
    log.log(
        logging.CRITICAL
        if fatal
        else _SEVERITY_LOG_LEVELS.get(error_code.severity, logging.ERROR),
        "[CONFIG-GATE] %s",
        issue.format(),
    )
    if crash_manager is not None:
        crash_manager.report_error(
            error_code,
            detail=f"{detail}\n{issue.format()}" if detail else issue.format(),
            context_info={
                "path": path,
                "line": line,
                "column": column,
                "fatal": fatal,
            },
        )
    return issue


def load_and_validate_config(
    path: str | Path,
    crash_manager: Any | None = None,
) -> ConfigGateResult:
    """Load and validate the main configuration file through the gate.

    Checks performed, in order:
    1. Existence/readability → ``CONFIG-0001`` (fatal).
    2. YAML syntax via ruamel round-trip parser → ``CONFIG-0002`` (fatal)
       with 1-based line/column from the parser's problem mark when present.
    3. Top-level document must be a mapping → ``CONFIG-0004`` (escalated to
       fatal, downstream code calls ``cfg.get``).
    4. Schema/type validation via ``validate_config_schema`` → ``CONFIG-0004``
       (non-fatal; first violation is reported).

    The gate logs and (optionally) reports every issue but never exits —
    the caller inspects :attr:`ConfigGateResult.fatal` and decides.

    Args:
        path: Path to the ``config.yaml`` file.
        crash_manager: Optional ``CrashManager``; when given, each issue is
            reported through ``report_error`` with its structured code.

    Returns:
        A :class:`ConfigGateResult`; ``config`` is ``None`` exactly when
        ``fatal`` is ``True``.
    """
    issues: list[ConfigIssue] = []
    path = Path(path)
    config: dict[str, Any] | None = None

    def _issue(
        error_code: Any,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        fatal: bool = False,
        detail: str = "",
    ) -> ConfigIssue:
        """Append, log and report one issue against the gate's config path."""
        return _report(
            issues,
            error_code=error_code,
            message=message,
            path=str(path),
            line=line,
            column=column,
            fatal=fatal,
            crash_manager=crash_manager,
            detail=detail,
        )

    # 1) Existence / readability → CONFIG-0001 (fatal)
    if not path.exists():
        _issue(
            CONFIG_0001,
            CONFIG_0001.message,
            fatal=True,
            detail=CONFIG_0001.recovery_hint,
        )
        return ConfigGateResult(config=None, ok=False, fatal=True, issues=issues)
    if not os.access(str(path), os.R_OK):
        _issue(
            CONFIG_0001,
            f"Configuration file is not readable: {path}",
            fatal=True,
            detail=CONFIG_0001.recovery_hint,
        )
        return ConfigGateResult(config=None, ok=False, fatal=True, issues=issues)

    # 2) YAML syntax → CONFIG-0002 (fatal, with mark when available)
    yaml = create_yaml_rt()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.load(f)
    except MarkedYAMLError as exc:
        line = column = None
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        if mark is not None:
            line, column = mark.line + 1, mark.column + 1  # marks are 0-based
        _issue(
            CONFIG_0002,
            f"Configuration file has invalid YAML syntax: {exc.problem}",
            line=line,
            column=column,
            fatal=True,
            detail=CONFIG_0002.recovery_hint,
        )
        return ConfigGateResult(config=None, ok=False, fatal=True, issues=issues)
    except (OSError, YAMLError) as exc:
        _issue(
            CONFIG_0002,
            f"Configuration file could not be loaded: {exc}",
            fatal=True,
            detail=CONFIG_0002.recovery_hint,
        )
        return ConfigGateResult(config=None, ok=False, fatal=True, issues=issues)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        # Downstream start.py code calls cfg.get(...) — a non-mapping
        # document cannot be used, despite the code's nominal severity.
        _issue(
            CONFIG_0004,
            f"Configuration must be a mapping, got {type(data).__name__}",
            fatal=True,
        )
        return ConfigGateResult(config=None, ok=False, fatal=True, issues=issues)

    # 3) Schema/type validation → CONFIG-0004 (non-fatal warning)
    try:
        validate_config_schema(data)
    except (TypeError, ValueError) as exc:
        _issue(
            CONFIG_0004,
            f"Configuration validation problem: {exc}",
        )

    config = data
    return ConfigGateResult(config=config, ok=not issues, fatal=False, issues=issues)
