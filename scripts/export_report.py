#!/usr/bin/env python3
"""
O&G Credit Intelligence — Report & Export Generator
Generates CSV exports and formatted reports for banking use.
"""
import csv
import json
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'og_credit_intel.db')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def export_company_csv():
    """Export master company list with credit facility summary."""
    conn = get_conn()
    
    rows = conn.execute("""
        SELECT 
            c.company_name,
            c.ticker,
            c.headquarters_city,
            c.headquarters_state_province,
            c.country,
            c.sector,
            c.subsector,
            c.public_private,
            CASE WHEN c.pe_backed = 1 THEN c.pe_firm_name ELSE NULL END as pe_backing,
            c.ebitda_most_recent,
            c.ebitda_fiscal_year,
            c.revenue_most_recent,
            c.total_debt,
            c.market_cap,
            c.enterprise_value,
            c.credit_rating,
            c.rating_agency
        FROM companies c
        ORDER BY c.ebitda_most_recent DESC NULLS LAST
    """).fetchall()
    
    outpath = os.path.join(OUTPUT_DIR, 'companies.csv')
    with open(outpath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Company Name', 'Ticker', 'HQ City', 'HQ State/Prov', 'Country',
                     'Sector', 'Subsector', 'Public/Private', 'PE Backing',
                     'EBITDA ($M)', 'EBITDA Year', 'Revenue ($M)', 'Total Debt ($M)',
                     'Market Cap ($M)', 'Enterprise Value ($M)', 'Credit Rating', 'Rating Agency'])
        for r in rows:
            w.writerow([
                r['company_name'], r['ticker'], r['headquarters_city'],
                r['headquarters_state_province'], r['country'],
                r['sector'], r['subsector'], r['public_private'],
                r['pe_backing'],
                f"${r['ebitda_most_recent']:,.0f}" if r['ebitda_most_recent'] else '',
                r['ebitda_fiscal_year'],
                f"${r['revenue_most_recent']:,.0f}" if r['revenue_most_recent'] else '',
                f"${r['total_debt']:,.0f}" if r['total_debt'] else '',
                f"${r['market_cap']:,.0f}" if r['market_cap'] else '',
                f"${r['enterprise_value']:,.0f}" if r['enterprise_value'] else '',
                r['credit_rating'], r['rating_agency'],
            ])
    print(f"Exported {len(rows)} companies → {outpath}")
    conn.close()

def export_facilities_csv():
    """Export all credit facilities with company context."""
    conn = get_conn()
    
    rows = conn.execute("""
        SELECT 
            c.company_name,
            c.ticker,
            c.sector,
            cf.facility_type,
            cf.facility_name,
            cf.facility_size,
            cf.tenor_months,
            cf.maturity_date,
            cf.pricing_base,
            cf.margin_spread_bps,
            cf.commitment_fee_bps,
            cf.drawn_amount,
            cf.lead_arrangers,
            cf.administrative_agent,
            cf.syndication_status,
            cf.source
        FROM credit_facilities cf
        JOIN companies c ON cf.company_id = c.id
        ORDER BY cf.maturity_date ASC NULLS LAST
    """).fetchall()
    
    outpath = os.path.join(OUTPUT_DIR, 'credit_facilities.csv')
    with open(outpath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Company', 'Ticker', 'Sector', 'Facility Type', 'Facility Name',
                     'Size ($M)', 'Tenor (Months)', 'Maturity Date',
                     'Pricing Base', 'Margin (bps)', 'Commitment Fee (bps)',
                     'Drawn ($M)', 'Lead Arrangers', 'Admin Agent',
                     'Status', 'Source'])
        for r in rows:
            w.writerow([
                r['company_name'], r['ticker'], r['sector'],
                r['facility_type'], r['facility_name'],
                f"${r['facility_size']:,.0f}M" if r['facility_size'] else '',
                r['tenor_months'], r['maturity_date'],
                r['pricing_base'],
                f"{r['margin_spread_bps']} bps" if r['margin_spread_bps'] else '',
                f"{r['commitment_fee_bps']} bps" if r['commitment_fee_bps'] else '',
                f"${r['drawn_amount']:,.0f}M" if r['drawn_amount'] else '',
                r['lead_arrangers'], r['administrative_agent'],
                r['syndication_status'], r['source'],
            ])
    print(f"Exported {len(rows)} facilities → {outpath}")
    conn.close()

def export_executives_csv():
    """Export all C-suite executives with office locations."""
    conn = get_conn()
    
    rows = conn.execute("""
        SELECT 
            c.company_name,
            e.name,
            e.title,
            e.office_city,
            e.office_state_province,
            e.office_country
        FROM executives e
        JOIN companies c ON e.company_id = c.id
        ORDER BY c.company_name, e.title
    """).fetchall()
    
    outpath = os.path.join(OUTPUT_DIR, 'executives.csv')
    with open(outpath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Company', 'Name', 'Title', 'Office City', 'Office State/Prov', 'Office Country'])
        for r in rows:
            w.writerow([
                r['company_name'], r['name'], r['title'],
                r['office_city'], r['office_state_province'], r['office_country'],
            ])
    print(f"Exported {len(rows)} executives → {outpath}")
    conn.close()

def generate_markdown_report():
    """Generate a comprehensive banking-focused market report."""
    conn = get_conn()
    
    # Summary stats
    total_companies = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    pe_count = conn.execute("SELECT COUNT(*) FROM companies WHERE pe_backed=1").fetchone()[0]
    by_sector = conn.execute("SELECT sector, COUNT(*) FROM companies GROUP BY sector").fetchall()
    by_country = conn.execute("SELECT country, COUNT(*) FROM companies GROUP BY country").fetchall()
    
    total_facilities = conn.execute("SELECT COUNT(*) FROM credit_facilities").fetchone()[0]
    active_facilities = conn.execute("""
        SELECT COUNT(*) FROM credit_facilities 
        WHERE syndication_status IN ('active', 'amended', 'upsized', 'extended')
    """).fetchone()[0]
    
    upcoming_maturities = conn.execute("""
        SELECT c.company_name, cf.facility_name, cf.facility_size, cf.maturity_date, cf.margin_spread_bps
        FROM credit_facilities cf
        JOIN companies c ON cf.company_id = c.id
        WHERE cf.maturity_date >= date('now')
        ORDER BY cf.maturity_date ASC
        LIMIT 20
    """).fetchall()
    
    # Top by EBITDA
    top_ebitda = conn.execute("""
        SELECT company_name, ticker, ebitda_most_recent, ebitda_fiscal_year, sector
        FROM companies
        WHERE ebitda_most_recent IS NOT NULL
        ORDER BY ebitda_most_recent DESC
        LIMIT 15
    """).fetchall()
    
    # Build report
    now = datetime.now().strftime('%B %d, %Y')
    report = f"""# O&G Credit Intelligence — Market Report
**Generated:** {now}
**Client:** Energy Finance — Large Bank Debt Lending & Syndicated Loans

---

## Coverage Summary

| Metric | Count |
|--------|-------|
| Total Companies Tracked | {total_companies} |
| PE-Backed Companies | {pe_count} |
| Total Credit Facilities | {total_facilities} |
| Active Facilities | {active_facilities} |

### By Sector
"""
    for sector, cnt in by_sector:
        report += f"| {sector.title()} | {cnt} |\n"
    
    report += "\n### By Country\n"
    for country, cnt in by_country:
        label = "United States" if country == 'US' else "Canada"
        report += f"| {label} | {cnt} |\n"
    
    # Top by EBITDA
    report += "\n---\n## Top O&G Companies by EBITDA\n\n"
    report += "| Company | Ticker | Sector | EBITDA | Year |\n"
    report += "|---------|--------|--------|--------|------|\n"
    for r in top_ebitda:
        ebitda_str = f"${r['ebitda_most_recent']:,.0f}" if r['ebitda_most_recent'] else 'N/A'
        report += f"| {r['company_name']} | {r['ticker'] or ''} | {r['sector']} | {ebitda_str} | {r['ebitda_fiscal_year'] or ''} |\n"
    
    # Upcoming maturities
    report += "\n---\n## Upcoming Credit Facility Maturities\n\n"
    report += "| Company | Facility | Size ($M) | Maturity | Pricing (bps) |\n"
    report += "|---------|----------|-----------|----------|---------------|\n"
    for r in upcoming_maturities:
        report += f"| {r['company_name']} | {r['facility_name']} | ${r['facility_size']:,.0f}M | {r['maturity_date'] or 'TBD'} | {r['margin_spread_bps'] or 'N/A'} |\n"
    
    # All companies with facilities detail
    companies_detail = conn.execute("""
        SELECT c.id, c.company_name, c.ticker, c.headquarters_city, 
               c.headquarters_state_province, c.country, c.sector, 
               c.ebitda_most_recent, c.ebitda_fiscal_year, c.pe_backed,
               c.pe_firm_name, c.credit_rating
        FROM companies c
        ORDER BY c.ebitda_most_recent DESC NULLS LAST
    """).fetchall()
    
    report += "\n---\n## Company Profiles — Full Detail\n\n"
    
    for comp in companies_detail:
        facilities = conn.execute("""
            SELECT * FROM credit_facilities WHERE company_id = ?
        """, (comp['id'],)).fetchall()
        
        execs = conn.execute("""
            SELECT * FROM executives WHERE company_id = ?
        """, (comp['id'],)).fetchall()
        
        pe_note = f" (PE-backed: {comp['pe_firm_name']})" if comp['pe_backed'] and comp['pe_firm_name'] else ""
        ebitda_str = f"${comp['ebitda_most_recent']:,.0f}" if comp['ebitda_most_recent'] else 'N/A'
        
        report += f"""### {comp['company_name']}{' (' + comp['ticker'] + ')' if comp['ticker'] else ''}
**Sector:** {comp['sector']} | **HQ:** {comp['headquarters_city']}, {comp['headquarters_state_province']}, {comp['country']}
**EBITDA:** {ebitda_str} ({comp['ebitda_fiscal_year'] or 'N/A'}){pe_note}
**Credit Rating:** {comp['credit_rating'] or 'N/A'}
"""
        if facilities:
            report += "\n**Credit Facilities:**\n"
            report += "| Type | Name | Size ($M) | Tenor (mo) | Maturity | Pricing | Margin (bps) | Status |\n"
            report += "|------|------|-----------|------------|----------|---------|-------------|--------|\n"
            for f in facilities:
                pricing = f['pricing_base'] or ''
                margin = f"{f['margin_spread_bps']} bps" if f['margin_spread_bps'] else ''
                report += f"| {f['facility_type']} | {f['facility_name'] or ''} | ${f['facility_size']:,.0f}M | {f['tenor_months'] or ''} | {f['maturity_date'] or ''} | {pricing} | {margin} | {f['syndication_status']} |\n"
        
        if execs:
            report += "\n**C-Suite Executives:**\n"
            for e in execs:
                loc = f"{e['office_city'] or ''}, {e['office_state_province'] or ''}" if e['office_city'] else 'N/A'
                report += f"- {e['name']} — {e['title']} ({loc})\n"
        
        report += "\n---\n"
    
    # Save
    os.makedirs(REPORTS_DIR, exist_ok=True)
    outpath = os.path.join(REPORTS_DIR, f'market_report_{datetime.now().strftime("%Y%m%d")}.md')
    with open(outpath, 'w') as f:
        f.write(report)
    
    print(f"Report generated → {outpath}")
    conn.close()
    return outpath

def export_all():
    """Run all exports."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    export_company_csv()
    export_facilities_csv()
    export_executives_csv()
    report_path = generate_markdown_report()
    print(f"\nAll exports complete. Reports in {REPORTS_DIR}/")
    return report_path

if __name__ == '__main__':
    export_all()
