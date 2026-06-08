"""
Scout — Two-Call Claude Synthesizer v2
Call 1: The Analyst — objective signal analysis, 5-component pressure scoring
Call 2: The Strategist — recommendations via advisory board and client brain

Pressure Score Components (updated May 2026):
  Social & Content Investment  30%  — Apify social signals (real data, high confidence)
  Owned Channel Activity       25%  — Web changes + competitor email CRM (real data, high confidence)
  Paid Investment              20%  — Meta Ads Library + Semrush paid (medium-high confidence)
  Search Presence              15%  — Semrush organic + Google Trends (medium confidence, estimated)
  News & PR                    10%  — Google News mentions (medium confidence, reactive)
"""

import os
import json
from datetime import datetime, date, timedelta
from anthropic import Anthropic
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Advisory Board ────────────────────────────────────────────────────────────
# Role titles used in output — never advisor names. Advisors are internal.

ADVISOR_ROLE_TITLES = {
    "seo_content": "SEO Strategist",
    "organic_demand": "Organic Growth Strategist",
    "paid_media": "Paid Media Specialist",
    "paid_search": "Paid Search Specialist",
    "retail": "Retail Strategist",
    "social": "Social Media Strategist",
    "branding": "Brand Strategist",
}

ADVISOR_PROMPTS = {
    "seo_content": """SEO & Content Marketing Framework:
- Content must be the best answer on the internet for the audience's question. Generic content is invisible.
- Data beats intuition. What does search data actually show? What are people asking?
- Updating existing content often outperforms creating new content. What pages almost rank?
- Links are earned through original research, tools, and being genuinely quotable.
- Analytics drive editorial decisions. What's working? Do more of it.
- Ask: What content gaps are competitors exploiting? What informational keywords are they ranking for? What pages drive the majority of competitor organic traffic? What content is earning links?""",

    "organic_demand": """Organic Growth & Brand Demand Framework:
- Brand awareness drives search demand. People search for brands they've heard of.
- Audience intelligence over keyword research. Where does the audience actually spend time?
- Zero-click searches are the new reality. Optimize for brand impression even when no click occurs.
- Share of Voice matters more than rank. Show up consistently across the audience's world.
- Dark social is real. Design for shareability in channels you can't track.
- Ask: Are competitors building brand demand or just capturing existing demand? What audiences are they reaching that we're not? Is their organic growth driven by genuine brand affinity or fragile SEO tactics?""",

    "paid_media": """Paid Media & Brand Amplification Framework:
- Amplify best organic content with small paid budgets before scaling. Don't create ads — promote what's already working.
- Video first. Video creative outperforms static for consumer brands across every paid channel.
- Amplify people, not just products. Employee and customer stories are inherently credible.
- Retargeting is where the money is. Most brands underinvest in their warm audience.
- Cross-channel consistency dramatically improves conversion rates.
- Ask: Are competitors running paid social to amplify organic content or purely promotional ads? What creative formats are they using? What's the gap in their funnel? Are they investing in video or static?""",

    "paid_search": """Paid Search & SEM Strategy Framework:
- Match types and search terms are the foundation. Most paid search problems trace back here.
- Ad testing must be systematic. Test one variable at a time with statistical significance.
- Budget allocation should follow performance data, not gut feel.
- Dayparting and geo-targeting are frequently underutilized, especially for regional retailers.
- Automation requires quality data and clear goals. Don't automate before sufficient conversion data.
- Ask: What does competitor keyword footprint tell us about their strategy? Are they bidding on branded terms? What keyword gaps exist where competitors are absent? For a regional retailer, are national competitors wasting spend on non-local traffic?""",

    "retail": """Retail Strategy & In-Store Experience Framework:
- Your people are your most important competitive advantage. No digital strategy compensates for undertrained associates.
- Retail is not transactional — it's emotional. Sell the outcome (better sleep, less pain), not the product.
- Online competitors can match price and product. They cannot match genuine human connection.
- Local market knowledge is a moat. A regional retailer that knows their community has an inherent advantage.
- Margin is protected by experience, not price. Competing on price is a race to the bottom.
- Ask: Are competitors signaling a shift in in-store experience strategy? What digital activity suggests driving foot traffic vs. online conversion? Where is the client's human-first model most differentiated?""",

    "social": """Social Media & Viral Content Strategy Framework:
- The Hook Point is everything. In a 3-second world, the first moment determines whether someone stops or scrolls.
- Virality is a science, not luck. Test systematically — hypothesis, test, analyze, pivot.
- Upload frequency is a signal of investment. Sporadic posting signals uncertainty or resource constraints.
- Platform-native content wins. Cross-posted content consistently underperforms.
- Engagement rate over follower count. A smaller highly engaged audience beats a large passive one.
- The first 24-48 hours determine algorithmic fate. Engineer early engagement deliberately.
- Ask: What's each competitor's upload cadence and what does it signal? Are they using platform-native formats? What content themes are emerging? Where has a competitor left a social gap the client could fill?""",

    "branding": """Brand Positioning & Category Strategy Framework:
- Positioning is a battle fought in the mind of the consumer, not the marketplace. Own a word.
- The Law of Leadership: better to be first than better. If you can't be first in a category, create one.
- The Law of the Opposite: if the leader owns one extreme, the powerful position is the other extreme.
- Focus wins. Brands that try to be everything own nothing in anyone's mind.
- PR builds brands; advertising maintains them. Credibility comes from third-party validation.
- Line extension dilutes brand power. Too many categories weakens core positioning.
- Ask: What word is each competitor trying to own? Are competitors diluting their positioning? Where has a competitor left a positioning gap the client could own?"""
}


# ── Signal Slimming ───────────────────────────────────────────────────────────

def slim_signal(source: str, signal: dict) -> dict | None:
    """Reduce each signal to only what Claude needs. Prevents token overflow."""
    comp = signal.get("competitor", "Unknown")
    data = signal.get("data", {})
    signal_type = signal.get("signal_type", "")

    if source == "semrush":
        if signal_type == "domain_overview":
            return {
                "competitor": comp,
                "signal_type": "domain_overview",
                "organic_keywords": data.get("Or"),
                "organic_traffic": data.get("Ot"),
                "adwords_keywords": data.get("Adwords Keywords") or data.get("Ad"),
                "adwords_traffic": data.get("Adwords Traffic") or data.get("At"),
            }
        if signal_type == "tracked_keyword_positions":
            return {
                "competitor": comp,
                "signal_type": "tracked_keyword_positions",
                "keyword_positions": [
                    {"keyword": k.get("keyword"), "position": k.get("position"), "volume": k.get("volume")}
                    for k in data.get("keywords", []) if k.get("position") is not None
                ],
            }
        if signal_type == "client_keyword_positions":
            return {
                "competitor": "Mattress Warehouse (client)",
                "signal_type": "client_keyword_positions",
                "keyword_positions": [
                    {"keyword": k.get("keyword"), "position": k.get("position"), "volume": k.get("volume")}
                    for k in data.get("keywords", []) if k.get("position") is not None
                ],
            }
        # organic_keywords fallback
        keywords = sorted(data.get("keywords", []), key=lambda k: int(k.get("Nq", 0) or 0), reverse=True)[:20]
        return {
            "competitor": comp,
            "signal_type": signal_type,
            "keywords": [
                {"keyword": k.get("Ph"), "position": k.get("Po"), "volume": k.get("Nq"),
                 "position_change": k.get("Pd", 0), "url": k.get("Ur")}
                for k in keywords
            ],
        }

    elif source == "google_news":
        return {
            "competitor": comp,
            "articles": [
                {"title": a.get("title", "")[:120], "source": a.get("source", ""), "published": a.get("published", "")}
                for a in data.get("articles", [])[:5]
            ],
        }

    elif source == "web_change":
        score = data.get("significance_score")
        if not score or int(score) == 0:
            return None
        return {
            "competitor": comp,
            "url": data.get("url", ""),
            "significance_score": score,
            "changes": [
                {"field": c.get("field"), "added": c.get("added", [])[:3], "removed": c.get("removed", [])[:3]}
                for c in data.get("changes", [])
            ],
        }

    elif source == "apify":
        if signal_type == "instagram_apify":
            return {
                "competitor": comp,
                "platform": "instagram",
                "follower_count": data.get("follower_count"),
                "posts_last_30d": data.get("posts_last_30d"),
                "avg_likes": data.get("avg_likes"),
                "engagement_rate": data.get("engagement_rate"),
                "recent_captions": data.get("recent_captions", [])[:3],
            }
        elif signal_type == "tiktok":
            return {
                "competitor": comp,
                "platform": "tiktok",
                "follower_count": data.get("follower_count"),
                "posts_last_30d": data.get("posts_last_30d"),
                "avg_views": data.get("avg_views"),
                "recent_descriptions": data.get("recent_descriptions", [])[:3],
            }
        elif signal_type == "facebook_posts":
            return {
                "competitor": comp,
                "platform": "facebook",
                "posts_last_30d": data.get("posts_last_30d"),
                "avg_likes": data.get("avg_likes"),
                "avg_shares": data.get("avg_shares"),
                "recent_texts": data.get("recent_texts", [])[:3],
            }
        elif signal_type == "meta_ads":
            ads = data.get("ads", [])[:10]
            return {
                "competitor": comp,
                "platform": "meta_ads",
                "total_active_ads": data.get("total_active_ads", 0),
                "ads": [
                    {
                        "creative_body": a.get("ad_creative_body", "")[:200],
                        "link_title": a.get("ad_creative_link_title", ""),
                        "formats": a.get("formats", []),
                        "start_date": a.get("start_date"),
                        "is_active": a.get("is_active", True),
                    }
                    for a in ads
                ],
            }
        elif signal_type == "youtube_apify":
            return {
                "competitor": comp,
                "platform": "youtube",
                "subscriber_count": data.get("subscriber_count"),
                "uploads_14d": data.get("uploads_14d"),
                "views_14d": data.get("views_14d"),
                "top_video_title": data.get("top_video_title"),
                "top_video_views": data.get("top_video_views"),
                "recent_titles": data.get("recent_titles", [])[:5],
                "recent_tags": data.get("recent_tags", [])[:10],
            }

    elif source == "reddit":
        return {
            "competitor": comp,
            "subreddit": data.get("subreddit"),
            "posts": [
                {"title": p.get("title", "")[:100], "score": p.get("score", 0), "num_comments": p.get("num_comments", 0)}
                for p in data.get("posts", [])[:5]
            ],
        }

    else:
        return {"competitor": comp, "signal_type": signal_type, "summary": str(data)[:300]}


# ── Fetch Signals ─────────────────────────────────────────────────────────────

def fetch_week_signals(client_id: str, days_back: int = 7) -> dict:
    """Pull all signals from the past week, slim them, and organize by source."""
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()

    result = (
        supabase.table("signals")
        .select("*, competitors(name, domain)")
        .eq("client_id", client_id)
        .gte("collected_at", cutoff)
        .execute()
    )

    organized = {
        "semrush_overview": [],
        "semrush_keywords": [],
        "semrush_paid": [],
        "semrush_positions": [],
        "google_news": [],
        "web_changes": [],
        "reddit": [],
        "social_instagram": [],
        "social_tiktok": [],
        "social_facebook": [],
        "social_meta_ads": [],
        "social_youtube": [],
    }

    for signal in (result.data or []):
        comp_name = (signal.get("competitors") or {}).get("name", "Unknown")
        if not signal.get("competitors"):
            comp_name = "Mattress Warehouse"
        source = signal.get("source", "other")
        signal_type = signal.get("signal_type", "")

        entry = {
            "competitor": comp_name,
            "signal_type": signal_type,
            "data": signal["data"],
            "collected_at": signal["collected_at"],
        }

        slimmed = slim_signal(source, entry)
        if slimmed is None:
            continue

        if source in ("semrush", "semrush_csv"):
            if signal_type == "domain_overview":
                organized["semrush_overview"].append(slimmed)
            elif signal_type == "organic_keywords":
                organized["semrush_keywords"].append(slimmed)
            elif signal_type == "paid_keywords":
                organized["semrush_paid"].append(slimmed)
            elif signal_type in ("tracked_keyword_positions", "client_keyword_positions"):
                organized["semrush_positions"].append(slimmed)
        elif source == "google_news":
            organized["google_news"].append(slimmed)
        elif source == "web_change":
            organized["web_changes"].append(slimmed)
        elif source == "reddit":
            organized["reddit"].append(slimmed)
        elif source == "apify":
            if signal_type == "instagram_apify":
                organized["social_instagram"].append(slimmed)
            elif signal_type == "tiktok":
                organized["social_tiktok"].append(slimmed)
            elif signal_type == "facebook_posts":
                organized["social_facebook"].append(slimmed)
            elif signal_type == "meta_ads":
                organized["social_meta_ads"].append(slimmed)
            elif signal_type == "youtube_apify":
                organized["social_youtube"].append(slimmed)

    for key in organized:
        organized[key] = organized[key][:15]

    return organized


def fetch_recent_competitor_emails(client_id: str, days_back: int = 7) -> list:
    """Pull unanalyzed competitor emails from the past week."""
    cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()

    result = (
        supabase.table("competitor_emails")
        .select("competitor_name, subject, body_text, from_address, received_at")
        .eq("client_id", client_id)
        .gte("received_at", cutoff)
        .order("received_at", desc=True)
        .limit(20)
        .execute()
    )

    emails = []
    for e in (result.data or []):
        emails.append({
            "competitor": e.get("competitor_name"),
            "subject": e.get("subject", ""),
            "body_preview": (e.get("body_text") or "")[:300],
            "received_at": e.get("received_at"),
        })

    return emails


# ── Call 1: The Analyst ───────────────────────────────────────────────────────

ANALYST_SYSTEM = """You are the Scout Analyst. Your job is pure objective intelligence.
Analyze raw competitive signals and produce structured data. No recommendations. No strategy. Just what happened, what changed, and what the numbers show.

You write with precision. Every claim must reference data in the signals provided.

Three hard rules:
1. CITATION ENFORCEMENT: Only reference competitors, keywords, and numbers present in the signals above. Never introduce facts from memory.
2. CONFIDENCE GATING: If fewer than 3 signals exist for a competitor in a given category, add them to data_quality_flags and note limited data rather than drawing conclusions.
3. SCHEMA ENFORCEMENT: Respond only with valid JSON matching the schema provided. No free-form narrative outside defined fields.
4. Meta Ads Sampling Guardrail: The meta_ads signal provides TWO counts:
   - `total_ads_in_library`: the real number of active ads in Meta's Ad Library (e.g. 387)
   - `ads_sampled`: how many we collected for analysis (always ≤ 20, our collection cap)
   NEVER say a competitor "is running [ads_sampled] ads" — that number is meaningless, it is 
   always our cap. Use total_ads_in_library for any volume statement. Focus analysis on the 
   sampled ads' creative themes: messaging angles, product focus, offer/discount language, 
   formats (DCO, video, carousel, image), UGC vs. brand content, and funnel stage 
   (awareness/Prospecting vs. conversion/retargeting visible in UTM campaign names).

Output format: Always respond with valid JSON matching the schema provided."""


def build_analyst_prompt(client_name: str, signals: dict, emails: list, week_of: str) -> str:
    return f"""Analyze the following competitive intelligence signals for {client_name} (week of {week_of}).

## SCORING METHODOLOGY
Score each component using ONLY the signals present. Apply these weights:
- Social & Content Investment (30%): Instagram, TikTok, Facebook, YouTube signals
- Owned Channel Activity (25%): Web changes + competitor email signals
- Paid Investment (20%): Meta Ads Library + Semrush paid keyword data
- Search Presence (15%): Semrush organic positions + tracked keyword data
- News & PR (10%): Google News mentions and coverage

Score ranges: 0-25 Calm, 26-50 Active, 51-75 Elevated, 76-90 High, 91-100 Critical

## RAW SIGNALS
{json.dumps(signals, indent=2, default=str)}

## COMPETITOR EMAILS THIS WEEK
{json.dumps(emails, indent=2, default=str) if emails else "No emails received yet — monitoring active."}

## YOUR TASK
Produce structured competitive intelligence as JSON:

{{
  "pressure_score": <integer 0-100, weighted composite>,
  "pressure_components": {{
    "social_content_investment": <0-100>,
    "owned_channel_activity": <0-100>,
    "paid_investment": <0-100>,
    "search_presence": <0-100>,
    "news_pr": <0-100>
  }},
  "executive_summary": "<2-3 sentence objective summary — facts only, no recommendations>",
  "competitor_intelligence": [
    {{
      "competitor": "<name>",
      "social_activity": "<summary of social signals this week>",
      "paid_activity": "<summary of paid signals>",
      "owned_channel_activity": "<summary of web changes and email signals>",
      "search_activity": "<summary of keyword position data>",
      "news_activity": "<summary of news mentions>",
      "notable_changes": ["<specific change 1>", "<specific change 2>"]
    }}
  ],
  "keyword_comparison": [
    {{
      "keyword": "<tracked keyword>",
      "volume": <integer or null>,
      "client_position": <integer or null>,
      "competitor_positions": {{"<competitor name>": <integer or null>}}
    }}
  ],
  "social_metrics": [
    {{
      "competitor": "<name>",
      "platform": "<platform>",
      "followers": <integer or null>,
      "posts_this_week": <integer or null>,
      "avg_engagement": <float or null>,
      "top_content_theme": "<dominant theme from captions/titles/descriptions>"
    }}
  ],
  "meta_ads_intelligence": [
    {{
      "competitor": "<name>",
      "active_ad_count": <integer>,
      "dominant_format": "<video|image|carousel|unknown>",
      "messaging_theme": "<what the ads are saying>",
      "estimated_campaign_start": "<date or unknown>",
      "notable_creative": "<most interesting ad copy observed>"
    }}
  ],
  "email_intelligence": [
    {{
      "competitor": "<name>",
      "emails_received": <integer>,
      "subjects": ["<subject 1>", "<subject 2>"],
      "promotional_offer": "<discount or offer if present, null if none>",
      "messaging_theme": "<what they are communicating>",
      "send_frequency": "<daily|weekly|multiple_weekly|unknown>"
    }}
  ],
  "web_changes": [
    {{
      "competitor": "<name>",
      "url": "<page changed>",
      "significance_score": <integer>,
      "what_changed": "<specific change observed>",
      "strategic_implication": "<what this might signal>"
    }}
  ],
  "brand_campaign_signals": [
    {{
      "competitor": "<name>",
      "confidence": "high|medium|low",
      "evidence": ["<signal 1>", "<signal 2>", "<signal 3>"],
      "campaign_theme": "<what the campaign appears to be about>",
      "first_detected": "<earliest signal date>"
    }}
  ],
  "content_themes": [
    {{
      "competitor": "<name>",
      "themes": ["<theme 1>", "<theme 2>", "<theme 3>"],
      "dominant_platform": "<where most content activity is happening>",
      "theme_shift": "<has their content focus changed from typical? describe or null>"
    }}
  ],
  "keyword_movements": [
    {{
      "competitor": "<name>",
      "keyword": "<keyword>",
      "position_change": <integer>,
      "current_position": <integer>,
      "overlap_with_client": <true|false>,
      "monthly_volume": <integer>
    }}
  ],
  "data_quality_flags": ["<competitor or source with limited data this week>"]
}}

## BRAND CAMPAIGN DETECTION RULES
Flag a brand_campaign_signal when you observe TWO OR MORE of these in the same week for a competitor:
- Homepage or key landing page messaging change (web change with significance score > 50)
- Social upload frequency spike (posts this week significantly above typical)
- New Meta ads appearing with consistent messaging theme
- News coverage spike
- New promotional offer in email/CRM
High confidence = 3+ signals. Medium = 2 signals. Low = 1 signal with strong circumstantial support."""


# ── Call 2: The Strategist ────────────────────────────────────────────────────

STRATEGIST_SYSTEM = """You are the Scout Strategist for Parallel Path, a digital marketing agency.
You receive structured competitive intelligence and transform it into specific, actionable recommendations.

You think like a senior strategist advising a real client. Every recommendation must be:
- Specific enough to brief a team member on Monday morning
- Realistic given the client's actual capabilities and Parallel Path's digital marketing scope
- Grounded in the intelligence provided — never introduce events or data not in the analysis
- Attributed to a role title (e.g. "SEO Strategist recommends...") never a person's name

Output format: Always respond with valid JSON matching the schema provided."""


def build_strategist_prompt(
    client_name: str,
    analysis: dict,
    brain: str,
    active_advisors: list,
    week_of: str
) -> str:

    advisor_section = "\n\n".join([
        f"[{ADVISOR_ROLE_TITLES.get(a, a).upper()}]\n{ADVISOR_PROMPTS[a]}"
        for a in active_advisors if a in ADVISOR_PROMPTS
    ])

    return f"""You are producing strategic recommendations for {client_name} (week of {week_of}).

## CLIENT CONTEXT
{brain}

## ADVISORY FRAMEWORKS
Apply these frameworks when generating recommendations. Attribute recommendations to role titles only — never to advisor names:

{advisor_section}

## THIS WEEK'S COMPETITIVE INTELLIGENCE
{json.dumps(analysis, indent=2, default=str)}

## YOUR TASK
Produce strategic recommendations as JSON:

{{
  "top_developments": [
    {{
      "type": "alert|watch|opportunity",
      "competitor": "<name>",
      "headline": "<10 words max>",
      "detail": "<2-3 sentences — what this means strategically for {client_name}>",
      "recommended_action": "<1 specific action — specific enough to brief a team member Monday morning>",
      "urgency": "immediate|this_week|this_month",
      "advisor_role": "<role title that informed this e.g. Paid Media Specialist, SEO Strategist>"
    }}
  ],
  "strategic_narrative": "<3-4 sentences synthesizing the week's competitive picture for a marketing director>",
  "social_content_recommendations": [
    {{
      "competitor": "<name>",
      "platform": "<platform>",
      "observation": "<what their content activity shows>",
      "content_theme": "<dominant theme observed>",
      "recommended_response": "<specific content action for {client_name}>",
      "advisor_role": "<role title>"
    }}
  ],
  "paid_recommendations": [
    {{
      "competitor": "<name>",
      "observation": "<what the paid data shows>",
      "implication": "<what this means for {client_name}>",
      "recommended_action": "<specific paid media action>",
      "advisor_role": "<role title>"
    }}
  ],
  "search_recommendations": [
    {{
      "observation": "<what the keyword data shows>",
      "opportunity": "<specific keyword or content gap>",
      "recommended_action": "<specific SEO or content action>",
      "advisor_role": "<role title>"
    }}
  ],
  "brand_campaign_alerts": [
    {{
      "competitor": "<name>",
      "campaign_summary": "<what the campaign appears to be>",
      "threat_level": "high|medium|low",
      "recommended_response": "<specific action for {client_name}>",
      "advisor_role": "<role title>"
    }}
  ],
  "owned_channel_observations": [
    {{
      "competitor": "<name>",
      "signal_type": "web_change|email|content",
      "observation": "<what was detected>",
      "implication": "<what this signals>",
      "recommended_action": "<specific response if warranted>"
    }}
  ],
  "week_over_week_changes": {{
    "pressure_score_delta": <integer>,
    "notable_changes": ["<change 1>", "<change 2>"]
  }}
}}

Rules:
- top_developments: 3-5 items sorted by urgency
- alert = immediate threats, watch = trends to monitor, opportunity = gaps to exploit
- Every recommended_action must be realistic for a digital marketing agency scope
- Always use role titles, never advisor names
- Brand campaign alerts should only appear if the Analyst flagged brand_campaign_signals"""


# ── Advisor Activation ────────────────────────────────────────────────────────

def select_active_advisors(signals: dict, advisors_config: dict) -> list:
    active_signals = set()

    if signals.get("semrush_overview") or signals.get("semrush_keywords") or signals.get("semrush_positions"):
        active_signals.add("organic_search")
    if signals.get("semrush_paid") or signals.get("social_meta_ads"):
        active_signals.add("paid_search")
    if signals.get("web_changes"):
        active_signals.add("web_changes")
        active_signals.add("content_velocity")
    if signals.get("social_instagram") or signals.get("social_tiktok") or signals.get("social_facebook") or signals.get("social_youtube"):
        active_signals.add("social_buzz")
        active_signals.add("content_velocity")

    active_advisors = []
    for key, config in advisors_config.items():
        if any(s in active_signals for s in config.get("activation", [])):
            active_advisors.append(key)

    print(f"[synthesizer] Active signals: {active_signals}")
    print(f"[synthesizer] Activated advisors: {[ADVISOR_ROLE_TITLES.get(a, a) for a in active_advisors]}")
    return active_advisors


# ── Supabase Helpers ──────────────────────────────────────────────────────────

def get_last_week_score(client_id: str) -> int | None:
    last_week = (date.today() - timedelta(days=7)).isoformat()
    result = (
        supabase.table("briefings")
        .select("pressure_score")
        .eq("client_id", client_id)
        .lte("week_of", last_week)
        .order("week_of", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["pressure_score"] if result.data else None


def mark_emails_analyzed(client_id: str, week_cutoff: str):
    """Mark all emails from this week as analyzed."""
    supabase.table("competitor_emails").update({"analyzed": True}).eq("client_id", client_id).gte("received_at", week_cutoff).execute()


# ── Main Synthesis Flow ───────────────────────────────────────────────────────

def synthesize_for_client(client_slug: str):
    """Generate weekly briefing using two-call architecture."""
    print(f"[synthesizer] Starting two-call synthesis for: {client_slug}")

    result = supabase.table("clients").select("id, name, config, brain, advisors").eq("slug", client_slug).single().execute()
    if not result.data:
        print(f"[synthesizer] ERROR: Client '{client_slug}' not found")
        return

    client_id = result.data["id"]
    client_name = result.data["name"]
    brain = result.data.get("brain") or "No client brain configured."
    advisors_config = result.data.get("advisors") or {}
    week_of = date.today().isoformat()
    week_cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

    # Fetch signals and emails
    signals = fetch_week_signals(client_id)
    emails = fetch_recent_competitor_emails(client_id)
    total_signals = sum(len(v) for v in signals.values())
    print(f"[synthesizer] Found {total_signals} signals, {len(emails)} competitor emails")

    # ── Call 1: The Analyst ───────────────────────────────────────────────────
    analyst_prompt = build_analyst_prompt(client_name, signals, emails, week_of)
    estimated_tokens = len(analyst_prompt) // 4
    print(f"[synthesizer] Call 1 estimated tokens: ~{estimated_tokens:,}")

    if estimated_tokens > 150000:
        print(f"[synthesizer] WARNING: Trimming signals for token limit")
        for key in signals:
            signals[key] = signals[key][:5]
        analyst_prompt = build_analyst_prompt(client_name, signals, emails[:5], week_of)

    print(f"[synthesizer] Call 1: The Analyst...")
    analyst_response = anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        temperature=0.1,
        system=ANALYST_SYSTEM,
        messages=[{"role": "user", "content": analyst_prompt}],
    )

    try:
        raw = analyst_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        analysis = json.loads(raw.strip())
        print(f"[synthesizer] Call 1 complete — pressure score: {analysis.get('pressure_score')}")
    except json.JSONDecodeError as e:
        print(f"[synthesizer] ERROR: Failed to parse Analyst response: {e}")
        return

    # ── Call 2: The Strategist ────────────────────────────────────────────────
    active_advisors = select_active_advisors(signals, advisors_config)
    strategist_prompt = build_strategist_prompt(
        client_name=client_name,
        analysis=analysis,
        brain=brain,
        active_advisors=active_advisors,
        week_of=week_of,
    )
    estimated_tokens_2 = len(strategist_prompt) // 4
    print(f"[synthesizer] Call 2 estimated tokens: ~{estimated_tokens_2:,}")

    print(f"[synthesizer] Call 2: The Strategist...")
    strategist_response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
        temperature=0.3,
        system=STRATEGIST_SYSTEM,
        messages=[{"role": "user", "content": strategist_prompt}],
    )

    try:
        raw2 = strategist_response.content[0].text.strip()
        if raw2.startswith("```"):
            raw2 = raw2.split("```")[1]
            if raw2.startswith("json"):
                raw2 = raw2[4:]
        strategy = json.loads(raw2.strip())
        print(f"[synthesizer] Call 2 complete — {len(strategy.get('top_developments', []))} developments")
    except json.JSONDecodeError as e:
        print(f"[synthesizer] ERROR: Failed to parse Strategist response: {e}")
        return

    # ── Merge outputs ─────────────────────────────────────────────────────────
    last_score = get_last_week_score(client_id)
    pressure_delta = (analysis.get("pressure_score", 50) - last_score) if last_score is not None else 0

    if "week_over_week_changes" in strategy:
        strategy["week_over_week_changes"]["pressure_score_delta"] = pressure_delta

    full_report = {
        # From Analyst
        "pressure_score": analysis.get("pressure_score", 50),
        "pressure_components": analysis.get("pressure_components", {}),
        "executive_summary": analysis.get("executive_summary", ""),
        "competitor_intelligence": analysis.get("competitor_intelligence", []),
        "keyword_comparison": analysis.get("keyword_comparison", []),
        "keyword_movements": analysis.get("keyword_movements", []),
        "social_metrics": analysis.get("social_metrics", []),
        "meta_ads_intelligence": analysis.get("meta_ads_intelligence", []),
        "email_intelligence": analysis.get("email_intelligence", []),
        "web_changes": analysis.get("web_changes", []),
        "brand_campaign_signals": analysis.get("brand_campaign_signals", []),
        "content_themes": analysis.get("content_themes", []),
        "data_quality_flags": analysis.get("data_quality_flags", []),
        # From Strategist
        "top_developments": strategy.get("top_developments", []),
        "strategic_narrative": strategy.get("strategic_narrative", ""),
        "social_content_recommendations": strategy.get("social_content_recommendations", []),
        "paid_recommendations": strategy.get("paid_recommendations", []),
        "search_recommendations": strategy.get("search_recommendations", []),
        "brand_campaign_alerts": strategy.get("brand_campaign_alerts", []),
        "owned_channel_observations": strategy.get("owned_channel_observations", []),
        "week_over_week_changes": strategy.get("week_over_week_changes", {}),
        # Meta
        "advisors_activated": [ADVISOR_ROLE_TITLES.get(a, a) for a in active_advisors],
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Save briefing
      supabase.table("briefings").upsert({
        "client_id": client_id,
        "week_of": week_of,
        "pressure_score": full_report["pressure_score"],
        "summary": full_report["executive_summary"],
        "developments": full_report["top_developments"],
        "full_report": json.dumps(full_report),
        "created_at": datetime.utcnow().isoformat(),
    }, on_conflict="client_id,week_of").execute()

    # Mark emails as analyzed
    if emails:
        mark_emails_analyzed(client_id, week_cutoff)

    print(f"[synthesizer] Briefing saved — Pressure: {full_report['pressure_score']} | Advisors: {full_report['advisors_activated']}")
    return full_report


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python synthesizer.py <client_slug>")
        sys.exit(1)
    result = synthesize_for_client(sys.argv[1])
    if result:
        print(f"\nExecutive Summary: {result.get('executive_summary')}")
        print(f"Strategic Narrative: {result.get('strategic_narrative')}")
        print(f"Top Developments: {len(result.get('top_developments', []))} items")
        print(f"Brand Campaign Signals: {len(result.get('brand_campaign_signals', []))} detected")
        print(f"Advisors activated: {result.get('advisors_activated')}")
