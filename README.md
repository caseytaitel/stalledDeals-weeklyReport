# CRO Stalled Deals Report

A one-file HTML report for CRO 1:1s: every **open** Realm Prospects deal that has sat **30 or more days in its current stage**, from **10% Discovery through 90% Procurement** (Discovery, Qualification, Planning, Evaluation, Negotiation, Procurement). All reps, including direct and no-partner deals. Closed Won / Closed Lost / Closed No Opportunity / Deal Reg are out.

**Days in Stage** is the stall rule: the deal has not moved stage in 30+ days. Overview counts, row colors, and the 30–59 / 60–89 / 90–179 / 180+ bands all use that number.

**Days Open** is days since HubSpot create date — the age of the opportunity. That is the signal for deals that have been open too long with no movement, even if they changed stage more recently. It appears on rep tabs only, not on Overview.

This is separate from the Channel Ops weekly report. 

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

The script reads `HUBSPOT_TOKEN` from `.env.local` (never commit that file). HubSpot must be reachable. It writes `output/stalled_report_YYYY-MM-DD.html`. Running twice on the same calendar day overwrites that file.

If HubSpot rejects the token or the API is down, the script exits with an `ERROR:` line instead of writing a partial report.

## Sharing

Open the HTML in a browser, check Overview and each rep tab, then send the file yourself (email, Slack, etc.). Nothing posts automatically.

## What you should see

- Masthead: **Stalled Deals: N**. N is the company total on Overview and that rep’s count when you switch tabs (or click a name on Overview).
- Overview: one row per rep with total stalled and counts by days-in-stage band, plus an All footer.
- One tab per rep who has at least one stalled deal. 
- Rep tabs group deals by close date, empty groups omitted: **Past close date**, previous quarters of the current fiscal year, then current FY by quarter (for example **Q3**, **Q4**, **FY28**), then next FY. Fiscal year starts Feb 1 (Q1 Feb–Apr, Q2 May–Jul, Q3 Aug–Oct, Q4 Nov–Jan). A blank HubSpot close date gets its own **No close date** group.
- Columns: Deal Name (HubSpot record link), Deal Stage, Days Open, Days in Stage, Close Date. Days Open is a plain number (or — if HubSpot has no create date). It does not change inclusion, sort, or color.
- Colors: 30–59 yellow, 60–89 orange, 90–179 dark orange, 180+ red, all from days in stage. Nothing under 30 days in stage is listed. Close date is not a pull filter; it only affects grouping on the rep tabs.

Archived HubSpot owners are resolved by name (so Leo Clougherty is not shown as a numeric owner id). A deal with no owner, or an owner HubSpot cannot find even in archived records, lands on an **Unassigned** tab.

Days in stage are whole days in UTC from `hs_v2_date_entered_current_stage`. Days Open is whole days in UTC from HubSpot `createdate`. The date in the report title is your computer’s local date.

## Design changes (playground copy)

Do not hand-edit a generated report you might share. Copy it, then experiment on the copy:

```
Copy-Item output\stalled_report_YYYY-MM-DD.html output\stalled_report_YYYY-MM-DD.ui-playground.html
```

Open the `.ui-playground.html` file in a browser, edit that file only, and lock the look there. When you are happy with it, change `stalled_deals_report.py` (the generator) to match, then re-run the script so the next dated file in `output/` is produced by the generator.
