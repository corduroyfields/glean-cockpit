# Joint Success Plan — Acme Corp × Glean

**Status:** Live since 2026-05-01 · adoption phase · _Platform health: AT RISK_
**Plan owners:** AISM (Glean) + VP IT / Knowledge (Acme, exec sponsor)
**Cadence:** Weekly working sync · Monthly steering · **First EBR: Aug 2026** · Renewal: 2027-05

---

## 1. Business objectives (Acme's words)
- Cut time employees spend searching across Slack, Drive, Confluence, Jira, GitHub.
- Deflect repetitive support questions to self-serve AI answers.
- Do it **without exposing anything** beyond a user's existing permissions.

## 2. Success metrics (tracked in the Cockpit)
| Metric | Baseline (Jun 2026) | Target (EBR, Aug 2026) |
|---|---|---|
| Company adoption rate (Glean MAU / total MAU) | 45% | ≥ 65% |
| License penetration | 56% | ≥ 80% |
| Stalled departments (penetration < 25%) | 1 (Legal) | 0 |
| Platform health | AT RISK | HEALTHY |
| Quantified value | $2.8M/yr | Validated & growing |

## 3. Milestones
- ✅ **Go-live** (2026-05-01) — core datasources + SSO connected.
- ▶ **Stabilize health** (Jun 2026) — fix Jira connector sync, **enforce SSO**, review anonymous-access docs.
- ▢ **Targeted enablement** (Jul 2026) — Legal & Sales adoption plays (champions, training, use cases).
- ▢ **First EBR** (Aug 2026) — present value, adoption, and the next-quarter plan.
- ▢ **Expansion review** (Q4 2026) — additional datasources / seats based on demonstrated value.

## 4. Roles
| Who | Responsibility |
|---|---|
| **AISM (me)** | Owns plan, health/adoption, EBRs, escalations |
| Account Executive | Commercial, expansion, renewal |
| Solutions Architect | Connector/SSO technical depth |
| Customer champion | Internal enablement, change management |
| Glean Support / R&D | Connector + platform escalations |

## 5. Top risks → mitigations
| Risk | Mitigation | Owner |
|---|---|---|
| Jira connector failing (stale index → wrong answers) | Escalate to R&D; re-auth + monitor in Cockpit | AISM + Support |
| SSO configured but **not enforced** (security gap) | Enforce SSO before broad rollout | SA + Acme IT |
| Legal dept stalled (15% penetration) | Champion-led enablement; reclaim/redeploy seats if no lift | AISM + champion |
| Over-shared (anonymous) documents | Governance review of anonymous-access content | Acme IT |
