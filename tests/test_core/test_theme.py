from core.theme import _DEFAULT_THEMES, load_plugin_theme, theme_css


class TestLoadPluginTheme:
    def test_returns_defaults_when_no_user_theme(self):
        cfg = {}  # no theme section
        result = load_plugin_theme(cfg, "overlay_text")
        assert result == _DEFAULT_THEMES["overlay_text"]

    def test_merges_user_overrides(self):
        cfg = {"theme": {"background": "#111111"}}
        result = load_plugin_theme(cfg, "overlay_text")
        assert result["background"] == "#111111"
        assert result["text"] == "#ffffff"  # default preserved

    def test_full_override(self):
        cfg = {
            "theme": {
                "background": "#000000",
                "text": "#FFFFFF",
                "accent": "#00FF00",
            }
        }
        result = load_plugin_theme(cfg, "overlay_text")
        assert result["background"] == "#000000"
        assert result["text"] == "#FFFFFF"
        assert result["accent"] == "#00FF00"

    def test_unknown_key_returns_empty_with_user_theme(self):
        cfg = {"theme": {"custom": "#123456"}}
        result = load_plugin_theme(cfg, "nonexistent")
        assert result == {"custom": "#123456"}

    def test_unknown_key_no_user_theme(self):
        cfg = {}
        result = load_plugin_theme(cfg, "nonexistent")
        assert result == {}

    def test_plugins_own_their_defaults(self):
        """Plugins ship their default colors in their own config.yaml —
        the core must not carry per-plugin fallbacks."""
        from core.theme import _DEFAULT_THEMES

        for key in _DEFAULT_THEMES:
            assert key == "overlay_text"


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

    def test_strips_css_injection_from_values(self):
        css = theme_css({"background": "red;} </style><script>alert(1)</script>"})
        assert "</style>" not in css
        assert "<script>" not in css
        assert "};" not in css
        assert "--background: red /stylescriptalert(1)/script;" in css

    def test_sanitizes_keys(self):
        css = theme_css({"bg color": "#000000", "x};--evil: 1": "#000000"})
        assert "--bg-color: #000000;" in css
        assert "--x---evil-1: #000000;" in css
