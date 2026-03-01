from datetime import datetime, timezone

from app.core import alarm_store
from app.services import alarm_checker


class _ThresholdStub:
    def __init__(self, data):
        self._data = data

    def get_threshold(self, param_type, pump_id=None):
        value = self._data.get(param_type)
        if value is None:
            return None
        if isinstance(value, dict) and pump_id is not None and f"pump_{pump_id}" in value:
            return value[f"pump_{pump_id}"]
        return value


def test_log_alarm_dedup_updates_only_on_success(monkeypatch):
    alarm_store._last_alarms.clear()

    write_results = iter([False, True])
    write_calls = []

    def fake_write_point(*args, **kwargs):
        write_calls.append((args, kwargs))
        return next(write_results)

    monkeypatch.setattr(alarm_store, "write_point", fake_write_point)

    first = alarm_store.log_alarm(
        device_id="pump_1",
        alarm_type="current",
        param_name="pump_current_pump_1_I_0",
        value=88.0,
        threshold=80.0,
        level="alarm",
    )
    second = alarm_store.log_alarm(
        device_id="pump_1",
        alarm_type="current",
        param_name="pump_current_pump_1_I_0",
        value=88.0,
        threshold=80.0,
        level="alarm",
    )

    assert first is False
    assert second is True
    assert len(write_calls) == 2


def test_query_alarms_uses_prefix_filter_without_regex(monkeypatch):
    captured = {"query": ""}

    class _FakeQueryApi:
        def query(self, query):
            captured["query"] = query
            return []

    class _FakeClient:
        def query_api(self):
            return _FakeQueryApi()

    monkeypatch.setattr(alarm_store, "get_influx_client", lambda: _FakeClient())

    records = alarm_store.query_alarms(level="alarm", param_prefix="pump_current")

    assert records == []
    assert 'import "strings"' in captured["query"]
    assert "strings.hasPrefix" in captured["query"]
    assert '=~ /' not in captured["query"]
    assert 'r["level"] == "alarm"' in captured["query"]


def test_check_one_triggers_log_alarm_when_over_warning(monkeypatch):
    svc = _ThresholdStub({"current": {"pump_1": {"normal_max": 50.0, "warning_max": 80.0}}})
    monkeypatch.setattr(alarm_checker, "get_threshold_service", lambda: svc)

    calls = []

    def fake_log_alarm(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(alarm_checker, "log_alarm", fake_log_alarm)

    alarm_checker._check_one(
        device_id="pump_1",
        alarm_type="current",
        param_name="pump_current_pump_1_I_0",
        param_type="current",
        pump_idx=1,
        value=85.0,
        unit="A",
        timestamp=datetime.now(timezone.utc),
    )

    assert len(calls) == 1
    assert calls[0]["threshold"] == 80.0
    assert calls[0]["level"] == "alarm"


def test_check_pressure_alarm_triggers_high_and_low(monkeypatch):
    svc = _ThresholdStub({"pressure": {"high_alarm": 1.0, "low_alarm": 0.3}})
    monkeypatch.setattr(alarm_checker, "get_threshold_service", lambda: svc)

    calls = []

    def fake_log_alarm(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(alarm_checker, "log_alarm", fake_log_alarm)

    ts = datetime.now(timezone.utc)
    alarm_checker._check_pressure_alarm({"value": 1.2}, ts)
    alarm_checker._check_pressure_alarm({"value": 0.2}, ts)
    alarm_checker._check_pressure_alarm({"value": 0.0}, ts)

    param_names = [item["param_name"] for item in calls]
    assert "pressure_high" in param_names
    assert "pressure_low" in param_names
    assert len(calls) == 2
