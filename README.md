# O&G Credit Intelligence System

A Hermes Agent-powered intelligence system for tracking oil and gas companies (US/Canada), their credit facilities, and C-suite locations — built for an Energy Finance debt lending desk at a large bank.

## System Architecture

```
og-credit-intel/
├── data/
│   └── og_credit_intel.db       # SQLite database
├── scripts/
│   ├── create_db.py             # Database schema & init
│   ├── import_data.py           # Import research JSONs → DB
│   ├── monitor_news.py          # Cron: news & deal monitoring
│   └── export_report.py         # CSV exports & market report
├── output/
│   ├── research_largecap.json   # Research subagent output
│   ├── research_midcap.json     # Research subagent output
│   ├── research_canada_pe.json  # Research subagent output
│   ├── companies.csv            # Master company export
│   ├── credit_facilities.csv    # Credit facility export
│   └── executives.csv           # Executive locations export
├── reports/
│   └── market_report_*.md       # Generated market reports
└── README.md
```

## How to Run

### Initial Setup (one-time)
```bash
cd ~/Documents/og-credit-intel
python3 scripts/create_db.py          # Initialize database
python3 scripts/import_data.py         # Import research data
python3 scripts/export_report.py       # Generate reports & CSVs
```

### Research a New Segment
```bash
# Use delegate_task in Hermes with the appropriate prompt
# Example: dispatch a subagent to research "Permian Basin private operators"
# The subagent writes to output/research_*.json, then run:
python3 scripts/import_data.py
python3 scripts/export_report.py
```

### Generate Latest Reports
```bash
python3 scripts/export_report.py
# Outputs:
#   output/companies.csv         — Full company screen
#   output/credit_facilities.csv — All credit facilities
#   output/executives.csv        — C-suite locations
#   reports/market_report_*.md   — Full market report
```

## Cron Jobs (Hermes)

Three cron jobs run within Hermes for ongoing monitoring:

### 1. Weekly Credit Monitor
- **Schedule:** Every Monday 8:00 AM EST
- **Action:** Scans Google News RSS + SEC EDGAR for new O&G credit facility announcements
- **Delivery:** Back to this chat

### 2. Monthly Refresh
- **Schedule:** 1st of every month at 9:00 AM EST
- **Action:** Regenerates CSV exports and market report from current database
- **Delivery:** Back to this chat

### 3. News Alerts (Daily - optional)
- **Schedule:** Every weekday 7:00 AM EST
- **Action:** Quick scan for O&G debt deal headlines
- **Delivery:** Back to this chat

## Database Schema

### Companies
| Field | Description |
|-------|-------------|
| company_name | Legal name |
| ticker | Stock symbol (public) |
| headquarters_city/state | HQ location |
| country | US or CA |
| sector | upstream/midstream/downstream/integrated/oilfield_services |
| pe_backed / pe_firm_name | PE backing details |
| ebitda_most_recent | Most recent EBITDA |
| revenue_most_recent | Most recent revenue |
| total_debt | Total debt outstanding |
| credit_rating | S&P/Moody's/Fitch rating |

### Credit Facilities
| Field | Description |
|-------|-------------|
| facility_type | revolving_credit, term_loan_a, term_loan_b, etc. |
| facility_size | Size in $M |
| tenor_months | Duration in months |
| maturity_date | Expected maturity |
| pricing_base | SOFR, LIBOR, Base_Rate, etc. |
| margin_spread_bps | Margin over base in basis points |
| commitment_fee_bps | Undrawn commitment fee |
| lead_arrangers | Syndicate lead banks |
| syndication_status | active, amended, repaid, upsized, etc. |

## Data Sources
- **SEC EDGAR:** 10-K/8-K filings for public company credit agreements
- **Yahoo Finance / MarketWatch:** Financial data (EBITDA, revenue, debt)
- **Google News RSS:** Deal announcements, new facilities, amendments
- **Company Investor Relations pages:** Credit facility presentations
- **SEDAR:** Canadian company filings

## Usage Tips

1. **Deal Sourcing:** Check `reports/market_report_latest.md` for upcoming maturity dates — these represent refinancing opportunities
2. **Competitive Intelligence:** Monitor `output/credit_facilities.csv` for pricing trends across sectors
3. **PE-Backed Prospects:** The `pe_backed` flag identifies companies that may need additional debt capital for acquisitions
4. **Exec Locations:** Knowing where C-suites are based helps target relationship-building efforts
