# CRO Stalled Deals Report

A one-file HTML report for CRO 1:1s: every **Realm Prospects** deal that has sat **30 or more days** through **50% Evaluation** (Discovery, Qualification, Planning, Evaluation). Deal Reg is not included. All reps, including direct and no-partner deals. Closed Won / Closed Lost / Closed No Opportunity are out.

This is not the Channel Ops weekly report. Channel’s 14-day cutoff, partner-required filter, deal-reg table, and Slack post are not used here. Filters, columns, and colors are defined in `SPEC.md`.

## How to run

From this folder, in PowerShell:

```
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

You only need to create the venv and install once. After that:

```
.\venv\Scripts\Activate.ps1
python cro_stalled_report.py
```

The script reads `HUBSPOT_TOKEN` from `.env.local` (never commit that file). HubSpot must be reachable. It writes `output/cro_stalled_report_YYYY-MM-DD.html`. Running twice on the same calendar day overwrites that file.

If HubSpot rejects the token or the API is down, the script exits with an `ERROR:` line instead of writing a partial report.

## Sharing

Open the HTML in a browser, check Overview and each rep tab, then send the file yourself (email, Slack, etc.). Nothing posts automatically.

## What you should see

- Overview: total stalled deals, number of reps, counts by color band, summary table (click a name to open that rep’s tab).
- One tab per rep who has at least one stalled deal.
- Columns: Deal Name (HubSpot record link), Deal Stage, Days in Stage, Close Date.
- Colors: 30–59 yellow, 60–89 orange, 90–179 dark orange, 180+ red. Nothing under 30 days is listed.

Archived HubSpot owners are resolved by name (so Leo Clougherty is not shown as a numeric owner id). A deal with no owner, or an owner HubSpot cannot find even in archived records, lands on an **Unassigned** tab.

Days in stage are whole days in UTC from `hs_v2_date_entered_current_stage`. The date in the report title is your computer’s local date.
