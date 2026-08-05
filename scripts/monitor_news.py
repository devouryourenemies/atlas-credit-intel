#!/usr/bin/env python3
"""
O&G Credit Intelligence — News & Deal Monitor
Searches for new O&G debt facilities, amendments, refinancings, and credit rating changes.
Designed to run as a Hermes cron job.
"""
import json
import os
import sys
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from xml.etree import ElementTree

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

def search_google_news(query, max_results=10):
    """Search Google News RSS for O&G deal news."""
    results = []
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        resp = urllib.request.urlopen(req, timeout=15)
        tree = ElementTree.fromstring(resp.read())
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for item in tree.findall('.//item')[:max_results]:
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pubdate = item.findtext('pubDate', '')
            source = item.findtext('source', '')
            results.append({
                'title': title.strip(),
                'url': link.strip(),
                'source': source.strip(),
                'published': pubdate.strip(),
            })
    except Exception as e:
        print(f"[WARN] Google News RSS failed: {e}", file=sys.stderr)
    return results

def search_sec_edgar_recent(query="credit agreement", days_back=7):
    """Search SEC EDGAR for recent O&G credit agreement filings."""
    results = []
    try:
        from datetime import datetime as dt
        start_date = (dt.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        search_url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q={urllib.parse.quote(query)}+oil+gas"
            f"&dateRange=custom&startdt={start_date}&enddt={dt.now().strftime('%Y-%m-%d')}"
            f"&category=form-cat1"
        )
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'OGCreditIntel/1.0 (research)',
            'Accept': 'application/json',
        })
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        
        for hit in data.get('hits', {}).get('hits', []):
            source = hit.get('_source', {})
            results.append({
                'title': source.get('display_names', [''])[0],
                'url': f"https://www.sec.gov{source.get('_id', '')}",
                'form_type': source.get('form_type', ''),
                'filed_date': source.get('filed_date', ''),
                'company': source.get('display_names', [''])[0] if source.get('display_names') else '',
            })
    except Exception as e:
        print(f"[WARN] SEC EDGAR search failed: {e}", file=sys.stderr)
    return results

def check_new_activity():
    """Main monitoring function. Returns dict of findings."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Search for new credit facility deals
    deal_queries = [
        '"credit facility" oil gas "billion"',
        '"syndicated loan" oil gas',
        '"revolving credit" oil gas',
        '"term loan" oil gas',
        '"credit agreement" oil gas 8-K',
        '"upsized" credit facility oil gas',
    ]
    
    all_deals = []
    for query in deal_queries:
        results = search_google_news(query, max_results=5)
        all_deals.extend(results)
    
    # Search for PE-backed O&G deals
    pe_queries = [
        '"private equity" oil gas "credit facility"',
        'EnCap "credit facility"',
        'Quantum Energy "credit facility"',
        'Blackstone oil gas debt',
    ]
    
    for query in pe_queries:
        results = search_google_news(query, max_results=3)
        all_deals.extend(results)
    
    # Deduplicate
    seen = set()
    unique_deals = []
    for d in all_deals:
        key = d['title'][:80]
        if key not in seen:
            seen.add(key)
            unique_deals.append(d)
    
    result = {
        'run_timestamp': now,
        'new_deals_found': len(unique_deals),
        'deals': unique_deals,
    }
    
    # Write output for cron delivery
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    outpath = os.path.join(OUTPUT_DIR, 'latest_monitor_results.json')
    with open(outpath, 'w') as f:
        json.dump(result, f, indent=2)
    
    # Generate human-readable summary
    if unique_deals:
        summary = f"## O&G Credit Monitor — {datetime.now().strftime('%b %d, %Y')}\n\n"
        summary += f"Found {len(unique_deals)} new items:\n\n"
        for deal in unique_deals[:10]:
            summary += f"• **{deal['title']}**\n"
            summary += f"  {deal.get('source', '')} | {deal.get('url', '')}\n"
        print(summary)
    else:
        print(f"No new O&G credit facility news found as of {now}")
    
    return result

if __name__ == '__main__':
    check_new_activity()
