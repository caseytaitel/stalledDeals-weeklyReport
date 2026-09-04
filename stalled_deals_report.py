#!/usr/bin/env python3
"""
CRO stalled-deals report.

Pulls all Realm Prospects deals in Discovery / Qualification / Planning / Evaluation /
Negotiation / Procurement that have been in the current stage ≥ 30 days, every rep,
no partner filter.
Writes a self-contained HTML file with an Overview tab and one tab per rep.
Rep tabs split deals by fiscal close period (past, remaining quarters, next FY).

USAGE
  1. pip install -r requirements.txt
  2. Set HUBSPOT_TOKEN in .env.local
  3. Run: python cro_stalled_report.py
  4. Open output/stalled_report_YYYY-MM-DD.html and share it yourself.
"""

import html
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv(".env.local")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")

if not HUBSPOT_TOKEN:
    sys.exit("ERROR: HUBSPOT_TOKEN environment variable not set.")

PORTAL_ID = "47829307"
HUBSPOT_API = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# Realm Prospects stages. Closed Won / Closed Lost / Closed No Opportunity
# / Deal Reg are omitted by not being in this list. 
STAGE_LABELS = {
    "appointmentscheduled": "10% Discovery",
    "qualifiedtobuy": "20% Qualification",
    "presentationscheduled": "30% Planning",
    "decisionmakerboughtin": "50% Evaluation",
    "1412214374": "75% Negotiation",
    "1412220225": "90% Procurement"
}
STALLED_STAGE_IDS = list(STAGE_LABELS)
STALLED_THRESHOLD_DAYS = 30

# One definition of the four color buckets. Under STALLED_THRESHOLD_DAYS is omitted.
BANDS = (
    {"lo": 30, "hi": 59, "key": "band_30_59", "row": "row-mild", "badge": "badge-mild", "header": "30–59d"},
    {"lo": 60, "hi": 89, "key": "band_60_89", "row": "row-watch", "badge": "badge-watch", "header": "60–89d"},
    {"lo": 90, "hi": 179, "key": "band_90_179", "row": "row-warn", "badge": "badge-warn", "header": "90–179d"},
    {"lo": 180, "hi": None, "key": "band_180", "row": "row-critical", "badge": "badge-critical", "header": "180d+"},
)

# Fiscal year starts February 1. FY number is the calendar year it ends in:
# Feb 2026–Jan 2027 is FY27; Q1 Feb–Apr, Q2 May–Jul, Q3 Aug–Oct, Q4 Nov–Jan.
FY_START_MONTH = 2

DEAL_RECORD_URL = f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-3/{{deal_id}}"

OUTPUT_DIR = "output"

_owner_cache = {}


# ---------------------------------------------------------------------------
# HubSpot I/O (network only — no stalled-deal rules here)
# ---------------------------------------------------------------------------

def _hubspot_error(action, exc_or_resp):
    sys.exit(f"ERROR: HubSpot {action} failed: {exc_or_resp}")


def hubspot_search_deals(filter_groups, properties, limit=200):
    """Search deals with pagination. Returns a list of result dicts."""
    results = []
    after = None
    reported_total = None
    while True:
        body = {
            "filterGroups": filter_groups,
            "properties": properties,
            "limit": limit,
        }
        if after:
            body["after"] = after
        try:
            resp = requests.post(
                f"{HUBSPOT_API}/crm/v3/objects/deals/search",
                headers=HEADERS,
                json=body,
                timeout=30,
            )
            if resp.status_code in (401, 403):
                _hubspot_error(
                    "deal search (auth)",
                    "token rejected. Check HUBSPOT_TOKEN and crm.objects.deals.read.",
                )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            _hubspot_error("deal search", exc)
        if reported_total is None:
            reported_total = data.get("total")
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    if reported_total is not None and reported_total > 10000:
        print(
            "WARNING: HubSpot search reports more than 10,000 matching deals; "
            "the report may be truncated.",
            file=sys.stderr,
        )
    return results


def fetch_early_stage_deals():
    """All Realm Prospects deals in listed STAGE_LABELS stages. Not yet age-filtered."""
    return hubspot_search_deals(
        filter_groups=[{
            "filters": [
                {"propertyName": "dealstage", "operator": "IN", "values": STALLED_STAGE_IDS},
            ]
        }],
        properties=[
            "dealname",
            "dealstage",
            "hs_v2_date_entered_current_stage",
            "createdate",
            "closedate",
            "hubspot_owner_id",
        ],
    )


def get_owner_name(owner_id):
    """Resolve a hubspot_owner_id to a display name, with caching.

    Archived owners 404 on the default endpoint. Retry with archived=true so
    deactivated reps still show a real name (e.g. Leo Clougherty) instead of
    "Owner {id}". Network/auth failures abort the run instead of labeling
    everyone Unassigned.
    """
    if not owner_id:
        return "Unassigned"
    if owner_id in _owner_cache:
        return _owner_cache[owner_id]

    def _display_name(data):
        return (
            f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
            or data.get("email")
            or "Unassigned"
        )

    def _fetch(archived=False):
        try:
            resp = requests.get(
                f"{HUBSPOT_API}/crm/v3/owners/{owner_id}",
                headers=HEADERS,
                params={"archived": "true"} if archived else None,
                timeout=30,
            )
        except requests.RequestException as exc:
            _hubspot_error("owners lookup", exc)
        if resp.status_code in (401, 403):
            _hubspot_error(
                "owners lookup (auth)",
                "token rejected. Check HUBSPOT_TOKEN and crm.objects.owners.read.",
            )
        return resp

    resp = _fetch(archived=False)
    if resp.status_code == 200:
        _owner_cache[owner_id] = _display_name(resp.json())
        return _owner_cache[owner_id]

    archived = _fetch(archived=True)
    if archived.status_code == 200:
        _owner_cache[owner_id] = _display_name(archived.json())
        return _owner_cache[owner_id]

    if resp.status_code >= 500 or archived.status_code >= 500:
        _hubspot_error(
            "owners lookup",
            f"server error (live={resp.status_code}, archived={archived.status_code})",
        )

    _owner_cache[owner_id] = "Unassigned"
    return _owner_cache[owner_id]


# ---------------------------------------------------------------------------
# Domain: dates, stalled filter, grouping
# ---------------------------------------------------------------------------

def days_since(date_str):
    """date_str is 'YYYY-MM-DD' or an ISO datetime string. Returns whole days elapsed."""
    if not date_str:
        return None
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        return None


def _parse_close_date(date_str):
    """Return a date from 'YYYY-MM-DD', or None if missing/invalid."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _fiscal_year(d):
    """Calendar year the FY ending on this date ends in. Feb 1, 2026 → 2027."""
    if d.month >= FY_START_MONTH:
        return d.year + 1
    return d.year


def _fiscal_quarter(d):
    """1–4 for a Feb-start fiscal year. Aug → 3, Jan → 4."""
    offset = (d.month - FY_START_MONTH) % 12
    return offset // 3 + 1


def _fy_label(year):
    return f"FY{year % 100:02d}"


def _close_period_sections(deals, as_of):
    """Split deals into past / remaining FY quarters / next FY / no date.

    Empty sections are omitted. Order inside each section is preserved
    (callers pass deals already sorted by days in stage).
    """
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    as_of_fy = _fiscal_year(as_of)
    as_of_q = _fiscal_quarter(as_of)
    later_label = _fy_label(as_of_fy + 1)
    buckets = [("Past close date", [])]
    for q in range(as_of_q, 5):
        buckets.append((f"Q{q}", []))
    buckets.append((later_label, []))
    buckets.append(("No close date", []))
    by_label = {label: rows for label, rows in buckets}

    for deal in deals:
        close = _parse_close_date(deal.get("close_date"))
        if close is None:
            by_label["No close date"].append(deal)
        elif close < as_of:
            by_label["Past close date"].append(deal)
        elif _fiscal_year(close) == as_of_fy and _fiscal_quarter(close) >= as_of_q:
            by_label[f"Q{_fiscal_quarter(close)}"].append(deal)
        else:
            by_label[later_label].append(deal)

    return [(label, rows) for label, rows in buckets if rows]


def _band_for_days(days):
    """Return the BANDS entry for a stalled deal's age."""
    for band in BANDS:
        hi = band["hi"]
        if days >= band["lo"] and (hi is None or days <= hi):
            return band
    return BANDS[-1]


def _band_counts(deals):
    counts = {band["key"]: 0 for band in BANDS}
    for deal in deals:
        counts[_band_for_days(deal["days_in_stage"])["key"]] += 1
    return counts


def _stalled_row(deal):
    """Map one HubSpot deal to a report row, or None if it is not stalled."""
    p = deal.get("properties") or {}
    stage_id = p.get("dealstage")
    if stage_id not in STAGE_LABELS:
        return None
    stage_days = days_since(p.get("hs_v2_date_entered_current_stage"))
    if stage_days is None or stage_days < STALLED_THRESHOLD_DAYS:
        return None
    close_raw = p.get("closedate") or ""
    return {
        "id": deal["id"],
        "name": p.get("dealname") or "(unnamed)",
        "stage_label": STAGE_LABELS[stage_id],
        "days_in_stage": stage_days,
        "days_open": days_since(p.get("createdate")),
        "close_date": close_raw[:10] if close_raw else "",
        "owner": get_owner_name(p.get("hubspot_owner_id")),
    }


def get_stalled_deals():
    rows = [row for row in (_stalled_row(deal) for deal in fetch_early_stage_deals()) if row]
    rows.sort(key=lambda r: r["days_in_stage"], reverse=True)
    return rows


def group_by_rep(rows):
    """One bucket per display name, sorted by stalled count desc then name."""
    by_owner = defaultdict(list)
    for row in rows:
        by_owner[row["owner"]].append(row)

    reps = []
    used_ids = set()
    for name, deals in by_owner.items():
        deals.sort(key=lambda r: r["days_in_stage"], reverse=True)
        counts = _band_counts(deals)
        reps.append({
            "name": name,
            "tab_id": _tab_id(name, used_ids),
            "deals": deals,
            "count": len(deals),
            **counts,
        })

    reps.sort(key=lambda r: (-r["count"], r["name"].casefold()))
    return reps


def _tab_id(name, used):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unassigned"
    slug = base
    n = 2
    while f"rep-{slug}" in used:
        slug = f"{base}-{n}"
        n += 1
    tab_id = f"rep-{slug}"
    used.add(tab_id)
    return tab_id


# ---------------------------------------------------------------------------
# HTML render (markup / CSS / JS only)
# ---------------------------------------------------------------------------

def _esc(value):
    return html.escape("" if value is None else str(value))


def _deal_href(deal_id):
    return DEAL_RECORD_URL.format(deal_id=deal_id)


def _urgency_class(days):
    return _band_for_days(days)["row"]


def _days_badge(days):
    return f'<span class="badge {_band_for_days(days)["badge"]}">{days}</span>'


def _format_date(date_str):
    if not date_str:
        return "—"
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return date_str


def _deal_name_cell(deal_id, name):
    return (
        f'<a class="deal-link" href="{_esc(_deal_href(deal_id))}" '
        f'target="_blank" rel="noopener">{_esc(name)}</a>'
    )


def _empty_row(colspan, message):
    return f'<tr class="empty"><td colspan="{colspan}">{_esc(message)}</td></tr>'


def _rep_deal_rows(deals):
    if not deals:
        return _empty_row(5, "None currently.")
    parts = []
    for r in deals:
        days = r["days_in_stage"]
        days_open = r["days_open"]
        parts.append(
            "<tr class=\"{cls}\">"
            "<td>{name}</td>"
            "<td>{stage}</td>"
            "<td class=\"num\">{open}</td>"
            "<td class=\"num\">{badge}</td>"
            "<td class=\"nowrap\">{close}</td>"
            "</tr>".format(
                cls=_urgency_class(days),
                name=_deal_name_cell(r["id"], r["name"]),
                stage=_esc(r["stage_label"]),
                badge=_days_badge(days),
                open="—" if days_open is None else days_open,
                close=_esc(_format_date(r["close_date"])),
            )
        )
    return "\n".join(parts)


def _rep_deal_table(deals):
    return (
        "<div class=\"table-wrap\">"
        "<table class=\"deals\">"
        "<thead><tr>"
        "<th>Deal Name</th>"
        "<th>Deal Stage</th>"
        "<th class=\"num\">Days Open</th>"
        "<th class=\"num\">Days in Stage</th>"
        "<th>Close Date</th>"
        "</tr></thead>"
        f"<tbody>{_rep_deal_rows(deals)}</tbody>"
        "</table>"
        "</div>"
    )


def _overview_rows(reps):
    if not reps:
        return _empty_row(2 + len(BANDS), "None currently.")
    parts = []
    for rep in reps:
        band_cells = "".join(
            f'<td class="num">{rep[band["key"]]}</td>' for band in BANDS
        )
        parts.append(
            "<tr>"
            "<td><a class=\"rep-link\" href=\"#{tab}\" data-goto=\"{tab}\">{name}</a></td>"
            "<td class=\"num\">{total}</td>"
            "{bands}"
            "</tr>".format(
                tab=_esc(rep["tab_id"]),
                name=_esc(rep["name"]),
                total=rep["count"],
                bands=band_cells,
            )
        )
    return "\n".join(parts)


def _overview_totals_row(reps):
    """One footer row: grand total plus each days-in-stage band across all reps."""
    grand = sum(r["count"] for r in reps)
    band_cells = "".join(
        f'<td class="num">{sum(r[band["key"]] for r in reps)}</td>' for band in BANDS
    )
    return (
        "<tr>"
        "<td>All</td>"
        f'<td class="num">{grand}</td>'
        f"{band_cells}"
        "</tr>"
    )


def _tab_buttons(reps):
    grand = sum(r["count"] for r in reps)
    parts = [
        '<button type="button" class="tab-btn active" role="tab" '
        f'data-tab="overview" data-count="{grand}" aria-selected="true">Overview</button>'
    ]
    for rep in reps:
        parts.append(
            '<button type="button" class="tab-btn" role="tab" '
            'data-tab="{tab}" data-count="{count}" aria-selected="false">{name}</button>'.format(
                tab=_esc(rep["tab_id"]),
                count=rep["count"],
                name=_esc(rep["name"]),
            )
        )
    return "\n".join(parts)


def _rep_panels(reps, as_of):
    parts = []
    for rep in reps:
        sections = []
        for title, deals in _close_period_sections(rep["deals"], as_of):
            sections.append(
                f'<div class="section"><h2>{_esc(title)}</h2>{_rep_deal_table(deals)}</div>'
            )
        parts.append(
            '<section class="tab-panel" id="{tab}" role="tabpanel" hidden>'
            "{sections}"
            "</section>".format(
                tab=_esc(rep["tab_id"]),
                sections="".join(sections),
            )
        )
    return "\n".join(parts)


CSS = """
  :root {
    --bg: #f4f6f8;
    --card: #ffffff;
    --ink: #1c2430;
    --muted: #5c6b7a;
    --line: #e4e8ed;
    --accent: #1f6feb;
    --mild: #a16207;
    --mild-bg: #fff7d9;
    --watch: #c2410c;
    --watch-bg: #fff2e1;
    --warn: #9a3412;
    --warn-bg: #ffebd9;
    --crit: #9f1239;
    --crit-bg: #ffebec;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.45;
  }
  .page {
    max-width: 1120px;
    margin: 0 auto;
    padding: 28px 20px 48px;
  }
  .masthead {
    border-bottom: 1px solid var(--line);
    padding: 4px 0 16px;
    margin-bottom: 16px;
  }
  .masthead h1 {
    margin: 0 0 4px;
    font-size: 20px;
    font-weight: 600;
    color: var(--ink);
  }
  .masthead h1 .count {
    color: var(--warn);
    font-weight: 600;
  }
  .masthead .date {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 0;
    border-bottom: 1px solid var(--line);
    margin-bottom: 20px;
  }
  .tab-btn {
    appearance: none;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    padding: 8px 12px;
    color: var(--muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
  }
  .tab-btn:hover { color: var(--ink); }
  .tab-btn.active {
    color: var(--ink);
    font-weight: 600;
    border-bottom-color: var(--accent);
  }
  .tab-panel[hidden] { display: none; }
  h2 {
    margin: 0 0 10px;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  .section { margin-bottom: 26px; }
  .table-wrap {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  table.overview {
    table-layout: fixed;
    width: 100%;
  }
  table.overview .col-rep { width: 11.5rem; }
  table.overview .col-total { width: 5.5rem; }
  table.overview td:first-child,
  table.overview th:first-child {
    white-space: nowrap;
  }
  table.deals {
    table-layout: fixed;
    width: 100%;
  }
  table.deals th:nth-child(1),
  table.deals td:nth-child(1) {
    width: auto;
  }
  table.deals th:nth-child(2),
  table.deals td:nth-child(2) {
    width: 11.5rem;
    white-space: nowrap;
  }
  table.deals th:nth-child(3),
  table.deals td:nth-child(3) {
    width: 7.5rem;
  }
  table.deals th:nth-child(4),
  table.deals td:nth-child(4) {
    width: 9.5rem;
  }
  table.deals th:nth-child(5),
  table.deals td:nth-child(5) {
    width: 8rem;
    white-space: nowrap;
  }
  th, td {
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid var(--line);
  }
  th {
    background: #f7f9fb;
    color: #3d4d5c;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    white-space: nowrap;
    position: sticky;
    top: 0;
    vertical-align: middle;
  }
  th.num, td.num {
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  th.band-group {
    text-align: center;
    letter-spacing: 0.04em;
  }
  tfoot td {
    font-weight: 700;
    color: var(--ink);
    background: #f7f9fb;
    border-top: 1px solid var(--line);
    border-bottom: none;
  }
  tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: #fafbfd; }
  tbody tr.row-mild:hover td { background: #feeda9; }
  tbody tr.row-watch:hover td { background: #ffe2c0; }
  tbody tr.row-warn:hover td { background: #fecfa0; }
  tbody tr.row-critical:hover td { background: #ffd9dd; }
  .num { white-space: nowrap; }
  .nowrap { white-space: nowrap; }
  .deal-link, .rep-link {
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }
  .deal-link { overflow-wrap: anywhere; }
  .deal-link:hover, .rep-link:hover { text-decoration: underline; }
  tr.row-mild { background: var(--mild-bg); }
  tr.row-watch { background: var(--watch-bg); }
  tr.row-warn { background: var(--warn-bg); }
  tr.row-critical { background: var(--crit-bg); }
  tr.empty td {
    color: var(--muted);
    font-style: italic;
    padding: 16px 12px;
  }
  .badge {
    display: inline-block;
    min-width: 2.6em;
    padding: 1px 7px;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 12px;
    text-align: center;
  }
  .badge-mild { background: #feeda9; color: var(--mild); }
  .badge-watch { background: #ffe2c0; color: var(--watch); }
  .badge-warn { background: #fecfa0; color: var(--warn); }
  .badge-critical { background: #ffd9dd; color: var(--crit); }
  th .badge {
    min-width: 0;
    padding: 2px 9px;
    letter-spacing: 0.02em;
    text-transform: none;
  }
"""

JS = """
(function () {
  var buttons = document.querySelectorAll(".tab-btn");
  var panels = document.querySelectorAll(".tab-panel");
  var countEl = document.getElementById("masthead-count");

  function activate(id) {
    if (!id) return;
    var found = false;
    panels.forEach(function (panel) {
      var match = panel.id === id;
      if (match) found = true;
      panel.hidden = !match;
    });
    if (!found) return;
    buttons.forEach(function (btn) {
      var on = btn.getAttribute("data-tab") === id;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
      if (on && countEl) {
        var count = btn.getAttribute("data-count");
        if (count) countEl.textContent = count;
      }
    });
    try {
      if (history.replaceState) {
        history.replaceState(null, "", "#" + id);
      } else {
        location.hash = id;
      }
    } catch (e) {}
  }

  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activate(btn.getAttribute("data-tab"));
    });
  });

  document.querySelectorAll("[data-goto]").forEach(function (el) {
    el.addEventListener("click", function (event) {
      event.preventDefault();
      activate(el.getAttribute("data-goto"));
    });
  });

  window.addEventListener("hashchange", function () {
    var fromHash = location.hash.replace(/^#/, "");
    if (fromHash) activate(fromHash);
  });

  var initial = location.hash.replace(/^#/, "");
  if (initial) {
    activate(initial);
  } else {
    activate("overview");
  }
})();
"""


def build_html_report(reps, now):
    today = now.strftime("%B %d, %Y")
    total = sum(r["count"] for r in reps)
    band_headers = "\n                ".join(
        f'<th class="num"><span class="badge {band["badge"]}">{band["header"]}</span></th>'
        for band in BANDS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stalled Deals — {today}</title>
<style>{CSS}</style>
</head>
<body>
  <div class="page">
    <header class="masthead">
      <h1>Stalled Deals: <span class="count" id="masthead-count">{total}</span></h1>
      <p class="date">{today}</p>
    </header>

    <nav class="tabs" role="tablist" aria-label="Report sections">
      {_tab_buttons(reps)}
    </nav>

    <section class="tab-panel" id="overview" role="tabpanel">
      <div class="section">
        <div class="table-wrap">
          <table class="overview">
            <colgroup>
              <col class="col-rep">
              <col class="col-total">
              <col class="col-band">
              <col class="col-band">
              <col class="col-band">
              <col class="col-band">
            </colgroup>
            <thead>
              <tr>
                <th rowspan="2">Rep</th>
                <th class="num" rowspan="2">Total</th>
                <th class="band-group" colspan="4">Days in stage</th>
              </tr>
              <tr>
                {band_headers}
              </tr>
            </thead>
            <tbody>
              {_overview_rows(reps)}
            </tbody>
            {f"<tfoot>{_overview_totals_row(reps)}</tfoot>" if reps else ""}
          </table>
        </div>
      </div>
    </section>

    {_rep_panels(reps, now.date() if isinstance(now, datetime) else now)}
  </div>
  <script>{JS}</script>
</body>
</html>
"""


def main():
    now = datetime.now()
    stalled = get_stalled_deals()
    reps = group_by_rep(stalled)
    report = build_html_report(reps, now)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"stalled_report_{now.strftime('%Y-%m-%d')}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {filepath}. Open it in a browser and share it yourself.")


if __name__ == "__main__":
    main()
