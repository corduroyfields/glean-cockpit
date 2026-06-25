"""Core logic for the Deployment Health & Adoption Cockpit.

This module is the "brain". It loads a customer's Glean signals and computes
health (and, in later layers, adoption, risk, and EBR value). It knows nothing
about Streamlit or the browser, so every function here can be unit-tested alone.

Field names mirror Glean's own vocabulary — datasources, documents, and
permission ACLs — so the mock data lines up with what Glean's real APIs return.
Glean's HTTP API uses camelCase (e.g. `allowAnonymousAccess`); we use snake_case
here and will translate at the API boundary when we add the RestGleanClient.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class Datasource:
    id: str                    # Glean datasource identifier, e.g. "gdrive"
    display_name: str
    category: str              # e.g. "DOCUMENT_STORE", "TICKETING"
    last_sync_hours_ago: int
    document_count: int


@dataclass
class Permissions:
    # Mirrors Glean's document ACL fields (camelCase in the real API).
    allow_anonymous_access: bool
    allow_all_datasource_users_access: bool
    allowed_users: List[str]   # emails
    allowed_groups: List[str]  # group names


@dataclass
class Document:
    id: str
    title: str
    datasource: str            # references Datasource.id
    permissions: Permissions


@dataclass
class User:
    email: str
    name: str
    groups: List[str]


@dataclass
class SSO:
    configured: bool
    enforced: bool
    provider: str
    users_provisioned: int


@dataclass
class TeamUsage:
    team: str
    seats: int
    monthly_active_users: int
    weekly_active_users: int
    queries_last_30d: int
    search_success_rate: float


@dataclass
class ValueInputs:
    avg_minutes_saved_per_query: float
    loaded_hourly_cost_usd: float
    support_tickets_deflected_last_30d: int
    avg_minutes_per_support_ticket: float


@dataclass
class CustomerData:
    name: str
    plan: str
    seats_licensed: int
    go_live_date: str
    datasources: List[Datasource]
    documents: List[Document]
    users: List[User]
    groups: List[str]
    sso: SSO
    usage_by_team: List[TeamUsage]
    total_company_mau: int
    value_inputs: ValueInputs


@dataclass
class Finding:
    area: str                  # e.g. "datasource:jira" or "sso"
    severity: str              # "ok" | "warn" | "critical"
    message: str


@dataclass
class HealthReport:
    overall: str               # "healthy" | "needs_attention" | "at_risk"
    findings: List[Finding]


def _load_document(raw: dict) -> Document:
    """Build a Document, translating its nested permissions block."""
    return Document(
        id=raw["id"],
        title=raw["title"],
        datasource=raw["datasource"],
        permissions=Permissions(**raw["permissions"]),
    )


def load_customer(path: str) -> CustomerData:
    """Read a customer JSON file and turn it into typed Python objects."""
    with open(path) as f:
        raw = json.load(f)

    return CustomerData(
        name=raw["customer"]["name"],
        plan=raw["customer"]["plan"],
        seats_licensed=raw["customer"]["seats_licensed"],
        go_live_date=raw["customer"]["go_live_date"],
        datasources=[Datasource(**d) for d in raw["datasources"]],
        documents=[_load_document(d) for d in raw["documents"]],
        users=[User(**u) for u in raw["users"]],
        groups=raw["groups"],
        sso=SSO(**raw["sso"]),
        usage_by_team=[TeamUsage(**t) for t in raw["usage_by_team"]],
        total_company_mau=raw["total_company_mau"],
        value_inputs=ValueInputs(**raw["value_inputs"]),
    )


class GleanClient(ABC):
    """A source of one customer's Glean deployment data.

    The rest of the app depends on this abstraction, never on where the data
    actually comes from — so we can run on local mock data today and a live
    Glean tenant tomorrow just by swapping the implementation.
    """

    @abstractmethod
    def load(self) -> CustomerData:
        ...


class MockGleanClient(GleanClient):
    """Local implementation — reads a customer's data from a JSON fixture."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> CustomerData:
        return load_customer(self.path)


class RestGleanClient(GleanClient):
    """Live implementation — assembles CustomerData from Glean's real REST APIs.

    Not wired up here (needs a Glean tenant + API token). Sketch of the real
    work, to show exactly where this plugs in:
      - Indexing API   -> datasources, documents (+ ACL permissions), users, groups
      - Insights API   -> usage_by_team (WAU/MAU by department), total_company_mau
      - Admin / config -> sso posture, customer profile (plan, seats, go-live)
    Each endpoint returns camelCase JSON (e.g. allowAnonymousAccess) — this is the
    translation boundary where we map it onto our snake_case dataclasses.
    """

    def __init__(self, instance_url: str, api_token: str):
        self.instance_url = instance_url
        self.api_token = api_token

    def load(self) -> CustomerData:
        raise NotImplementedError(
            "RestGleanClient needs a live Glean tenant + API token. "
            "Use MockGleanClient for local development and demos."
        )


# Thresholds for datasource freshness, kept as named constants so the rules are
# obvious and easy to defend in review (no "magic numbers" buried in logic).
SYNC_WARN_HOURS = 6
SYNC_CRITICAL_HOURS = 48


def score_datasource(d: Datasource) -> Finding:
    """Judge one datasource's health from how long since it last synced."""
    if d.last_sync_hours_ago >= SYNC_CRITICAL_HOURS:
        return Finding(f"datasource:{d.id}", "critical",
                       f"{d.display_name} hasn't synced in {d.last_sync_hours_ago}h — index is going stale")
    if d.last_sync_hours_ago >= SYNC_WARN_HOURS:
        return Finding(f"datasource:{d.id}", "warn",
                       f"{d.display_name} last synced {d.last_sync_hours_ago}h ago — watch for drift")
    return Finding(f"datasource:{d.id}", "ok",
                   f"{d.display_name} healthy — synced {d.last_sync_hours_ago}h ago")


def score_sso(sso: SSO) -> Finding:
    """Judge SSO posture: unconfigured is critical, configured-but-unenforced is a warning."""
    if not sso.configured:
        return Finding("sso", "critical", "SSO is not configured — blocks a secure go-live")
    if not sso.enforced:
        return Finding("sso", "warn",
                       "SSO configured but not enforced — users can still sign in outside SSO")
    return Finding("sso", "ok", f"SSO enforced via {sso.provider}")


def can_access(user: User, document: Document) -> bool:
    """Glean-style inclusive allow-list check: may this user see this document?

    Access is granted if ANY rule allows it; there are no explicit deny rules.
    """
    p = document.permissions
    if p.allow_anonymous_access:
        return True
    if p.allow_all_datasource_users_access:
        return True  # simplification: in our mock, every user is a datasource user
    if user.email in p.allowed_users:
        return True
    if set(user.groups) & set(p.allowed_groups):
        return True
    return False


def accessible_documents(user: User, documents: List[Document]) -> List[Document]:
    """Filter a document set down to what one user is permitted to see."""
    return [d for d in documents if can_access(user, d)]


def score_governance(documents: List[Document]) -> Finding:
    """Surface over-sharing risk: documents visible to the entire company."""
    anon = [d for d in documents if d.permissions.allow_anonymous_access]
    if anon:
        titles = ", ".join(d.title for d in anon)
        return Finding("governance", "warn",
                       f"{len(anon)} document(s) visible to all employees (anonymous access) "
                       f"— confirm intended: {titles}")
    return Finding("governance", "ok", "No documents are anonymously accessible")


def assess_health(data: CustomerData) -> HealthReport:
    """Combine datasource + SSO + governance findings into one verdict (worst severity wins)."""
    findings = [score_datasource(d) for d in data.datasources]
    findings.append(score_sso(data.sso))
    findings.append(score_governance(data.documents))

    if any(f.severity == "critical" for f in findings):
        overall = "at_risk"
    elif any(f.severity == "warn" for f in findings):
        overall = "needs_attention"
    else:
        overall = "healthy"

    return HealthReport(overall=overall, findings=findings)


@dataclass
class TeamAdoption:
    team: str
    seats: int
    monthly_active_users: int
    weekly_active_users: int
    license_penetration: float   # MAU / seats — "are we using what we bought?"
    stickiness: float            # WAU / MAU — do people come back weekly?


@dataclass
class AdoptionSummary:
    glean_mau: int               # company-wide Glean monthly active users
    total_company_mau: int       # all employees active in the business (the denominator)
    adoption_rate: float         # Glean's own formula: Glean MAU / Total MAU
    license_penetration: float   # Glean MAU / seats licensed
    teams: List[TeamAdoption]


@dataclass
class AdoptionReport:
    summary: AdoptionSummary
    findings: List[Finding]


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Divide without crashing on a zero denominator (e.g. a team with 0 seats)."""
    return numerator / denominator if denominator else 0.0


def compute_team_adoption(t: TeamUsage) -> TeamAdoption:
    """Derive a department's adoption ratios from its raw active-user counts."""
    return TeamAdoption(
        team=t.team,
        seats=t.seats,
        monthly_active_users=t.monthly_active_users,
        weekly_active_users=t.weekly_active_users,
        license_penetration=_safe_ratio(t.monthly_active_users, t.seats),
        stickiness=_safe_ratio(t.weekly_active_users, t.monthly_active_users),
    )


# A department using fewer than this share of its licensed seats is under-adopted.
PENETRATION_WARN = 0.50
PENETRATION_CRITICAL = 0.25


def assess_adoption(data: CustomerData) -> AdoptionReport:
    """Compute company + per-department adoption, and flag under-adopted teams."""
    teams = [compute_team_adoption(t) for t in data.usage_by_team]
    glean_mau = sum(t.monthly_active_users for t in teams)

    summary = AdoptionSummary(
        glean_mau=glean_mau,
        total_company_mau=data.total_company_mau,
        adoption_rate=_safe_ratio(glean_mau, data.total_company_mau),
        license_penetration=_safe_ratio(glean_mau, data.seats_licensed),
        teams=teams,
    )

    findings = []
    for t in teams:
        if t.license_penetration < PENETRATION_CRITICAL:
            findings.append(Finding(f"adoption:{t.team}", "critical",
                f"{t.team} adoption stalled — only {t.monthly_active_users}/{t.seats} seats active "
                f"({t.license_penetration:.0%})"))
        elif t.license_penetration < PENETRATION_WARN:
            findings.append(Finding(f"adoption:{t.team}", "warn",
                f"{t.team} under-adopted — {t.license_penetration:.0%} of seats active"))
        else:
            findings.append(Finding(f"adoption:{t.team}", "ok",
                f"{t.team} adopting well — {t.license_penetration:.0%} of seats active"))

    return AdoptionReport(summary=summary, findings=findings)


@dataclass
class ValueEstimate:
    queries_last_30d: int
    hours_saved_search: float
    search_value_usd: float
    tickets_deflected: int
    deflection_value_usd: float
    monthly_value_usd: float
    annualized_value_usd: float


def estimate_value(data: CustomerData) -> ValueEstimate:
    """Translate usage into an EBR-ready dollar value: search time saved + ticket deflection.

    Two transparent levers, both priced at the customer's loaded hourly cost:
      - searches/mo x minutes saved per search -> hours -> dollars
      - tickets deflected/mo x handle minutes  -> hours -> dollars
    The per-query and per-ticket minutes are assumptions to validate with the customer.
    """
    vi = data.value_inputs
    total_queries = sum(t.queries_last_30d for t in data.usage_by_team)

    hours_saved_search = total_queries * vi.avg_minutes_saved_per_query / 60
    search_value = hours_saved_search * vi.loaded_hourly_cost_usd

    deflection_hours = vi.support_tickets_deflected_last_30d * vi.avg_minutes_per_support_ticket / 60
    deflection_value = deflection_hours * vi.loaded_hourly_cost_usd

    monthly = search_value + deflection_value
    return ValueEstimate(
        queries_last_30d=total_queries,
        hours_saved_search=hours_saved_search,
        search_value_usd=search_value,
        tickets_deflected=vi.support_tickets_deflected_last_30d,
        deflection_value_usd=deflection_value,
        monthly_value_usd=monthly,
        annualized_value_usd=monthly * 12,
    )


if __name__ == "__main__":
    client = MockGleanClient("data/acme.json")
    data = client.load()
    print(f"Loaded: {data.name} ({data.plan}, {data.seats_licensed} seats)")
    print(f"Datasources: {len(data.datasources)}  |  Documents: {len(data.documents)}  |  Groups: {len(data.groups)}")
    for d in data.datasources:
        print(f"  - {d.display_name:<13} {d.category:<16} synced {d.last_sync_hours_ago}h ago")

    report = assess_health(data)
    print(f"\nPlatform health: {report.overall.upper()}")
    for f in report.findings:
        if f.severity != "ok":
            print(f"  [{f.severity:<8}] {f.message}")

    dana = next(u for u in data.users if u.email == "dana@acme.com")
    visible = accessible_documents(dana, data.documents)
    print(f"\nPermission preview — {dana.name} ({', '.join(dana.groups)}) "
          f"can see {len(visible)}/{len(data.documents)} documents:")
    for d in visible:
        print(f"  + {d.title}")

    adoption = assess_adoption(data)
    s = adoption.summary
    print(f"\nAdoption: {s.adoption_rate:.0%} company-wide "
          f"(Glean MAU {s.glean_mau} / {s.total_company_mau} total) | "
          f"license penetration {s.license_penetration:.0%}")
    for f in adoption.findings:
        if f.severity != "ok":
            print(f"  [{f.severity:<8}] {f.message}")

    value = estimate_value(data)
    print(f"\nEstimated value: ${value.monthly_value_usd:,.0f}/mo "
          f"(${value.annualized_value_usd:,.0f}/yr) — "
          f"{value.hours_saved_search:,.0f} hrs saved + {value.tickets_deflected:,} tickets deflected")
