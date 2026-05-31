_DEFAULT_THEMES = {
    "like_goal": {
        "background": "#050505",
        "text": "#ffffff",
        "accent": "#00f5ff",
        "accent2": "#8a2be2",
        "danger": "#ff4d4d",
    },
    "death_counter": {
        "background": "#000000",
        "text": "#8ef3ff",
    },
    "win_counter": {
        "background": "#000000",
        "text": "#ffffff",
        "danger": "#ff4d4d",
        "muted": "#666666",
        "separator": "#333333",
    },
    "timer": {
        "background": "#000000",
        "text": "#89CFF0",
        "warning": "#FFD700",
        "blink": "#FF8C00",
        "danger": "#FF0000",
    },
    "overlay_text": {
        "background": "#00FF00",
        "text": "#ffffff",
    },
    "spotify": {
        "background": "#000000",
        "text": "#ffffff",
        "accent": "#1db954",
        "accent2": "#1ed760",
    },
}


def load_plugin_theme(plugin_cfg: dict, plugin_key: str) -> dict:
    """Return merged theme colors for a plugin.

    *plugin_cfg* is the **plugin-local** configuration dict (the one loaded
    from ``plugins/<name>/config.yaml``).  The plugin's own ``theme:``
    section is read directly; no global config is consulted.

    Parameters
    ----------
    plugin_cfg:
        The dict returned by ``load_plugin_config(plugin_dir)``.
    plugin_key:
        Canonical theme key (e.g. ``"spotify"``, ``"like_goal"``) used
        to look up built-in fallback colors.
    """
    defaults = _DEFAULT_THEMES.get(plugin_key, {})
    user_theme = plugin_cfg.get("theme", {})
    return {**defaults, **user_theme}


def theme_css(colors: dict) -> str:
    lines = ["    :root {"]
    for key, value in colors.items():
        lines.append(f"        --{key.replace('_', '-')}: {value};")
    lines.append("    }")
    return "\n".join(lines)
