#!/usr/bin/env python3
# ==================================================
# random.py - $random action hook
# ==================================================
# Picks a random eligible trigger and executes it.
# Configurable via config.yaml > random_triggers.
#
# USAGE in actions.mca:
#   gift_id:$random
# ==================================================

import random
import logging
from core.hook_api import HookAPI

log = logging.getLogger(__name__)


def register(api: HookAPI):
    def random_handler(user, trigger, context):
        all_valid = sorted(api.get_valid_functions())

        if not all_valid:
            log.info("[RANDOM-HOOK] No valid functions available for $random.")
            return

        random_cfg = api.config.get("random_triggers", {})
        mode = str(random_cfg.get("mode", "deny-all")).lower()
        raw_list = random_cfg.get("triggers", [])
        configured = [str(t).strip().lower() for t in raw_list if str(t).strip()] if isinstance(raw_list, list) else []

        candidates = []
        for func in all_valid:
            if mode == "deny-all":
                if func not in configured:
                    candidates.append(func)
            else:
                if func in configured:
                    candidates.append(func)

        if not candidates:
            log.info("[RANDOM-HOOK] No eligible actions in $random pool.")
            return

        chosen = random.choice(candidates)
        username = str(user)
        if isinstance(user, dict):
            username = user.get("user", str(user))

        api.enqueue_trigger(chosen, username)

    api.register_action("random", random_handler)
    log.info("[RANDOM-HOOK] $random action registered")
