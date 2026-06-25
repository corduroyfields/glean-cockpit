# Go-Live Runbook — SSO & Connectors (Datasources)

A repeatable checklist for standing up a new Glean deployment. Validate each gate
in the **Cockpit** before advancing (health should move AT RISK → HEALTHY).

---

## Phase 1 — SSO (do this first)
1. **Configure** the IdP (e.g. Okta SAML): metadata exchange, ACS URL, attribute mapping (email, groups).
2. **Provision** users (SCIM or directory sync); confirm `users_provisioned` ≈ licensed seats.
3. **Test** with a pilot group — confirm login + group membership flow through.
4. **Enforce** SSO so users *cannot* sign in outside it. ← _common miss; the Cockpit flags "configured but not enforced" as a warning._
5. **Gate:** SSO finding in the Cockpit is green.

## Phase 2 — Connectors / Datasources
For each datasource (Slack, Drive, Confluence, Jira, GitHub, …):
1. **Authorize** the connector (service account / OAuth) with least-privilege scopes.
2. **Map permissions** — confirm the datasource's ACLs (users/groups) sync into Glean so document access mirrors the source system.
3. **Run initial crawl**; confirm `document_count` is non-trivial and growing.
4. **Validate freshness** — `last_sync` recent. _Cockpit thresholds: warn ≥ 6h, critical ≥ 48h._
5. **Gate:** datasource finding is green (no stale/critical syncs).

## Phase 3 — Permission validation (do not skip)
1. Pick 3–5 representative users across departments.
2. In the **Permission Inspector**, confirm each sees **only** what they should — spot-check a sensitive doc is *hidden* from someone outside its ACL.
3. Confirm no unexpected `allowAnonymousAccess` documents (governance review).
4. **Gate:** permission spot-checks pass; governance findings reviewed.

## Phase 4 — Go-live gate (all must be true)
- [ ] SSO enforced
- [ ] All datasources healthy (no critical/stale)
- [ ] Permission spot-checks pass
- [ ] Governance (anonymous docs) reviewed
- [ ] Overall Cockpit health = **HEALTHY**

## Escalation
- **Connector failing / stale:** re-auth → check source-side rate limits → escalate to Glean Support/R&D with the datasource + last-sync timestamp.
- **Permission mismatch:** stop rollout; treat as P1 — never expose content beyond source permissions.
