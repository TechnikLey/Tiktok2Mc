"""Built-in $random script action.

This used to be shipped as the ``random`` hook. It is now a fixed part of
the program so it is always available and updated with the tool itself.
"""

import logging
import random

log = logging.getLogger(__name__)


def register_random_action(api, config: dict | None = None) -> None:
    """Register the built-in ``$random`` action handler.

    ``config`` is the full application config (or a dict containing a
    ``builtins.random`` section). Falls back to sensible defaults.
    """
    cfg = {}
    if isinstance(config, dict):
        builtins = config.get("builtins", {})
        if isinstance(builtins, dict):
            cfg = builtins.get("random", {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}

    mode = str(cfg.get("mode", "deny-all")).lower()
    raw_list = cfg.get("triggers", [])
    configured = (
        [str(t).strip().lower() for t in raw_list if str(t).strip()]
        if isinstance(raw_list, list)
        else []
    )

    def random_handler(user, trigger, context):
        all_valid = sorted(api.get_valid_functions())

        if not all_valid:
            log.info("[RANDOM] No valid functions available for $random.")
            return

        candidates = []
        for func in all_valid:
            if mode == "deny-all":
                if func not in configured:
                    candidates.append(func)
            else:
                if func in configured:
                    candidates.append(func)

        if not candidates:
            log.info("[RANDOM] No eligible actions in $random pool.")
            return

        chosen = random.choice(candidates)
        username = str(user) or "Unknown"
        api.enqueue_trigger(chosen, username)

    try:
        api.register_action("random", random_handler)
        log.info("[RANDOM] $random action registered (built-in)")
    except Exception as exc:  # never crash bridge startup
        log.error("[RANDOM] Failed to register $random: %s", exc)
