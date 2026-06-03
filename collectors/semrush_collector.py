"""
Scout — Semrush Collector
Pulls keyword, traffic, and competitor data from Semrush API
and stores it in Supabase.
"""

import os
import requests
from datetime import datetime, date
from supabase import create_client, Client

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SEMRUSH_API_KEY = os.environ.get("SEMRUSH_API_KEY")

SEMRUSH_BASE = "https://api.semrush.com"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Semrush API Helpers ───────────────────────────────────────────────────────

def get_domain_overview(domain: str) -> dict:
    """Get traffic and keyword overview for a domain."""
    params = {
        "type": "domain_ranks",
        "key": SEMRUSH_API_KEY,
        "domain": domain,
        "database": "us",
        "export_columns": "Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
    }
    resp = requests.get(SEMRUSH_BASE, params=params)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    if len(lines) < 2:
        return {}

    headers = lines[0].split(";")
    values = lines[1].split(";")
    return dict(zip(headers, values))


def get_organic_keywords(domain: str, limit: int = 50, brand_terms: list = None) -> list[dict]:
    """Get top organic keywords for a domain, filtering brand terms if provided."""
    params = {
        "type": "domain_organic",
        "key": SEMRUSH_API_KEY,
        "domain": domain,
        "database": "us",
        "display_limit": limit,
        "export_columns": "Ph,Po,Pp,Pd,Nq,Cp,Ur,Tr,Tc,Co,Nr,Td",
        "display_sort": "tr_desc",
    }
    resp = requests.get(SEMRUSH_BASE, params=params)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    if len(lines) < 2:
        return []

    headers = lines[0].split(";")
    keywords = [dict(zip(headers, line.split(";"))) for line in lines[1:] if line]

    # Filter brand terms if provided
    if brand_terms:
        brand_terms_lower = [t.lower() for t in brand_terms]
        keywords = [
            kw for kw in keywords
            if not any(bt in kw.get("Ph", "").lower() for bt in brand_terms_lower)
        ]

    return keywords


def get_paid_keywords(domain: str, limit: int = 100) -> list[dict]:
    """Get paid search keywords for a domain."""
    params = {
        "type": "domain_adwords",
        "key": SEMRUSH_API_KEY,
        "domain": domain,
        "database": "us",
        "display_limit": limit,
        "export_columns": "Ph,Po,Pp,Pd,Ab,Nq,Cp,Tr,Tc,Co,Nr,Td",
        "display_sort": "tr_desc",
    }
    resp = requests.get(SEMRUSH_BASE, params=params)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    if len(lines) < 2:
        return []

    headers = lines[0].split(";")
    return [dict(zip(headers, line.split(";"))) for line in lines[1:] if line]


def get_keyword_positions(domain: str, keywords: list[str], campaign_id: str = "29906708") -> list[dict]:
    """
    Get keyword positions using Position Tracking API.
    One API call per domain — far fewer units than phrase_organic or domain_organic.
    """
    try:
        params = {
            "type": "tracking_position_all",
            "key": SEMRUSH_API_KEY,
            "campaign_id": campaign_id,
            "domain": domain,
            "database": "us",
            "export_columns": "Ph,Po,Nq,Ur",
        }
        resp = requests.get("https://api.semrush.com/analytics/v1/", params=params)
        resp.raise_for_status()

        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            return [{"keyword": kw, "position": None, "volume": None, "url": None, "domain": domain} for kw in keywords]

        headers = lines[0].split(";")
        all_rows = [dict(zip(headers, line.split(";"))) for line in lines[1:] if line]

        # Build lookup by keyword
        kw_map = {row.get("Ph", "").lower(): row for row in all_rows}

        results = []
        for kw in keywords:
            match = kw_map.get(kw.lower())
            if match:
                pos = match.get("Po", "")
                vol = match.get("Nq", "")
                results.append({
                    "keyword": kw,
                    "position": int(pos) if str(pos).isdigit() else None,
                    "volume": int(vol) if str(vol).isdigit() else None,
                    "url": match.get("Ur"),
                    "domain": domain,
                })
            else:
                results.append({"keyword": kw, "position": None, "volume": None, "url": None, "domain": domain})

        return results

    except Exception as e:
        print(f"[semrush]   ERROR position tracking for {domain}: {e}")
        return [{"keyword": kw, "position": None, "volume": None, "url": None, "domain": domain} for kw in keywords]


# ── Supabase Storage ──────────────────────────────────────────────────────────

def get_client_id(slug: str) -> str | None:
    result = supabase.table("clients").select("id").eq("slug", slug).single().execute()
    return result.data["id"] if result.data else None


def get_competitor_id(client_id: str, domain: str) -> str | None:
    result = (
        supabase.table("competitors")
        .select("id")
        .eq("client_id", client_id)
        .eq("domain", domain)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None


def save_signal(client_id: str, competitor_id: str | None, source: str, signal_type: str, data: dict):
    supabase.table("signals").insert({
        "client_id": client_id,
        "competitor_id": competitor_id,
        "source": source,
        "signal_type": signal_type,
        "data": data,
        "collected_at": datetime.utcnow().isoformat(),
    }).execute()


# ── Main Collection Flow ──────────────────────────────────────────────────────

def collect_for_client(client_slug: str):
    """Run full Semrush collection for a client and all their competitors."""
    print(f"[semrush] Starting collection for: {client_slug}")

    client_id = get_client_id(client_slug)
    if not client_id:
        print(f"[semrush] ERROR: Client '{client_slug}' not found in Supabase")
        return

    # Load client config
    result = supabase.table("clients").select("config").eq("id", client_id).single().execute()
    config = result.data.get("config", {})
    client_domain = config.get("domain")
    competitors = config.get("competitors", [])
    tracked_keywords = config.get("tracked_keywords", [])

    if not client_domain:
        print(f"[semrush] ERROR: No domain in config for '{client_slug}'")
        return

    # ── Client own domain overview ────────────────────────────────────────────
    print(f"[semrush]   Collecting client domain: {client_domain}")
    try:
        overview = get_domain_overview(client_domain)
        save_signal(client_id, None, "semrush", "client_domain_overview", overview)
    except Exception as e:
        print(f"[semrush]   ERROR client domain_overview: {e}")

    # ── Client keyword positions for tracked keywords ─────────────────────────
    if tracked_keywords:
        print(f"[semrush]   Collecting client keyword positions for {len(tracked_keywords)} tracked terms")
        try:
            client_positions = get_keyword_positions(client_domain, tracked_keywords)
            save_signal(client_id, None, "semrush", "client_keyword_positions", {
                "domain": client_domain,
                "keywords": client_positions,
            })
        except Exception as e:
            print(f"[semrush]   ERROR client keyword positions: {e}")

    # ── Competitor data ───────────────────────────────────────────────────────
    for comp in competitors:
        comp_domain = comp.get("domain")
        comp_name = comp.get("name")
        brand_terms = comp.get("brand_terms", [])
        comp_id = get_competitor_id(client_id, comp_domain)

        if not comp_id:
            print(f"[semrush] WARNING: Competitor '{comp_domain}' not in DB, skipping")
            continue

        print(f"[semrush]   Collecting: {comp_domain}")

        # Domain overview
        try:
            overview = get_domain_overview(comp_domain)
            save_signal(client_id, comp_id, "semrush", "domain_overview", overview)
        except Exception as e:
            print(f"[semrush]   ERROR domain_overview: {e}")

        # Organic keywords — filtered by brand terms
        try:
            organic = get_organic_keywords(comp_domain, brand_terms=brand_terms)
            filtered_count = len(organic)
            print(f"[semrush]   {comp_name}: {filtered_count} organic keywords after brand filter")
            save_signal(client_id, comp_id, "semrush", "organic_keywords", {"keywords": organic})
        except Exception as e:
            print(f"[semrush]   ERROR organic_keywords: {e}")

        # Paid keywords — cap raised to 100
        try:
            paid = get_paid_keywords(comp_domain)
            save_signal(client_id, comp_id, "semrush", "paid_keywords", {"keywords": paid})
        except Exception as e:
            print(f"[semrush]   ERROR paid_keywords: {e}")

        # Competitor keyword positions for tracked keywords
        if tracked_keywords:
            try:
                comp_positions = get_keyword_positions(comp_domain, tracked_keywords)
                save_signal(client_id, comp_id, "semrush", "tracked_keyword_positions", {
                    "domain": comp_domain,
                    "competitor": comp_name,
                    "keywords": comp_positions,
                })
            except Exception as e:
                print(f"[semrush]   ERROR tracked keyword positions: {e}")

    print(f"[semrush] Done: {client_slug}")


# ── Manual CSV Import (fallback when API units are low) ──────────────────────

def import_semrush_csv(client_slug: str, competitor_domain: str, csv_path: str, signal_type: str):
    """
    Import a manually exported Semrush CSV into Supabase.
    Use this when API units are exhausted.
    """
    import csv

    client_id = get_client_id(client_slug)
    comp_id = get_competitor_id(client_id, competitor_domain)

    if not client_id or not comp_id:
        print("ERROR: Client or competitor not found")
        return

    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    save_signal(client_id, comp_id, "semrush_csv", signal_type, {"keywords": rows, "imported_date": date.today().isoformat()})
    print(f"Imported {len(rows)} rows from {csv_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python semrush_collector.py <client_slug>")
        sys.exit(1)

    collect_for_client(sys.argv[1])
