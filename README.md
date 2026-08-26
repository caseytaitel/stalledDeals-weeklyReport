# CRO Stalled Deals Report

A one-file HTML report for CRO 1:1s: every **Realm Prospects** deal that has sat **30 or more days** through **50% Evaluation** (Discovery, Qualification, Planning, Evaluation). Deal Reg is not included. All reps, including direct and no-partner deals. Closed Won / Closed Lost / Closed No Opportunity are out.

This is not the Channel Ops weekly report. Channel’s 14-day cutoff, partner-required filter, deal-reg table, and Slack post are not used here. Filters, columns, and colors live in `stalled_deals_report.py`.

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
python stalled_deals_report.py
```

The script reads `HUBSPOT_TOKEN` from `.env.local` (never commit that file). HubSpot must be reachable. It writes `output/cro_stalled_report_YYYY-MM-DD.html`. Running twice on the same calendar day overwrites that file.

If HubSpot rejects the token or the API is down, the script exits with an `ERROR:` line instead of writing a partial report.

## Sharing

Open the HTML in a browser, check Overview and each rep tab, then send the file yourself (email, Slack, etc.). Nothing posts automatically.

## What you should see

- Masthead: **Stalled Deals: N**. N is the company total on Overview and that rep’s count when you switch tabs (or click a name on Overview).
- Overview: one row per rep with total stalled and counts by days-in-stage band, plus an All footer.
- One tab per rep who has at least one stalled deal. The tab name is the who; there is no second heading with the rep’s name.
- Rep tabs group deals by close date, empty groups omitted: **Past close date**, remaining quarters of the current fiscal year, then next FY (for example **Q3**, **Q4**, **FY28**). Fiscal year starts Feb 1 (Q1 Feb–Apr, Q2 May–Jul, Q3 Aug–Oct, Q4 Nov–Jan). A blank HubSpot close date gets its own **No close date** group.
- Columns: Deal Name (HubSpot record link), Deal Stage, Days in Stage, Close Date.
- Colors: 30–59 yellow, 60–89 orange, 90–179 dark orange, 180+ red. Nothing under 30 days is listed. Close date is not a pull filter; it only affects grouping on the rep tabs.

Archived HubSpot owners are resolved by name (so Leo Clougherty is not shown as a numeric owner id). A deal with no owner, or an owner HubSpot cannot find even in archived records, lands on an **Unassigned** tab.

Days in stage are whole days in UTC from `hs_v2_date_entered_current_stage`. The date in the report title is your computer’s local date.

## Design changes (playground copy)

Do not hand-edit a generated report you might share. Copy it, then experiment on the copy:

```
Copy-Item output\cro_stalled_report_YYYY-MM-DD.html output\cro_stalled_report_YYYY-MM-DD.ui-playground.html
```

Open the `.ui-playground.html` file in a browser, edit that file only, and lock the look there. When you are happy with it, change `stalled_deals_report.py` (the generator) to match, then re-run the script so the next dated file in `output/` is produced by the generator.
