"""Streamlit UI for the Deployment Health & Adoption Cockpit.

This file is a THIN presentation layer. It contains no business logic — it only
calls functions from cockpit.py and arranges the results on screen. All the
"thinking" (and its tests) lives in the core module.
"""

import os

import pandas as pd
import streamlit as st

from cockpit import (
    MockGleanClient, assess_health, assess_adoption, accessible_documents, estimate_value,
)

DATA = os.path.join(os.path.dirname(__file__), "data", "acme.json")


@st.cache_data
def get_data():
    """Load the customer once and reuse it across reruns (see caching note)."""
    return MockGleanClient(DATA).load()


def acl_summary(doc):
    """Human-readable summary of who a document's ACL grants access to (display only)."""
    p = doc.permissions
    if p.allow_anonymous_access:
        return "Everyone (anonymous access)"
    parts = []
    if p.allowed_groups:
        parts.append("groups: " + ", ".join(p.allowed_groups))
    if p.allowed_users:
        parts.append("users: " + ", ".join(p.allowed_users))
    if p.allow_all_datasource_users_access:
        parts.append("all datasource users")
    return "; ".join(parts) if parts else "no grants"


st.set_page_config(page_title="Glean Deployment Cockpit", page_icon=":bar_chart:", layout="wide")

data = get_data()
health = assess_health(data)
adoption = assess_adoption(data)
value = estimate_value(data)

# ---------- Header (always visible) ----------
st.title("Glean Deployment Cockpit")
st.caption(f"{data.name}  ·  {data.plan}  ·  {data.seats_licensed:,} seats  ·  go-live {data.go_live_date}")

verdict_label = {"healthy": "HEALTHY", "needs_attention": "NEEDS ATTENTION", "at_risk": "AT RISK"}
banner = {"healthy": st.success, "needs_attention": st.warning, "at_risk": st.error}[health.overall]
banner(f"Platform health: {verdict_label[health.overall]}")

st.subheader("Estimated business value")
v1, v2, v3, v4 = st.columns(4)
v1.metric("Value / month", f"${value.monthly_value_usd / 1000:,.0f}K")
v2.metric("Annualized", f"${value.annualized_value_usd / 1_000_000:,.1f}M")
v3.metric("Hours saved / mo", f"{value.hours_saved_search:,.0f}")
v4.metric("Tickets deflected / mo", f"{value.tickets_deflected:,}")
st.caption(
    f"{value.queries_last_30d:,} searches/mo × {data.value_inputs.avg_minutes_saved_per_query} min saved, "
    f"plus {value.tickets_deflected:,} tickets deflected, at ${data.value_inputs.loaded_hourly_cost_usd}/hr "
    f"loaded cost — assumptions editable per customer."
)

tab_health, tab_adoption, tab_perms = st.tabs(["Platform health", "Adoption", "Permission inspector"])

# ---------- Platform Health ----------
with tab_health:
    criticals = [f for f in health.findings if f.severity == "critical"]
    warnings = [f for f in health.findings if f.severity == "warn"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Critical issues", len(criticals))
    c2.metric("Warnings", len(warnings))
    c3.metric("Datasources", len(data.datasources))
    c4.metric("Documents indexed", f"{sum(d.document_count for d in data.datasources):,}")

    issues = criticals + warnings
    if issues:
        for f in issues:
            show = st.error if f.severity == "critical" else st.warning
            show(f.message)
    else:
        st.success("No platform issues detected.")

    with st.expander("Show healthy checks"):
        for f in health.findings:
            if f.severity == "ok":
                st.write(f"✓ {f.message}")

# ---------- Adoption ----------
with tab_adoption:
    s = adoption.summary

    a1, a2, a3 = st.columns(3)
    a1.metric("Adoption rate", f"{s.adoption_rate:.0%}", help="Glean MAU / total company MAU")
    a2.metric("License penetration", f"{s.license_penetration:.0%}", help="Glean MAU / licensed seats")
    a3.metric("Glean MAU", f"{s.glean_mau:,}")

    severity_by_team = {f.area.split(":", 1)[1]: f.severity for f in adoption.findings}
    status_label = {"critical": "Stalled", "warn": "Under-adopted", "ok": "Healthy"}

    table = pd.DataFrame([
        {
            "Team": t.team,
            "MAU": t.monthly_active_users,
            "Seats": t.seats,
            "Penetration": round(t.license_penetration * 100),
            "Stickiness": round(t.stickiness * 100),
            "Status": status_label[severity_by_team[t.team]],
        }
        for t in s.teams
    ])

    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "MAU": st.column_config.NumberColumn("Monthly actives"),
            "Penetration": st.column_config.ProgressColumn(
                "License penetration", format="%d%%", min_value=0, max_value=100),
            "Stickiness": st.column_config.ProgressColumn(
                "Stickiness (WAU/MAU)", format="%d%%", min_value=0, max_value=100),
        },
    )

    for f in adoption.findings:
        if f.severity != "ok":
            (st.error if f.severity == "critical" else st.warning)(f.message)

# ---------- Permission Inspector ----------
with tab_perms:
    st.caption("Pick a user to see exactly which documents Glean would let them surface — ACLs enforced.")

    choice = st.selectbox(
        "View as user",
        range(len(data.users)),
        format_func=lambda i: f"{data.users[i].name}  ({', '.join(data.users[i].groups)})",
    )
    user = data.users[choice]

    visible = accessible_documents(user, data.documents)
    visible_ids = {d.id for d in visible}
    hidden = [d for d in data.documents if d.id not in visible_ids]

    st.metric(f"{user.name} can access", f"{len(visible)} / {len(data.documents)} documents")

    col_visible, col_hidden = st.columns(2)
    with col_visible:
        st.markdown("**✓ Can see**")
        for d in visible:
            st.success(f"{d.title}  \n_{acl_summary(d)}_")
    with col_hidden:
        st.markdown("**✗ Cannot see**")
        for d in hidden:
            st.error(f"{d.title}  \n_{acl_summary(d)}_")
