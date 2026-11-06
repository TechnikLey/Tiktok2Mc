"""Reference hook showing action registration, RCON and overlay usage."""

import logging

from core.hook_api import HookAPI

log = logging.getLogger(__name__)


def register(api: HookAPI):
    """Register the example ``$superjump`` action.

    The action grants jump boost to every online player, announces the
    triggering viewer in chat and shows an overlay message.
    """

    def superjump(user, trigger, context):
        """Run the example action for one trigger invocation."""
        api.rcon_enqueue(
            [
                "effect give @a minecraft:jump_boost 10 5 true",
                f"say {user} triggered a super jump!",
            ]
        )
        api.log(f"superjump triggered by {user}")
        api.send_overlay_text(
            title="Super Jump!", subtitle=f"Triggered by {user}", duration=5
        )

    api.register_action("superjump", superjump)
