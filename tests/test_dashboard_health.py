"""Tests for dashboard health / state derivation."""
from dashboard.health import build_alerts, build_subsystem_status, derive_system_state, resolve_equity


def test_degraded_when_core_offline():
    subs = build_subsystem_status(mt5_connected=False, zmq_alive=False, cooldown=False)
    assert subs["execution"] == "OFFLINE"
    assert subs["data_ingestion"] == "OFFLINE"
    state = derive_system_state(red_folder=False, subsystems=subs, mt5_connected=False)
    assert state == "OFFLINE"
    alerts = build_alerts(
        subsystems=subs,
        mt5_connected=False,
        red_folder=False,
        red_title=None,
        cooldown=False,
    )
    assert len(alerts) >= 1
    assert any(a["code"] == "mt5_offline" for a in alerts)


def test_normal_when_mt5_up():
    subs = build_subsystem_status(mt5_connected=True, zmq_alive=True, cooldown=False)
    state = derive_system_state(red_folder=False, subsystems=subs, mt5_connected=True)
    assert state == "NORMAL"


def test_halt_beats_offline():
    subs = build_subsystem_status(mt5_connected=False, zmq_alive=False, cooldown=False)
    state = derive_system_state(red_folder=True, subsystems=subs, mt5_connected=False)
    assert state == "HALT_TRADING"


def test_resolve_equity_prefers_live():
    eq, stale = resolve_equity({"connected": True, "equity": 50.0}, last_equity=40.0)
    assert eq == 50.0 and stale is False
    eq2, stale2 = resolve_equity({"connected": False, "equity": 0}, last_equity=48.5)
    assert eq2 == 48.5 and stale2 is True
