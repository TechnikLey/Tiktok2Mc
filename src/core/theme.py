import re

_DEFAULT_THEMES = {
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
        Canonical theme key (e.g. ``"spotify"``) used
        to look up built-in fallback colors.
    """
    defaults = _DEFAULT_THEMES.get(plugin_key, {})
    user_theme = plugin_cfg.get("theme", {})
    return {**defaults, **user_theme}


_INVALID_CSS_KEY_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
_INVALID_CSS_VALUE_CHARS = re.compile(r"[\\;{}<>\r\n\x00-\x1f]+")


def sanitize_css_key(key: str) -> str:
    """Keep only characters that are safe inside a CSS custom-property name."""
    cleaned = _INVALID_CSS_KEY_CHARS.sub("-", str(key))
    return cleaned or "key"


def sanitize_css_value(value: str) -> str:
    """Strip characters that could break out of a CSS declaration block."""
    cleaned = _INVALID_CSS_VALUE_CHARS.sub("", str(value)).strip()
    return cleaned or "inherit"


def theme_css(colors: dict) -> str:
    lines = ["    :root {"]
    for key, value in colors.items():
        name = sanitize_css_key(key).replace("_", "-")
        lines.append(f"        --{name}: {sanitize_css_value(value)};")
    lines.append("    }")
    return "\n".join(lines)
