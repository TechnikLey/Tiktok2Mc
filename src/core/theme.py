import re

# Core-owned theme defaults only. Plugins define their own default colors
# in the ``theme:`` section of their plugin-local config.yaml — the core
# must not know individual plugins.
_DEFAULT_THEMES = {
    "overlay_text": {
        "background": "#00FF00",
        "text": "#ffffff",
    },
}


def load_plugin_theme(plugin_cfg: dict, theme_key: str) -> dict:
    """Return merged theme colors for an overlay consumer.

    *plugin_cfg* is the **plugin-local** configuration dict (the one loaded
    from ``plugins/<name>/config.yaml``).  The ``theme:`` section is read
    directly; no global config is consulted.  ``theme_key`` selects a
    built-in default for core-owned consumers (e.g. ``"overlay_text"``);
    unknown keys simply start from an empty default and rely entirely on
    the local ``theme:`` section.
    """
    defaults = _DEFAULT_THEMES.get(theme_key, {})
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
