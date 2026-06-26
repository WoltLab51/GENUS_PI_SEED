from genus import rules
from tests.conftest import observe_cpu_value


def test_registry_holds_the_rule_reactors():
    assert rules.apply_threshold in rules.REACTORS
    assert rules.apply_trend in rules.REACTORS
    assert rules.apply_correlation in rules.REACTORS


def test_a_registered_reactor_runs_on_each_observation(monkeypatch, conn):
    seen = []

    def spy(_conn, metric_key):
        seen.append(metric_key)
        return []

    monkeypatch.setattr(rules, "REACTORS", rules.REACTORS + (spy,))
    observe_cpu_value(conn, 50.0)

    # registering a reactor is enough — process_observation dispatches it uniformly
    assert rules.CPU_METRIC_KEY in seen
