#!/usr/bin/env python3
"""
O&G Credit Intelligence — SEC EDGAR Credit Agreement Extractor
Searches and extracts credit agreement details from SEC filings (8-K, 10-K, 10-Q).
Designed for public O&G companies. Extracts:
  - Facility size & type
  - Maturity date
  - Pricing (base rate + spread)
  - Covenants summary
  - Lead arrangers / administrative agent
"""
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# SEC EDGAR CIK codes for major O&G companies
KNOWN_CIKS = {
    'XOM': '0000034088',  'CVX': '0000093410',  'COP': '0001163165',
    'EOG': '0000821214',  'DVN': '0001090012',  'FANG': '0001539838',
    'CTRA': '0000858470', 'EQT': '0000033213',  'CHK': '0001628973',
    'EPD': '0001061219',  'ET': '0001276187',   'KMI': '0001506307',
    'WMB': '0000107263',  'OKE': '0001039684',   'MPLX': '0001802769',
    'TRGP': '0001380770', 'PSX': '0001534701',   'VLO': '0001035002',
    'MPC': '0001510295',  'HAL': '0000045012',   'SLB': '0000087347',
    'BKR': '0001701603',  'NOV': '0001021860',
}

def search_sec_cik(ticker):
    """Search SEC for a CIK number by ticker."""
    try:
        url = f"https://efts.sec.gov/LATEST/search-index?q={urllib.parse.quote(ticker)}+oil+gas&dateRange=all&category=form-cat1"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'OGCreditIntel/1.0 (research; vance.cole@bank.com)'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        hits = data.get('hits', {}).get('hits', [])
        for hit in hits[:5]:
            source = hit.get('_source', {})
            cik = source.get('cik')
            name = source.get('display_names', [''])[0]
            if cik and ticker.upper() in name.upper():
                return cik.zfill(10)
        return None
    except Exception as e:
        print(f"[WARN] CIK search failed for {ticker}: {e}", file=sys.stderr)
        return None

def get_company_filings(cik, form_type='8-K', count=20):
    """Get recent filings for a company by form type."""
    filings = []
    try:
        url = f"https://efts.sec.gov/LATEST/search-index?q=cik:{cik}+form-type:{form_type}&dateRange=all&category=form-cat1&pageSize={count}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'OGCreditIntel/1.0 (research; vance.cole@bank.com)'
        })
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        for hit in data.get('hits', {}).get('hits', []):
            source = hit.get('_source', {})
            if source.get('form_type') == form_type:
                filings.append({
                    'accession': source.get('accession_number', ''),
                    'filed_date': source.get('filed_date', ''),
                    'description': source.get('description', ''),
                    'form_type': source.get('form_type', ''),
                    'cik': cik,
                })
        return filings
    except Exception as e:
        print(f"[WARN] Filing search failed for CIK {cik}: {e}", file=sys.stderr)
        return []

def extract_filing_text(cik, accession):
    """Extract text from an SEC filing."""
    try:
        # SEC EDGAR document URL format
        # Remove dashes from accession for directory path
        clean_acc = accession.replace('-', '')
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{clean_acc}/{accession}.txt"
        
        req = urllib.request.Request(url, headers={
            'User-Agent': 'OGCreditIntel/1.0 (research; vance.cole@bank.com)',
            'Accept': 'text/html,application/xhtml+xml',
        })
        resp = urllib.request.urlopen(req, timeout=30)
        text = resp.read().decode('utf-8', errors='replace')
        return text
    except Exception as e:
        print(f"  [WARN] Filing text extraction failed: {e}", file=sys.stderr)
        return None

def parse_credit_agreement(text):
    """
    Parse a credit agreement filing to extract key terms.
    Looks for: facility size, maturity, interest rate/pricing, arrangers, covenants.
    """
    if not text:
        return None
    
    result = {}
    
    # Facility size
    size_patterns = [
        r'facility\s+(in\s+)?(the\s+)?(aggregate\s+)?(principal\s+)?amount\s+(of\s+)?[\$]?\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?',
        r'[\$]\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)?\s+(?:revolving|term\s+loan|credit\s+facility)',
        r'commitment[s]?\s+(of\s+)?[\$]\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion)',
        r'aggregate\s+(?:commitments|principal)\s+(?:amount\s+)?(?:of\s+)?[\$]\s*([\d,]+(?:\.\d+)?)',
    ]
    for pat in size_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # Find the first numeric group
            for g in m.groups():
                if g and re.match(r'[\d,]+(?:\.\d+)?$', g.replace(',', '')):
                    try:
                        val = float(g.replace(',', ''))
                        # Check if billion
                        context = text[max(0, m.start()-50):m.end()+50].lower()
                        if 'billion' in context:
                            result['facility_size'] = val * 1000  # Convert to $M
                        else:
                            result['facility_size'] = val
                        break
                    except ValueError:
                        continue
            if 'facility_size' in result:
                break
    
    # Maturity
    maturity_patterns = [
        r'maturity\s+date[:\s]+([A-Z][a-z]+ \d{1,2},?\s*\d{4})',
        r'(?:mature[s]?\s+on|maturing\s+|terminat(?:e|ing)\s+on)\s+([A-Z][a-z]+ \d{1,2},?\s*\d{4})',
        r'([A-Z][a-z]+ \d{1,2},?\s*\d{4})\s*(?:and\s+will\s+)?(?:mature|terminat)',
    ]
    for pat in maturity_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result['maturity_date'] = m.group(1).strip()
            break
    
    # If maturity not found, try to find "5-year" or "364-day" etc
    if 'maturity_date' not in result:
        tenor_match = re.search(r'(\d+)[- ](year|month|day)\s*(?:\w+\s+)?(?:maturity|facility|term)', text, re.IGNORECASE)
        if tenor_match:
            result['tenor'] = f"{tenor_match.group(1)}-{tenor_match.group(2)}"
    
    # Pricing - SOFR / LIBOR spreads
    pricing_patterns = [
        r'(?:SOFR|LIBOR|Base\s+Rate|ABR|prime\s+rate)\s*(?:plus|and|rate\s+of|margin\s+of)?\s*([\d.]+)\s*%',
        r'(?:applicable\s+)?margin\s+(?:for\s+)?(?:SOFR|LIBOR|eurodollar|ABR)[-\s]?(?:loans|advances)?[:\s]+([\d.]+)\s*%',
        r'(?:priced\s+at|at\s+)\s*(?:SOFR|LIBOR)\s*(?:\+|\+?\s*)\s*([\d.]+)\s*%',
        r'(?:spread|margin)\s+of\s+([\d.]+)\s*%',
    ]
    for pat in pricing_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                pct = float(m.group(1))
                result['margin_bps'] = int(pct * 100)  # Convert to bps
                result['pricing_base'] = 'SOFR' if 'SOFR' in text[m.start()-30:m.end()+30].upper() else 'LIBOR'
                break
            except ValueError:
                continue
    
    # Also look for bps-style pricing
    if 'margin_bps' not in result:
        bps_match = re.search(r'(\d+)\s*basis\s+points\s*(?:over|above|plus)\s*(SOFR|LIBOR|ABR|base\s+rate)', text, re.IGNORECASE)
        if bps_match:
            result['margin_bps'] = int(bps_match.group(1))
            result['pricing_base'] = bps_match.group(2).upper().replace(' ', '_')
    
    # Lead arrangers / administrative agent
    agent_patterns = [
        r'administrative\s+agent[:\s]+([A-Z][A-Za-z\s]+(?:Inc\.?|Corp\.?|LLC|LLP|L\.P\.|NA)?)',
        r'(?:lead\s+)?arranger[s]?[:\s]+([A-Z][A-Za-z\s]+(?:Inc\.?|Corp\.?|LLC|LLP|Holding)?)',
    ]
    for pat in agent_patterns:
        m = re.search(pat, text)
        if m:
            result['admin_agent'] = m.group(1).strip()
            break
    
    # Commitment fee
    fee_match = re.search(r'commitment\s+fee\s+(?:of\s+)?([\d.]+)\s*%', text, re.IGNORECASE)
    if fee_match:
        try:
            result['commitment_fee_bps'] = int(float(fee_match.group(1)) * 100)
        except ValueError:
            pass
    
    # Facility type
    if re.search(r'revolving\s+credit', text, re.IGNORECASE):
        result['facility_type'] = 'revolving_credit'
    elif re.search(r'term\s+loan\s+[Bb]', text, re.IGNORECASE):
        result['facility_type'] = 'term_loan_b'
    elif re.search(r'term\s+loan\s+[Aa]', text, re.IGNORECASE):
        result['facility_type'] = 'term_loan_a'
    elif re.search(r'term\s+loan', text, re.IGNORECASE):
        result['facility_type'] = 'term_loan'
    elif re.search(r'delayed\s+draw', text, re.IGNORECASE):
        result['facility_type'] = 'delayed_draw'
    elif re.search(r'bridge\s+loan|bridge\s+facility', text, re.IGNORECASE):
        result['facility_type'] = 'bridge_loan'
    
    # Extract facility name from the first paragraph
    name_match = re.search(r'(?:this\s+)?(?:Credit Agreement|Revolving Credit Facility|Term Loan Agreement|Credit Facility)\s+[^.]{20,100}[.]', text)
    if name_match:
        result['facility_name'] = name_match.group(0).strip()[:200]
    
    return result

def extract_credit_facilities(ticker, cik=None, max_filings=10):
    """Full pipeline: find filings → extract credit agreement terms."""
    if not cik:
        cik = KNOWN_CIKS.get(ticker.upper())
    if not cik:
        print(f"Looking up CIK for {ticker}...")
        cik = search_sec_cik(ticker)
        if not cik:
            print(f"  ✗ Could not find CIK for {ticker}")
            return None
    
    cik = cik.zfill(10)
    print(f"\n{'='*60}")
    print(f"Extracting credit facilities for {ticker} (CIK: {cik})")
    print(f"{'='*60}")
    
    # Search for credit agreement filings
    all_filings = []
    for form in ['8-K', '10-K', '10-Q']:
        filings = get_company_filings(cik, form, count=max_filings)
        all_filings.extend(filings)
    
    # Deduplicate by accession
    seen = set()
    unique = []
    for f in all_filings:
        if f['accession'] not in seen:
            seen.add(f['accession'])
            unique.append(f)
    
    # Sort by date (newest first)
    unique.sort(key=lambda x: x.get('filed_date', ''), reverse=True)
    
    results = []
    for filing in unique[:max_filings]:
        desc = (filing.get('description') or '').lower()
        # Only process filings that mention credit, facility, or debt
        if not any(kw in desc for kw in ['credit', 'facility', 'debt', 'loan', 'offering']):
            continue
        
        print(f"\n  Filing: {filing['form_type']} — {filing['filed_date']}")
        print(f"  Description: {filing['description'][:120] if filing.get('description') else 'N/A'}...")
        
        text = extract_filing_text(cik, filing['accession'])
        if text:
            parsed = parse_credit_agreement(text)
            if parsed and parsed.get('facility_size'):
                parsed['ticker'] = ticker
                parsed['cik'] = cik
                parsed['filing_type'] = filing['form_type']
                parsed['filing_date'] = filing['filed_date']
                parsed['accession'] = filing['accession']
                results.append(parsed)
                print(f"  ✓ Found facility: ${parsed.get('facility_size', '?'):,.0f}M — "
                      f"{parsed.get('facility_type', '?')} — "
                      f"margin: {parsed.get('margin_bps', '?')} bps")
            else:
                print(f"  - No credit facility details found in this filing")
        
        time.sleep(0.5)  # SEC rate limiting
    
    return results

def batch_extract(tickers):
    """Run extraction for multiple tickers."""
    all_results = {}
    for ticker in tickers:
        try:
            results = extract_credit_facilities(ticker)
            if results:
                all_results[ticker] = results
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Failed for {ticker}: {e}", file=sys.stderr)
    
    # Save all results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, 'sec_credit_extracts.json')
    with open(outpath, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Batch extract complete: {len(all_results)} companies with data")
    print(f"Results saved to {outpath}")
    
    return all_results

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 sec_extractor.py <ticker>       # Single company")
        print("  python3 sec_extractor.py batch          # All known companies")
        print("  python3 sec_extractor.py XOM CVX COP    # Specific companies")
        sys.exit(1)
    
    if sys.argv[1] == 'batch':
        tickers = list(KNOWN_CIKS.keys())
        batch_extract(tickers)
    else:
        tickers = sys.argv[1:]
        for t in tickers:
            results = extract_credit_facilities(t.upper())
            if results:
                print(json.dumps(results, indent=2))
            time.sleep(1)
