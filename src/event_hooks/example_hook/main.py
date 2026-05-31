from core.hook_api import HookAPI
import logging
log = logging.getLogger(__name__)

def register(api: HookAPI):
    def superjump(user, trigger, context):
        api.rcon_enqueue([
            f"effect give @a minecraft:jump_boost 10 5 true",
            f"say {user} triggered a super jump!",
        ])
        api.log(f"superjump triggered by {user}")
        api.send_overlay_text(title="Super Jump!", subtitle=f"Triggered by {user}", duration=5)

    api.register_action("superjump", superjump)
