"""Unit tests for unified system_runtime settings store."""
from subsystems.config import system_runtime as sr


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "SYSTEM_RUNTIME_PATH", tmp_path / "system_runtime.json")
    monkeypatch.setattr(sr, "LEGACY_RISK_PATH", tmp_path / "risk_runtime.json")
    monkeypatch.setattr(sr, "_cache", None)


def test_load_save_merge_mask(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    rt = sr.load_settings()
    assert rt.risk.mode == "pct"
    assert rt.llm.provider == "lm_studio"

    sr.save_settings(
        {
            "provider": "openai_compatible",
            "base_url": "https://api.example/v1",
            "api_key": "sk-secret",
            "model": "gpt-test",
        },
        section="llm",
    )
    pub = sr.load_settings(force=True).public_dict(mask_secrets=True)
    assert pub["llm"]["api_key"] == "***"
    assert pub["llm"]["model"] == "gpt-test"
    assert pub["llm"]["provider"] == "openai_compatible"

    # blank / masked key must not wipe stored secret
    sr.save_settings({"api_key": "***", "temperature": 0.4}, section="llm")
    raw = sr.load_settings(force=True)
    assert raw.llm.api_key == "sk-secret"
    assert abs(raw.llm.temperature - 0.4) < 1e-9


def test_legacy_risk_migrate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    legacy = tmp_path / "risk_runtime.json"
    legacy.write_text(
        '{"mode":"fixed","fixed_dollars":3.25,"risk_pct":0.01}',
        encoding="utf-8",
    )
    rt = sr.load_settings()
    assert rt.risk.mode == "fixed"
    assert abs(rt.risk.fixed_dollars - 3.25) < 1e-9
    assert (tmp_path / "system_runtime.json").exists()


def test_symbol_overlay_merge(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    sr.save_settings({"EURUSD": {"atr_k1": 2.5, "use_atr_sizing": False}}, section="symbols")
    cfg = sr.merged_symbol_config("EURUSD")
    assert abs(cfg.atr_k1 - 2.5) < 1e-9
    assert cfg.use_atr_sizing is False
