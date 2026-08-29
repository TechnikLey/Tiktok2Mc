"""Tests for the encrypted chatbot session store (core.chatbot_session)."""

import json

import pytest

from core import chatbot_session as cs

VALID_SID = "abcd1234efgh5678ijkl"


@pytest.fixture
def session_path(project_dir):
    return project_dir / "data" / "chatbot_session.json"


class TestValidation:
    def test_valid_session_id_is_normalized(self):
        assert cs.validate_session_id(f"  {VALID_SID}  ") == VALID_SID

    def test_too_short_rejected(self):
        with pytest.raises(cs.SessionValidationError):
            cs.validate_session_id("short")

    def test_empty_rejected(self):
        with pytest.raises(cs.SessionValidationError):
            cs.validate_session_id("   ")

    def test_invalid_characters_rejected(self):
        with pytest.raises(cs.SessionValidationError):
            cs.validate_session_id("abc def; drop table users")

    def test_tt_target_idc_normalizes_and_validates(self):
        assert cs.validate_tt_target_idc(" va ") == "va"
        assert cs.validate_tt_target_idc(None) == ""
        with pytest.raises(cs.SessionValidationError):
            cs.validate_tt_target_idc("bad idc!")


class TestMasking:
    def test_long_ids_are_masked_with_prefix_and_suffix(self):
        masked = cs.mask_session_id(VALID_SID)
        assert masked == "abcd…ijkl"
        assert VALID_SID not in masked

    def test_short_ids_only_show_suffix(self):
        assert cs.mask_session_id("12345678") == "…5678"

    def test_none_stays_none(self):
        assert cs.mask_session_id(None) is None


class TestStoreRoundTrip:
    def test_save_creates_encrypted_record(self, session_path):
        info = cs.save_chatbot_session(VALID_SID, "va")
        assert info["configured"] is True
        assert info["masked_session_id"] == cs.mask_session_id(VALID_SID)
        assert info["tt_target_idc"] == "va"
        assert isinstance(info["updated"], float)

        # On disk the raw secret must never appear.
        record = json.loads(session_path.read_text(encoding="utf-8"))
        assert VALID_SID not in json.dumps(record)

    def test_load_returns_decrypted_credentials(self, session_path):
        cs.save_chatbot_session(VALID_SID, "maliva")
        assert cs.load_chatbot_session() == (VALID_SID, "maliva")

    def test_load_without_store_returns_none(self, session_path):
        assert cs.load_chatbot_session() is None

    def test_overwrite_replaces_old_value(self, session_path):
        cs.save_chatbot_session(VALID_SID, "")
        cs.save_chatbot_session("ffffffffffff0000", "useast2a")
        assert cs.load_chatbot_session() == ("ffffffffffff0000", "useast2a")

    def test_clear_removes_the_store(self, session_path):
        cs.save_chatbot_session(VALID_SID, "")
        assert cs.clear_chatbot_session() is True
        assert not session_path.exists()
        assert cs.clear_chatbot_session() is False
        assert cs.load_chatbot_session() is None


class TestInfoView:
    def test_info_when_absent(self, session_path):
        info = cs.get_chatbot_session_info()
        assert info == {
            "configured": False,
            "masked_session_id": None,
            "tt_target_idc": "",
            "updated": None,
        }

    def test_info_never_leaks_the_secret(self, session_path):
        cs.save_chatbot_session(VALID_SID, "va")
        blob = json.dumps(cs.get_chatbot_session_info(), ensure_ascii=False)
        assert VALID_SID not in blob
        masked = cs.mask_session_id(VALID_SID)
        assert masked is not None
        assert masked in blob

    def test_info_survives_corrupted_store(self, session_path):
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text("{not json", encoding="utf-8")
        info = cs.get_chatbot_session_info()
        assert info["configured"] is False


class _FakeCookie:
    """Mimics http.cookiejar.Cookie (what pywebview's get_cookies returns)."""

    def __init__(self, name, value):
        self.name = name
        self.value = value


class TestExtractSessionCookies:
    def test_extracts_from_cookiejar_objects(self):
        cookies = [
            _FakeCookie("tt-target-idc", "maliva"),
            _FakeCookie("sessionid", VALID_SID),
            _FakeCookie("sessionid_ss", "should-be-ignored"),
            _FakeCookie("other", "x"),
        ]
        assert cs.extract_session_cookies(cookies) == (VALID_SID, "maliva")

    def test_extracts_from_plain_dicts(self):
        cookies = [{"name": "sessionid", "value": VALID_SID}]
        assert cs.extract_session_cookies(cookies) == (VALID_SID, "")

    def test_missing_sessionid_returns_none(self):
        cookies = [_FakeCookie("sessionid_ss", "x"), {"name": "foo", "value": "bar"}]
        assert cs.extract_session_cookies(cookies) is None

    def test_empty_cookie_value_returns_none(self):
        assert cs.extract_session_cookies([_FakeCookie("sessionid", "")]) is None

    def test_empty_list_returns_none(self):
        assert cs.extract_session_cookies([]) is None

    def test_first_sessionid_wins(self):
        cookies = [
            _FakeCookie("sessionid", VALID_SID),
            _FakeCookie("sessionid", "zzzzzzzzzzzzzz"),
        ]
        assert cs.extract_session_cookies(cookies) == (VALID_SID, "")


class TestRequestBridgeReload:
    def test_writes_reload_signal(self, project_dir):
        assert cs.request_bridge_reload() is True
        signal = project_dir / "core" / "runtime" / "reload_chatbot"
        assert signal.exists()

    def test_creates_runtime_dir_if_missing(self, project_dir):
        import shutil

        runtime = project_dir / "core" / "runtime"
        if runtime.exists():
            shutil.rmtree(runtime)
        assert cs.request_bridge_reload() is True
        assert (runtime / "reload_chatbot").exists()
