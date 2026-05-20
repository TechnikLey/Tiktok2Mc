#!/usr/bin/env python3
# ==================================================
# example_hook.py - Example event hook
# ==================================================
# This file demonstrates how to create a custom
# $-command handler for the Streaming Tool.
#
# USAGE:
#   1. Add a line in data/actions.mca:
#          follow: $superjump
#   2. Start the build.py Script
#   3. Start/Restart the bot — the hook is loaded automatically.
#
# The handler receives:
#   user    — TikTok username who triggered the event
#   trigger — the action name from actions.mca (e.g. "superjump")
#   context — reserved dict for future use (currently empty)
# ==================================================

# Import for type hints and IntelliSense in your editor.
# This import is only used for development (autocomplete, docstrings) and has no effect at runtime.
from core.hook_api import HookAPI

def register(api: HookAPI):
    def superjump(user, trigger, context):
        api.rcon_enqueue([
            f"effect give @a minecraft:jump_boost 10 5 true",
            f"say {user} triggered a super jump!",
        ])
        api.log(f"superjump triggered by {user}")
        api.send_overlay_text(title="Super Jump!", subtitle=f"Triggered by {user}", duration=5)

    api.register_action("superjump", superjump)