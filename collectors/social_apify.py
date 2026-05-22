"""
Scout — Apify Social Collector
Collects social signals across Instagram, TikTok, Facebook, YouTube, and Meta Ads Library
using Apify actors. Replaces social_youtube.py and social_instagram.py.

Actors used:
- apify/instagram-scraper
- clockworks/tiktok-scraper
- apify/facebook-posts-scraper
- apify/facebook-ads-scraper
- streamers/youtube-scraper
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
APIFY_API_KEY = os.environ.get("APIFY_API_KEY")

APIFY_BASE = "https://api.apify.com/v2"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Apify API Helpers ─────────────────────────────────────────────────────────

def run_actor(actor_id: str, input_data: dict, timeout_secs: int = 120) -> list:
    """
    Run an Apify actor synchronously and return the results.
    Waits for completion up to timeout_secs.
    """
    print(f"[apify] Running actor: {actor_id}")

    # Start the actor run
    resp = requests.post(
        f"{APIFY_BASE}/acts/{actor_id.replace('/', '~')}/runs",
        headers={"Authorization": f"Bearer {APIFY_API_KEY}"},
        json=input_data,
        params={"timeout": timeout_secs, "memory": 256},
    )
    resp.raise_for_status()
    run_data = resp.json().get("data", {})
    run_id = run_data.get("id")

    if not run_id:
        print(f"[apify] ERROR: No run ID returned for {actor_id}")
        return []

    # Poll for completion
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        status_resp = requests.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            headers={"Authorization": f"Bearer {APIFY_API_KEY}"},
        )
        status_resp.raise_for_status()
        status = status_resp.json().get("data", {}).get("status")

        if status == "SUCCEEDED":
            break
        elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"[apify] Actor {actor_id} run {status}")
            return []

        time.sleep(5)
    else:
        print(f"[apify] Actor {actor_id} timed out after {timeout_secs}s")
        return []

    # Fetch results from dataset
    dataset_id = status_resp.json().get("data", {}).get("defaultDatasetId")
    if not dataset_id:
        return []

    results_resp = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {APIFY_API_KEY}"},
        params={"format": "json", "limit": 50},
    )
    results_resp.raise_for_status()
    results = results_resp.json()

    print(f"[apify] {actor_id} returned {len(results)} items")
    return results


# ── Platform Collectors ───────────────────────────────────────────────────────

def collect_instagram(handle: str) -> dict:
    """Collect Instagram profile metrics and recent posts."""
    try:
        results = run_actor("apify/instagram-scraper", {
            "usernames": [handle],
            "resultsType": "posts",
            "resultsLimit": 20,
            "addParentData": True,
        })

        if not results:
            return {}

        # Extract profile data from first result
        profile = results[0] if results else {}
        posts = results[:20]

        # Calculate post frequency (last 30 days)
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_posts = [
            p for p in posts
            if p.get("timestamp") and datetime.fromisoformat(
                p["timestamp"].replace("Z", "+00:00")
            ).replace(tzinfo=None) > cutoff
        ]

        avg_likes = sum(p.get("likesCount", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0
        avg_comments = sum(p.get("commentsCount", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0

        # Extract content themes from captions
        captions = [p.get("caption", "") for p in recent_posts if p.get("caption")]

        return {
            "platform": "instagram",
            "handle": handle,
            "follower_count": profile.get("followersCount"),
            "following_count": profile.get("followingCount"),
            "posts_count": profile.get("postsCount"),
            "posts_last_30d": len(recent_posts),
            "avg_likes": round(avg_likes, 1),
            "avg_comments": round(avg_comments, 1),
            "engagement_rate": round((avg_likes + avg_comments) / profile.get("followersCount", 1) * 100, 3) if profile.get("followersCount") else 0,
            "recent_captions": captions[:5],
            "collected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"[apify] ERROR Instagram {handle}: {e}")
        return {}


def collect_tiktok(handle: str) -> dict:
    """Collect TikTok profile metrics and recent posts."""
    try:
        results = run_actor("clockworks/tiktok-scraper", {
            "profiles": [handle],
            "resultsPerPage": 20,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
        })

        if not results:
            return {}

        # Separate profile from posts
        profile_data = next((r for r in results if r.get("type") == "user"), {})
        posts = [r for r in results if r.get("type") == "video"][:20]

        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_posts = [
            p for p in posts
            if p.get("createTimeISO") and datetime.fromisoformat(
                p["createTimeISO"].replace("Z", "+00:00")
            ).replace(tzinfo=None) > cutoff
        ]

        avg_views = sum(p.get("playCount", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0
        avg_likes = sum(p.get("diggCount", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0

        descriptions = [p.get("text", "") for p in recent_posts if p.get("text")]

        return {
            "platform": "tiktok",
            "handle": handle,
            "follower_count": profile_data.get("fans"),
            "following_count": profile_data.get("following"),
            "total_likes": profile_data.get("heart"),
            "posts_last_30d": len(recent_posts),
            "avg_views": round(avg_views, 0),
            "avg_likes": round(avg_likes, 1),
            "recent_descriptions": descriptions[:5],
            "collected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"[apify] ERROR TikTok {handle}: {e}")
        return {}


def collect_facebook_posts(page_name: str) -> dict:
    """Collect Facebook page posts and engagement metrics."""
    try:
        results = run_actor("apify/facebook-posts-scraper", {
            "startUrls": [{"url": f"https://www.facebook.com/{page_name}"}],
            "resultsLimit": 20,
        })

        if not results:
            return {}

        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_posts = [
            p for p in results
            if p.get("time") and datetime.fromisoformat(
                p["time"].replace("Z", "+00:00")
            ).replace(tzinfo=None) > cutoff
        ]

        avg_likes = sum(p.get("likes", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0
        avg_comments = sum(p.get("comments", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0
        avg_shares = sum(p.get("shares", 0) for p in recent_posts) / len(recent_posts) if recent_posts else 0

        texts = [p.get("text", "") for p in recent_posts if p.get("text")]

        return {
            "platform": "facebook",
            "page": page_name,
            "posts_last_30d": len(recent_posts),
            "avg_likes": round(avg_likes, 1),
            "avg_comments": round(avg_comments, 1),
            "avg_shares": round(avg_shares, 1),
            "recent_texts": texts[:5],
            "collected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"[apify] ERROR Facebook {page_name}: {e}")
        return {}


def collect_facebook_ads(competitor_name: str) -> dict:
    """Scrape Meta Ads Library for active competitor ads."""
    try:
        results = run_actor("apify/facebook-ads-scraper", {
            "searchTerms": [competitor_name],
            "adType": "all",
            "country": "US",
            "resultsLimit": 20,
        })

        if not results:
            return {}

        ads = []
        for ad in results[:20]:
            ads.append({
                "ad_id": ad.get("adArchiveID") or ad.get("id"),
                "page_name": ad.get("pageName"),
                "ad_creative_body": (ad.get("snapshot", {}).get("body", {}).get("text", "") or "")[:300],
                "ad_creative_link_title": ad.get("snapshot", {}).get("title", ""),
                "start_date": ad.get("startDate"),
                "end_date": ad.get("endDate"),
                "formats": ad.get("publisherPlatform", []),
                "is_active": ad.get("isActive", True),
            })

        active_ads = [a for a in ads if a.get("is_active")]

        return {
            "platform": "meta_ads",
            "competitor": competitor_name,
            "total_active_ads": len(active_ads),
            "ads": ads,
            "collected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"[apify] ERROR Meta Ads {competitor_name}: {e}")
        return {}


def collect_youtube(channel_id: str) -> dict:
    """Collect YouTube channel metrics and recent video data."""
    try:
        results = run_actor("streamers/youtube-scraper", {
            "startUrls": [{"url": f"https://www.youtube.com/channel/{channel_id}/videos"}],
            "maxResults": 20,
            "includeComments": False,
        })

        if not results:
            return {}

        # Separate channel from videos
        channel = next((r for r in results if r.get("type") == "channel"), {})
        videos = [r for r in results if r.get("type") == "video"][:20]

        cutoff = datetime.utcnow() - timedelta(days=14)
        recent_videos = [
            v for v in videos
            if v.get("uploadedAt") and datetime.fromisoformat(
                v["uploadedAt"].replace("Z", "+00:00")
            ).replace(tzinfo=None) > cutoff
        ]

        top_video = max(videos, key=lambda v: v.get("viewCount", 0)) if videos else {}

        # Extract content themes from titles and descriptions
        titles = [v.get("title", "") for v in recent_videos if v.get("title")]
        descriptions = [v.get("description", "")[:200] for v in recent_videos if v.get("description")]
        tags = list(set(tag for v in recent_videos for tag in (v.get("tags") or [])))[:20]

        return {
            "platform": "youtube",
            "channel_id": channel_id,
            "subscriber_count": channel.get("subscriberCount") or (videos[0].get("channelSubscriberCount") if videos else None),
            "video_count": channel.get("videoCount"),
            "uploads_14d": len(recent_videos),
            "views_14d": sum(v.get("viewCount", 0) for v in recent_videos),
            "avg_views": round(sum(v.get("viewCount", 0) for v in recent_videos) / len(recent_videos), 0) if recent_videos else 0,
            "top_video_title": top_video.get("title"),
            "top_video_url": top_video.get("url"),
            "top_video_views": top_video.get("viewCount"),
            "recent_titles": titles,
            "recent_tags": tags,
            "recent_descriptions": descriptions[:3],
            "collected_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        print(f"[apify] ERROR YouTube {channel_id}: {e}")
        return {}


# ── Supabase Storage ──────────────────────────────────────────────────────────

def get_client_id(slug: str) -> str | None:
    result = supabase.table("clients").select("id").eq("slug", slug).single().execute()
    return result.data["id"] if result.data else None


def get_competitor_id(client_id: str, name: str) -> str | None:
    result = (
        supabase.table("competitors")
        .select("id")
        .eq("client_id", client_id)
        .ilike("name", name)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None


def save_signal(client_id: str, competitor_id: str, signal_type: str, data: dict):
    supabase.table("signals").insert({
        "client_id": client_id,
        "competitor_id": competitor_id,
        "source": "apify",
        "signal_type": signal_type,
        "data": data,
        "collected_at": datetime.utcnow().isoformat(),
    }).execute()


# ── Main Collection Flow ──────────────────────────────────────────────────────

def collect_for_client(client_slug: str):
    """Run full Apify social collection for a client and all competitors."""
    print(f"[apify] Starting social collection for: {client_slug}")

    client_id = get_client_id(client_slug)
    if not client_id:
        print(f"[apify] ERROR: Client '{client_slug}' not found")
        return

    result = supabase.table("clients").select("config").eq("id", client_id).single().execute()
    config = result.data.get("config", {})
    competitors = config.get("competitors", [])

    for comp in competitors:
        name = comp.get("name")
        comp_id = get_competitor_id(client_id, name)

        if not comp_id:
            print(f"[apify] WARNING: Competitor '{name}' not in DB, skipping")
            continue

        print(f"[apify] Collecting social signals for: {name}")

        # Instagram
        if comp.get("instagram_handle"):
            data = collect_instagram(comp["instagram_handle"])
            if data:
                save_signal(client_id, comp_id, "instagram_apify", data)
                print(f"[apify]   Instagram: {data.get('posts_last_30d')} posts last 30d")

        # TikTok
        if comp.get("tiktok_handle"):
            data = collect_tiktok(comp["tiktok_handle"])
            if data:
                save_signal(client_id, comp_id, "tiktok", data)
                print(f"[apify]   TikTok: {data.get('posts_last_30d')} posts last 30d")

        # Facebook Posts
        if comp.get("facebook_page"):
            data = collect_facebook_posts(comp["facebook_page"])
            if data:
                save_signal(client_id, comp_id, "facebook_posts", data)
                print(f"[apify]   Facebook: {data.get('posts_last_30d')} posts last 30d")

        # Meta Ads Library
        data = collect_facebook_ads(name)
        if data:
            save_signal(client_id, comp_id, "meta_ads", data)
            print(f"[apify]   Meta Ads: {data.get('total_active_ads')} active ads")

        # YouTube
        if comp.get("youtube_channel_id"):
            data = collect_youtube(comp["youtube_channel_id"])
            if data:
                save_signal(client_id, comp_id, "youtube_apify", data)
                print(f"[apify]   YouTube: {data.get('uploads_14d')} uploads last 14d")

    print(f"[apify] Done: {client_slug}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python social_apify.py <client_slug>")
        sys.exit(1)
    collect_for_client(sys.argv[1])
