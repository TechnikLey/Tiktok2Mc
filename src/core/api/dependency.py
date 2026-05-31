"""Plugin dependency resolution and ordering.

Provides topological sort for plugin startup ordering and validation
that declared dependencies are satisfied at registration time.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class DependencyError(Exception):
    """Raised when plugin dependency resolution fails."""


def topological_sort(
    plugins: list[dict[str, Any]],
    name_key: str = "name",
    depends_on_key: str = "depends_on",
) -> list[dict[str, Any]]:
    """Topologically sort plugins by their ``depends_on`` declarations.

    Uses Kahn's algorithm.  Missing dependency targets are logged as
    warnings and ignored (the dependent plugin is placed as early as
    possible in the sorted output).

    Raises
    ------
    DependencyError
        When a circular dependency is detected.

    Returns
    -------
    list[dict[str, Any]]
        Plugins sorted so that dependencies appear before dependents.
    """
    by_name: dict[str, dict[str, Any]] = {p[name_key]: p for p in plugins}
    in_degree: dict[str, int] = {}
    adj: dict[str, list[str]] = {}

    for p in plugins:
        name = p[name_key]
        in_degree.setdefault(name, 0)
        adj.setdefault(name, [])

    for p in plugins:
        name = p[name_key]
        deps = p.get(depends_on_key) or []
        for dep_name in deps:
            if dep_name not in by_name:
                log.warning(
                    "Plugin '%s' depends on '%s' which is not registered — ignoring",
                    name, dep_name,
                )
                continue
            adj.setdefault(dep_name, []).append(name)
            in_degree[name] = in_degree.get(name, 0) + 1

    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_plugins: list[dict[str, Any]] = []

    while queue:
        name = queue.pop(0)
        sorted_plugins.append(by_name[name])
        for neighbor in adj.get(name, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_plugins) != len(plugins):
        sorted_names = {s[name_key] for s in sorted_plugins}
        cycled = [p[name_key] for p in plugins if p[name_key] not in sorted_names]
        raise DependencyError(
            f"Circular dependency detected involving: {', '.join(cycled)}"
        )

    return sorted_plugins


def validate_dependencies(
    plugin_name: str,
    depends_on: list[str],
    registered: dict[str, Any],
) -> list[str]:
    """Check that all dependencies for *plugin_name* are registered.

    Returns
    -------
    list[str]
        Missing dependency names (empty list if all satisfied).
    """
    return [dep for dep in depends_on if dep not in registered]


def get_dependency_order(
    plugins: list[dict[str, Any]],
    name_key: str = "name",
    depends_on_key: str = "depends_on",
) -> list[dict[str, Any]]:
    """Sort plugins by dependency order.

    Falls back to alphabetical order if a circular dependency is
    detected (logged as a warning).
    """
    try:
        return topological_sort(plugins, name_key, depends_on_key)
    except DependencyError as e:
        log.warning("Dependency sort failed: %s — falling back to alphabetical", e)
        return sorted(plugins, key=lambda p: p.get(name_key, ""))
