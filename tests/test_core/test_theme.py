import pytest

from core.theme import load_plugin_theme, theme_css, _DEFAULT_THEMES


class TestLoadPluginTheme:
    def test_returns_defaults_when_no_user_theme(self):
        cfg = {}  # no theme section
        result = load_plugin_theme(cfg, "spotify")
        assert result == _DEFAULT_THEMES["spotify"]

    def test_merges_user_overrides(self):
        cfg = {"theme": {"background": "#111111"}}
        result = load_plugin_theme(cfg, "spotify")
        assert result["background"] == "#111111"
        assert result["text"] == "#ffffff"  # default preserved
        assert result["accent"] == "#1db954"  # default preserved

    def test_full_override(self):
        cfg = {
            "theme": {
                "background": "#000000",
                "text": "#FFFFFF",
                "accent": "#00FF00",
                "accent2": "#FF00FF",
            }
        }
        result = load_plugin_theme(cfg, "spotify")
        assert result["background"] == "#000000"
        assert result["text"] == "#FFFFFF"
        assert result["accent"] == "#00FF00"
        assert result["accent2"] == "#FF00FF"

    def test_unknown_plugin_key_returns_empty_with_user_theme(self):
        cfg = {"theme": {"custom": "#123456"}}
        result = load_plugin_theme(cfg, "nonexistent")
        assert result == {"custom": "#123456"}

    def test_unknown_plugin_key_no_user_theme(self):
        cfg = {}
        result = load_plugin_theme(cfg, "nonexistent")
        assert result == {}


class TestThemeCss:
    def test_generates_css(self):
        colors = {"background": "#000000", "text": "#ffffff"}
        css = theme_css(colors)
        assert "--background: #000000;" in css
        assert "--text: #ffffff;" in css
        assert ":root {" in css

    def test_underscore_to_dash(self):
        colors = {"accent_color": "#ff0000"}
        css = theme_css(colors)
        assert "--accent-color: #ff0000;" in css

    def test_empty_dict(self):
        css = theme_css({})
        assert ":root {" in css
        assert "}" in css
