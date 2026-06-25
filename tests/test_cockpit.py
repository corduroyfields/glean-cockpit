"""Unit tests for the cockpit core logic.

Run either way:
    python3 tests/test_cockpit.py     # standalone, no dependencies
    python3 -m pytest tests/          # if pytest is installed
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cockpit import (
    Datasource, SSO, TeamUsage,
    score_datasource, score_sso, assess_health, load_customer,
    can_access, accessible_documents, score_governance,
    compute_team_adoption, assess_adoption, estimate_value,
    GleanClient, MockGleanClient, RestGleanClient,
)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "acme.json")


def _user(data, email):
    return next(u for u in data.users if u.email == email)


def _doc(data, doc_id):
    return next(d for d in data.documents if d.id == doc_id)


def test_fresh_datasource_is_ok():
    f = score_datasource(Datasource("slack", "Slack", "MESSAGING", 1, 1000))
    assert f.severity == "ok"


def test_degraded_datasource_warns():
    f = score_datasource(Datasource("confluence", "Confluence", "KNOWLEDGE_HUB", 14, 1000))
    assert f.severity == "warn"


def test_stale_datasource_is_critical():
    f = score_datasource(Datasource("jira", "Jira", "TICKETING", 73, 1000))
    assert f.severity == "critical"


def test_unenforced_sso_warns():
    f = score_sso(SSO(configured=True, enforced=False, provider="Okta", users_provisioned=1140))
    assert f.severity == "warn"


def test_overall_is_at_risk_when_any_critical():
    report = assess_health(load_customer(DATA))
    assert report.overall == "at_risk"


def test_data_model_loads_documents_and_acls():
    data = load_customer(DATA)
    assert len(data.documents) == 5
    handbook = next(d for d in data.documents if d.id == "doc-003")
    assert handbook.permissions.allow_anonymous_access is True


def test_user_can_access_own_group_document():
    data = load_customer(DATA)
    assert can_access(_user(data, "dana@acme.com"), _doc(data, "doc-001")) is True


def test_user_cannot_access_other_group_document():
    data = load_customer(DATA)
    assert can_access(_user(data, "dana@acme.com"), _doc(data, "doc-002")) is False


def test_anonymous_document_visible_to_all():
    data = load_customer(DATA)
    assert can_access(_user(data, "dana@acme.com"), _doc(data, "doc-003")) is True


def test_named_user_grant_overrides_group():
    # Sam is in Customer-Support, not Engineering, but is named on doc-004 directly.
    data = load_customer(DATA)
    assert can_access(_user(data, "support-lead@acme.com"), _doc(data, "doc-004")) is True


def test_accessible_documents_filters_correctly():
    data = load_customer(DATA)
    visible = accessible_documents(_user(data, "dana@acme.com"), data.documents)
    assert {d.id for d in visible} == {"doc-001", "doc-003"}


def test_governance_flags_anonymous_documents():
    data = load_customer(DATA)
    assert score_governance(data.documents).severity == "warn"


def test_team_adoption_computes_penetration_and_stickiness():
    t = TeamUsage("Eng", seats=100, monthly_active_users=80, weekly_active_users=60,
                  queries_last_30d=0, search_success_rate=0.8)
    a = compute_team_adoption(t)
    assert a.license_penetration == 0.8   # 80 / 100
    assert a.stickiness == 0.75           # 60 / 80


def test_dead_team_flagged_critical():
    data = load_customer(DATA)
    legal = next(f for f in assess_adoption(data).findings if f.area == "adoption:Legal")
    assert legal.severity == "critical"


def test_company_adoption_rate_uses_total_mau():
    data = load_customer(DATA)
    s = assess_adoption(data).summary
    assert s.glean_mau == 677              # sum of team MAUs
    assert s.total_company_mau == 1500
    assert abs(s.adoption_rate - 677 / 1500) < 1e-9


def test_adoption_summary_covers_all_teams():
    data = load_customer(DATA)
    assert len(assess_adoption(data).summary.teams) == 5


def test_mock_client_loads_customer():
    assert MockGleanClient(DATA).load().name == "Acme Corp"


def test_mock_client_satisfies_interface():
    assert isinstance(MockGleanClient(DATA), GleanClient)


def test_rest_client_not_implemented():
    try:
        RestGleanClient("https://acme.glean.com", "fake-token").load()
    except NotImplementedError:
        return
    assert False, "expected NotImplementedError"


def test_value_estimate_matches_formula():
    data = load_customer(DATA)
    v = estimate_value(data)
    assert v.queries_last_30d == 42310                       # sum of team queries
    assert abs(v.search_value_usd - 42310 * 4.5 / 60 * 65) < 1e-6
    assert abs(v.monthly_value_usd - (v.search_value_usd + v.deflection_value_usd)) < 1e-6
    assert abs(v.annualized_value_usd - v.monthly_value_usd * 12) < 1e-6


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        else:
            print(f"PASS  {t.__name__}")
            passed += 1
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
