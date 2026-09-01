"""Event-subscription wildcard matching (shared).

Single source of truth for the pattern language used by plugin
``event_subscriptions``, hook ``register_event`` subscriptions and the
outbound-channel ``events`` list.  Lives here (dependency-free) so that
every consuming process (API, bridge, plugins, hooks) reuses one
implementation instead of duplicating it.

Supported patterns:

* ``"*"``               — catch-all
* ``"tiktok.gift"``     — exact name
* ``"tiktok.*"``        — trailing prefix wildcard
"""


def match_event(event_type: str, pattern: str) -> bool:
    """Return whether *event_type* matches a subscription *pattern*."""
    if pattern == "*":
        return True
    if pattern == event_type:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type.startswith(prefix + ".")
    return False
