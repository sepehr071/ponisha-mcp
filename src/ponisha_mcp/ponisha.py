"""Ponisha tools: project and freelancer search, project details and bids, profiles, skills and categories."""

from __future__ import annotations

import asyncio
import html
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import API, SEARCH, SITE, ApiError, fetch
from .registry import tool

TEHRAN = timezone(timedelta(hours=3, minutes=30))
Skills = Annotated[
    list[str] | None,
    Field(
        description="Skill names, slugs or ids from pn_skills; ALL required.",
        max_length=5,
    ),
]
Limit = Annotated[int, Field(description="Results per page.", ge=1, le=50)]
Page = Annotated[int, Field(description="Page, from 1.", ge=1, le=200)]
ProjectId = Annotated[int, Field(description="Project id.", ge=1)]
Username = Annotated[str, Field(description="Ponisha username.", pattern=r"^[A-Za-z0-9_.-]{2,64}$")]

# Sort ids of ponisha.ir's project list (sort|order of its dropdown).
PROJECT_SORT = {
    # the API ignores sort=approved_at (the site's dropdown value); billboarded_at orders by approval time
    "newest": ("billboarded_at", "desc"),
    "oldest": ("billboarded_at", "asc"),
    "ending_soon": ("bidding_closed_at", "asc"),
    "most_time_left": ("bidding_closed_at", "desc"),
    "most_bids": ("bid_count", "desc"),
    "fewest_bids": ("bid_count", "asc"),
    "most_viewed": ("view_count", "desc"),
}
BIDS_PAGE = {"paginated": "1"}  # without it the bids endpoint returns every bid, minutes on big projects
# Level ids of the freelancer filter (read from search results: level.id).
LEVELS = {"1": 12, "2": 15, "top": 18}


def _when(ts: Any) -> str | None:
    """Epoch seconds or milliseconds -> Tehran-time 'YYYY-MM-DD HH:MM' (Gregorian)."""
    if not ts:
        return None
    ts = ts / 1000 if ts > 1e11 else ts
    return datetime.fromtimestamp(ts, TEHRAN).strftime("%Y-%m-%d %H:%M")


def _snip(text: str | None, n: int = 240) -> str | None:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


async def _skill_list() -> list[dict]:
    return (await fetch(f"{API}/categories/all"))["data"]


async def _skill_ids(names: list[str] | None) -> list[str]:
    """Resolve names, slugs or ids to skill ids; an unknown name is an error with a hint."""
    if not names:
        return []
    allskills = await _skill_list()
    out = []
    for raw in names:
        n = raw.strip().lower()
        hit = next((s for s in allskills if n in (str(s["id"]), s["slug"].lower(), (s["title"] or "").lower())), None)
        hit = hit or next((s for s in allskills if n and n in f"{s['slug']} {s['title'] or ''}".lower()), None)
        if not hit:
            raise ApiError(f"Unknown skill '{raw}'. Call pn_skills to find the exact name.")
        out.append(str(hit["id"]))
    return out


def _project_card(p: dict) -> dict:
    return {
        "id": int(p["id"]),
        "title": p["title"],
        "url": f"{SITE}/project/{p['id']}",
        "budget": {"min": p.get("amount_min"), "max": p.get("amount_max")},
        "bids": p.get("project_bids_count"),
        "skills": [s["title"] for s in p.get("skills", [])],
        "posted": _when(p.get("approved_at")),
        "bidding_ends": _when(p.get("bidding_closed_at")),
        "promotions": [x.get("title") if isinstance(x, dict) else x for x in p.get("promotions", [])] or None,
        "summary": _snip(p.get("description")),
    }


async def _project_search(body: dict) -> dict:
    return await fetch(f"{SEARCH}/projects/search", body=body)


async def _category_id(cat: str) -> str:
    cats = (await fetch(f"{API}/categories"))["data"]
    c = cat.strip().lower()
    hit = next((x for x in cats if c in (str(x["id"]), x["slug"].lower(), x["title"].lower())), None)
    if not hit:
        raise ApiError(f"Unknown category '{cat}'. Call pn_categories for the list.")
    return str(hit["id"])


@tool("Search projects")
async def pn_search_projects(
    query: Annotated[
        str,
        Field(description="Persian or English text. Empty = all.", max_length=200),
    ] = "",
    skills: Skills = None,
    category: Annotated[str | None, Field(description="Top-level category slug or id from pn_categories.")] = None,
    status: Annotated[
        Literal["open", "all"],
        Field(description="open = taking bids; all adds finished/closed."),
    ] = "open",
    min_budget: Annotated[int | None, Field(description="Budget range reaches at least this (Toman).", ge=0)] = None,
    max_budget: Annotated[int | None, Field(description="Budget range starts at or below this (Toman).", ge=0)] = None,
    sort: Annotated[
        Literal["newest", "oldest", "ending_soon", "most_time_left", "most_bids", "fewest_bids", "most_viewed"],
        Field(description="ending_soon = bidding closes first."),
    ] = "newest",
    page: Page = 1,
    limit: Limit = 20,
) -> dict:
    """Search Ponisha projects by text, skills, category, status and budget.

    Returns cards; next pn_project or pn_bids. Budget filters apply client-side to up to 50 projects per page.
    """
    sort_key, order = PROJECT_SORT[sort]
    filtered = min_budget is not None or max_budget is not None
    body = {
        "query": query,
        "page": page,
        "per_page": 50 if filtered else limit,
        "sort": sort_key,
        "order": order,
        "filters": {
            "is_open_projects": status == "open",
            "skills": await _skill_ids(skills),
            "category": [await _category_id(category)] if category else [],
            "promotions": [],
        },
    }
    r = await _project_search(body)
    rows = r["data"]
    if filtered:
        rows = [
            p
            for p in rows
            if (min_budget is None or (p.get("amount_max") or 0) >= min_budget)
            and (max_budget is None or (p.get("amount_min") or 0) <= max_budget)
        ]
    pg = r["meta"]["pagination"]
    return {
        "total": pg["total_items"],
        "page": pg["current_page"],
        "pages": pg["total_pages"],
        "average_bids": r["meta"].get("aggregations", {}).get("average_bids"),
        "budget_unit": "Toman",
        "matched_on_page": len(rows) if filtered else None,
        "projects": [_project_card(p) for p in rows[:limit]],
    }


def _bid_stats(bids: list[dict]) -> dict | None:
    amounts = [b["amount"] for b in bids if b.get("amount")]
    if not amounts:
        return None
    days = [b["days"] for b in bids if b.get("days")]
    return {
        "count": len(bids),
        "min": min(amounts),
        "median": int(statistics.median(amounts)),
        "average": int(statistics.mean(amounts)),
        "max": max(amounts),
        "median_days": statistics.median(days) if days else None,
    }


def _person(u: dict) -> dict:
    lvl = u.get("current_level") or {}
    return {
        "username": u.get("username"),
        "url": f"{SITE}/profile/{u.get('username')}",
        "level": lvl.get("level_fa"),
        "rating": u.get("feedback_rate") or None,
        "reviews": u.get("feedback_count"),
        "verified": u.get("verified"),
    }


@tool("Project details")
async def pn_project(project_id: ProjectId, include_bid_sample: bool = False) -> dict:
    """Get one Ponisha project: full description, budget, skills, deadline and the employer's track record.

    Use after pn_search_projects. Finished projects add accepted_price and done_by. include_bid_sample=true adds
    price stats of the first 20 offers (slow, up to 30 s).
    """
    d = (await fetch(f"{API}/projects/{project_id}"))["data"]
    emp = d.get("employer") or {}
    bids_task = (
        fetch(f"{API}/projects/{project_id}/bids", BIDS_PAGE | {"per_page": 20})
        if include_bid_sample
        else asyncio.sleep(0, None)
    )
    prof_task = fetch(f"{API}/users/{emp['username']}/profile") if emp.get("username") else asyncio.sleep(0, None)
    bids, prof = await asyncio.gather(bids_task, prof_task)
    out: dict[str, Any] = {
        "id": d["id"],
        "title": d["title"],
        "url": f"{SITE}/project/{d['id']}",
        "status": d.get("status"),
        "budget": {"min": d.get("amount_min"), "max": d.get("amount_max"), "unit": "Toman"},
        "bids": d.get("project_bids_count"),
        "priority": d.get("priority"),
        "category": (d.get("skill_category") or {}).get("title"),
        "sub_category": (d.get("skill_sub_category") or {}).get("title"),
        "skills": [s["title"] for s in d.get("skills", [])],
        "posted": _when(d.get("created_at")),
        "bidding_ends": _when(d.get("bidding_ends_at")),
        "promotions": [x.get("title") for x in d.get("promotions", [])] or None,
        "files": len(d.get("files") or []) or None,
        "description": d.get("description"),
    }
    if d.get("accepted_price"):  # finished projects only: what the winner was paid
        out["accepted_price"] = d["accepted_price"]
        out["done_by"] = [u.get("username") for u in d.get("done_by") or []] or None
    out["status_code"] = d.get("status_code")
    if prof:
        p = prof["data"]
        s = p.get("statistics", {})
        out["employer"] = {
            "username": emp.get("username"),
            "url": f"{SITE}/profile/{emp.get('username')}",
            "member_since": _when(p["user"].get("registered_at")),
            "last_seen": p["user"].get("last_activity"),
            "projects_created": s.get("created_projects_count"),
            "projects_completed": s.get("completed_projects_count"),
            "active_projects": s.get("active_projects_count"),
            "rating": s.get("feedback_rate") or None,
            "reviews": s.get("feedback_count"),
            "verified": p["user"].get("verified"),
        }
    if bids:
        out["bid_stats_first_20"] = _bid_stats(bids["data"])
    return out


@tool("Project bids")
async def pn_bids(
    project_id: ProjectId,
    page: Page = 1,
    limit: Annotated[int, Field(description="Per page.", ge=1, le=30)] = 10,
) -> dict:
    """List the offers on a Ponisha project: price (Toman), days, pitch and each bidder's track record.

    Slow (3-30 s on projects with many bids): keep limit small.
    """
    r = await fetch(f"{API}/projects/{project_id}/bids", BIDS_PAGE | {"per_page": limit, "page": page})
    pg = r["meta"]["pagination"]
    return {
        "project_id": project_id,
        "total": pg["total_items"],
        "page": pg["current_page"],
        "pages": pg["total_pages"],
        "stats_this_page": _bid_stats(r["data"]),
        "bids": [
            {
                **_person(b["user"]),
                "price": b["amount"],
                "days": b["days"],
                "status": b["status"],
                "completed_projects": b.get("completed_projects_count"),
                "pitch": _snip(b.get("description"), 300),
                "at": _when(b["created_at"]),
            }
            for b in r["data"]
        ],
    }


@tool("Search freelancers")
async def pn_search_freelancers(
    query: Annotated[str, Field(description="Text. Empty = all.", max_length=200)] = "",
    skills: Skills = None,
    level: Annotated[
        Literal["any", "1", "2", "top"],
        Field(description="Exact level; top = Ponisha's top freelancers."),
    ] = "any",
    has_portfolio: Annotated[bool, Field(description="Only with portfolio items.")] = False,
    sort: Annotated[Literal["rating", "default"], Field(description="rating = total score, highest first.")] = "rating",
    page: Page = 1,
    limit: Limit = 10,
    category: Annotated[str | None, Field(description="Top-level category slug or id from pn_categories.")] = None,
) -> dict:
    """Search Ponisha freelancers by text, skills, category, level and portfolio, ranked by score.

    Cards carry score, rating (0-5) and review count; next pn_profile. No city filter exists.
    """
    filters: dict[str, Any] = {}
    if skills:
        filters["skills"] = await _skill_ids(skills)
    if category:
        filters["category"] = [await _category_id(category)]
    if has_portfolio:
        filters["has_portfolio"] = True
    if level != "any":
        filters["levels"] = [str(LEVELS[level])]
    body = {
        "query": query,
        "page": page,
        "per_page": limit,
        "sort": "rating" if sort == "rating" else "",
        "order": "desc",
        "filters": filters,
    }
    r = await fetch(f"{SEARCH}/freelancers/search", body=body)
    pg = r["meta"]["pagination"]
    return {
        "total": pg["total_items"],
        "page": pg["current_page"],
        "pages": pg["total_pages"],
        "freelancers": [
            {
                "username": f["username"],
                "url": f"{SITE}/profile/{f['username']}",
                "level": (f.get("level") or {}).get("title"),
                "score": f.get("total_score"),
                "rating": round(f["rank"], 2) if f.get("rank") else None,
                "reviews": f.get("employer_feedbacks_count"),
                "portfolio_items": f.get("portfolio_count"),
                "verified": f.get("is_verified"),
                "skills": [s["title"] for s in f.get("skills", [])[:8]],
                "about": _snip(f.get("about"), 200),
            }
            for f in r["data"]
        ],
    }


@tool("User profile")
async def pn_profile(
    username: Username,
    include_resume: Annotated[bool, Field(description="Add work/education history.")] = False,
) -> dict:
    """Get a public Ponisha profile (freelancer or employer): level, skills, statistics, rating and activity.

    Next: pn_reviews, pn_portfolios, pn_user_projects. No contact data.
    """
    d = (await fetch(f"{API}/users/{username}/profile"))["data"]
    u, p, s = d["user"], d.get("profile") or {}, d.get("statistics") or {}
    resume = (await fetch(f"{API}/users/{username}/resume"))["data"] if include_resume else None
    return {
        "username": u["username"],
        "url": f"{SITE}/profile/{u['username']}",
        "type": u.get("type"),
        "level": (u.get("current_level") or {}).get("level_fa"),
        "verified": u.get("verified"),
        "member_since": _when(u.get("registered_at")),
        "last_seen": u.get("last_activity"),
        "online": u.get("is_online"),
        "followers": u.get("followers"),
        "city": (p.get("city") or {}).get("name"),
        "headline": _snip(p.get("job_title"), 200),
        "bio": _snip(p.get("job_description"), 800),
        "skills": [x["title"] for x in d.get("skills", [])],
        "completed_projects": s.get("completed_projects_count"),
        "active_projects": s.get("active_projects_count"),
        "created_projects": s.get("created_projects_count"),
        "rating": s.get("feedback_rate") or None,
        "reviews": s.get("feedback_count"),
        "total_score": s.get("total_score"),
        "portfolio_items": (s.get("portfolios_count") or {}).get("ALL"),
        "profile_views": s.get("profile_views"),
        "typical_response_under_hours": d.get("response_rate"),
        "on_vacation": bool(d.get("vacation")) or None,
        "resume": [
            {
                "type": r.get("type"),
                "title": r.get("title"),
                "place": r.get("place"),
                "from": (r.get("start_date") or "")[:10] or None,
                "to": (r.get("finish_date") or "")[:10] or None,
                "description": _snip(r.get("description"), 200),
            }
            for r in resume
        ]
        if resume is not None
        else None,
    }


@tool("Find skills")
async def pn_skills(
    query: Annotated[
        str,
        Field(
            description="Part of a skill name or slug, Persian or English.",
            min_length=1,
            max_length=60,
        ),
    ],
    limit: Annotated[int, Field(description="Max skills.", ge=1, le=50)] = 20,
) -> dict:
    """Find Ponisha skills (about 700 tags) by name for the skills filters of other tools.

    Pass the returned slug or id as `skills`.
    """
    q = query.strip().lower()
    hits = [s for s in await _skill_list() if q in f"{s['slug']} {s['title'] or ''}".lower()]
    return {
        "found": len(hits),
        "skills": [{"id": s["id"], "slug": s["slug"], "title": s["title"] or s["slug"]} for s in hits[:limit]],
    }


@tool("Categories")
async def pn_categories(
    slug: Annotated[str | None, Field(description="Top-level slug: list its sub-categories.")] = None,
    with_counts: Annotated[bool, Field(description="Add project counts per category (14 searches).")] = False,
) -> dict:
    """List Ponisha's top-level project categories, or the sub-categories of one.

    Top-level slugs/ids are the `category` value of the search tools.
    """
    if slug:
        d = (await fetch(f"{API}/categories/subs-with-slug/{slug}"))["data"]
        return {
            "category": d["title"],
            "slug": d["slug"],
            "subs": [{"slug": s["slug"], "title": s["title"].strip()} for s in d["subs"]],
        }
    cats = (await fetch(f"{API}/categories"))["data"]
    counts: dict[tuple, int] = {}
    if with_counts:
        keys = [(c["id"], is_open) for c in cats for is_open in (True, False)]
        bodies = [
            {
                "query": "",
                "page": 1,
                "per_page": 1,
                "sort": "billboarded_at",
                "order": "desc",
                "filters": {"is_open_projects": o, "skills": [], "category": [str(i)], "promotions": []},
            }
            for i, o in keys
        ]
        for k, r in zip(keys, await asyncio.gather(*map(_project_search, bodies)), strict=True):
            counts[k] = r["meta"]["pagination"]["total_items"]
    return {
        "categories": [
            {"id": c["id"], "slug": c["slug"], "title": c["title"]}
            | ({"open_projects": counts[(c["id"], True)], "all_projects": counts[(c["id"], False)]} if counts else {})
            for c in cats
        ]
    }


@tool("Skill market")
async def pn_market(
    skill: Annotated[str, Field(description="One skill name, slug or id from pn_skills.", max_length=60)],
) -> dict:
    """Summarize demand and supply for one skill on Ponisha: open projects, budgets, competition, related skills.

    Based on the 50 newest open projects (budgets in Toman, medians of midpoints) and the freelancer count.
    """
    sid = (await _skill_ids([skill]))[0]
    pbody = {
        "query": "",
        "page": 1,
        "per_page": 50,
        "sort": "billboarded_at",  # the API ignores approved_at; this orders by approval time
        "order": "desc",
        "filters": {"is_open_projects": True, "skills": [sid], "category": [], "promotions": []},
    }
    fbody = {"query": "", "page": 1, "per_page": 1, "sort": "rating", "order": "desc", "filters": {"skills": [sid]}}
    pr, fr = await asyncio.gather(_project_search(pbody), fetch(f"{SEARCH}/freelancers/search", body=fbody))
    rows = pr["data"]
    mids = sorted((p["amount_min"] + p["amount_max"]) / 2 for p in rows if p.get("amount_max"))
    bids = [p["project_bids_count"] for p in rows]
    related: dict[str, int] = {}
    for p in rows:
        for s in p["skills"]:
            if str(s["id"]) != sid:
                related[s["title"]] = related.get(s["title"], 0) + 1
    q = statistics.quantiles(mids, n=4) if len(mids) >= 4 else None
    return {
        "skill": skill,
        "open_projects": pr["meta"]["pagination"]["total_items"],
        "sampled": len(rows),
        "budget_toman": {"p25": int(q[0]), "median": int(q[1]), "p75": int(q[2])} if q else None,
        "median_bids": statistics.median(bids) if bids else None,
        "average_bids_all_open": pr["meta"].get("aggregations", {}).get("average_bids"),
        "freelancers_with_skill": fr["meta"]["pagination"]["total_items"],
        "related_skills": sorted(related, key=related.get, reverse=True)[:8],
    }


def _by(u: dict) -> dict:
    return {"username": u.get("username"), "reviews": u.get("feedback_count")}


def _project_ref(p: dict) -> dict:
    return {"id": p.get("id"), "title": p.get("title")}


@tool("Reviews")
async def pn_reviews(
    username: Annotated[
        str | None,
        Field(description="Reviews received by this user.", pattern=r"^[A-Za-z0-9_.-]{2,64}$"),
    ] = None,
    skill: Annotated[str | None, Field(description="Instead of username: recent reviews for a skill.")] = None,
    page: Page = 1,
    limit: Annotated[int, Field(description="Per page.", ge=1, le=30)] = 10,
) -> dict:
    """Read the reviews employers wrote about a Ponisha user, or recent reviews for a whole skill.

    Give exactly one of username or skill. A user also gets a score summary (stars, averages, success rate).
    Skill mode reaches the newest 2000 reviews.
    """
    if bool(username) == bool(skill):
        raise ApiError("Give exactly one of username or skill.")
    q = {"paginated": "1", "per_page": limit, "page": page}
    if skill:
        sid = (await _skill_ids([skill]))[0]
        r = await fetch(f"{API}/projects/desks/reviews_by_skill/{sid}", q)
        pg = r["meta"]["pagination"]
        return {
            "skill": skill,
            "total": pg["total_items"],
            "page": pg["current_page"],
            "pages": pg["total_pages"],
            "reviews": [
                {
                    "ratings": {
                        k: b.get(k) for k in ("quality", "communication", "timeline", "expertise", "hire_again")
                    },
                    "comment": _snip(b.get("comment"), 400),
                    "by": _by(b.get("user") or {}),
                    "project": _project_ref(b.get("project") or {}),
                }
                for b in r["data"]
            ],
        }
    r, f = await asyncio.gather(fetch(f"{API}/users/{username}/comments", q), fetch(f"{API}/users/{username}/feedback"))
    pg, f = r["meta"]["pagination"], f["data"]
    avg = {k.removesuffix("_avg"): float(v) for k, v in f["detailed_averages"].items()}
    return {
        "username": username,
        "summary": {
            "stars": {k.removeprefix("star_"): v for k, v in f["stars"].items()},
            "averages": avg,
            "success_rate_percent": float(f["success_rate"]) or None,
        },
        "total": pg["total_items"],
        "page": pg["current_page"],
        "pages": pg["total_pages"],
        "reviews": [
            {
                "rating": c.get("rank"),
                "comment": _snip(c.get("comment"), 400),
                "by": _by(c.get("user") or {}),
                "project": _project_ref(c.get("project") or {}),
                "at": _when(c.get("created_at")),
            }
            for c in r["data"]
        ],
    }


def _plain(text: str | None, n: int = 240) -> str | None:
    return _snip(html.unescape(re.sub(r"<[^>]+>", " ", text or "")), n)


@tool("Portfolios")
async def pn_portfolios(
    query: Annotated[str, Field(description="Text. Empty = all.", max_length=200)] = "",
    skills: Skills = None,
    category: Annotated[str | None, Field(description="Category slug or id (search mode only).")] = None,
    username: Annotated[
        str | None,
        Field(description="List this user's portfolio instead of searching.", pattern=r"^[A-Za-z0-9_.-]{2,64}$"),
    ] = None,
    page: Page = 1,
    limit: Annotated[int, Field(description="Per page.", ge=1, le=30)] = 10,
) -> dict:
    """Search Ponisha portfolio items (about 500k work samples), or list one user's portfolio.

    Search is ranked by quality score. With username, query/skills are ignored and only titles and links return.
    """
    if username:
        r = await fetch(f"{API}/users/{username}/portfolio/list", {"paginated": "1", "per_page": limit, "page": page})
        pg = r["meta"]["pagination"]
        items = [
            {"id": p["id"], "title": p["title"], "url": f"{SITE}/profile/{username}/portfolio/{p['id']}"}
            for p in r["data"]
        ]
    else:
        body = {
            "query": query,
            "page": page,
            "per_page": limit,
            "sort": "score",  # other sort values are ignored by the API
            "order": "desc",
            "filters": {
                "skills": await _skill_ids(skills),
                "tags": [],
                "category": [await _category_id(category)] if category else [],
            },
        }
        r = await fetch(f"{SEARCH}/portfolios/search", body=body)
        pg = r["meta"]["pagination"]
        items = [
            {
                "id": int(p["id"]),
                "title": p["title"],
                "url": f"{SITE}/profile/{p['user']['username']}/portfolio/{p['id']}",
                "by": p["user"]["username"],
                "views": p.get("views"),
                "likes": p.get("likes"),
                "skills": [s["title"] for s in p.get("skills", [])[:6]],
                "summary": _plain(p.get("description")),
            }
            for p in r["data"]
        ]
    return {"total": pg["total_items"], "page": pg["current_page"], "pages": pg["total_pages"], "items": items}


SERVICE_SORT = {
    "popular": ("done_projects", "desc"),
    "price_low": ("price", "asc"),
    "price_high": ("price", "desc"),
    "rating": ("score", "desc"),
}


def _service_card(c: dict) -> dict:
    cat = c.get("skill_category") or {}
    return {
        "id": c["id"],
        "title": c["title"],
        "url": f"{SITE}/services/product/{c['id']}/{c['slug']}",
        "seller": _person(c.get("user") or {}),
        "category": {"id": cat.get("id"), "slug": cat.get("slug"), "title": cat.get("title")},
        "price": c.get("basic_price"),
        "delivery": c.get("display_time"),
        "capacity": c.get("freelancer_project_capacity"),
        "summary": _plain(c.get("description"), 200),
    }


@tool("Service packages")
async def pn_services(
    query: Annotated[str, Field(description="Words in name or description. Empty = all.", max_length=100)] = "",
    category: Annotated[
        str | None, Field(description="Service category slug, id or name part, e.g. logo-design (see `categories`).")
    ] = None,
    min_price: Annotated[int | None, Field(description="Min package price (Toman).", ge=0)] = None,
    max_price: Annotated[int | None, Field(description="Max package price (Toman).", ge=0)] = None,
    min_rating: Annotated[float | None, Field(description="Min seller rating (0-5).", ge=0, le=5)] = None,
    sort: Annotated[
        Literal["popular", "price_low", "price_high", "rating"],
        Field(description="popular = most finished projects."),
    ] = "popular",
    page: Page = 1,
    limit: Annotated[int, Field(description="Per page.", ge=1, le=30)] = 10,
) -> dict:
    """Browse Ponisha's ready-made fixed-price service packages (logo design, WordPress themes, ...).

    About 80 packages; prices in Toman. Next: pn_service.
    """
    q: dict[str, Any] = {"order_by": SERVICE_SORT[sort][0], "sort_by": SERVICE_SORT[sort][1], "per_page": 50}
    for key, val in (("basic_price_min", min_price), ("basic_price_max", max_price), ("score", min_rating)):
        if val:
            q[f"filter[{key}]"] = val
    first = await fetch(f"{API}/catalogs", q | {"page": 1})
    rows = first["data"]
    last = first["meta"]["pagination"]["total_pages"]
    for r in await asyncio.gather(*(fetch(f"{API}/catalogs", q | {"page": n}) for n in range(2, last + 1))):
        rows += r["data"]
    cats: dict[int, dict] = {}
    for c in rows:
        k = (c.get("skill_category") or {}).get("id")
        cats.setdefault(
            k, {"id": k, "slug": c["skill_category"]["slug"], "title": c["skill_category"]["title"], "count": 0}
        )
        cats[k]["count"] += 1
    if category:
        n = category.strip().lower()
        rows = [
            c
            for c in rows
            if n in (str(c["skill_category"]["id"]), c["skill_category"]["slug"].lower())
            or n in c["skill_category"]["title"].lower()
        ]
    if query:
        words = query.lower().split()
        rows = [c for c in rows if all(w in f"{c['title']} {c.get('description') or ''}".lower() for w in words)]
    start = (page - 1) * limit
    return {
        "total": len(rows),
        "page": page,
        "categories": list(cats.values()),
        "services": [_service_card(c) for c in rows[start : start + limit]],
    }


@tool("Service package details")
async def pn_service(service_id: Annotated[int, Field(description="Package id.", ge=1)]) -> dict:
    """Get one Ponisha service package: price (Toman), delivery time, inclusions, requirements and add-ons."""
    c = (await fetch(f"{API}/catalogs/{service_id}"))["data"]
    return _service_card(c) | {
        "description": _plain(c.get("description"), 1500),
        "delivery_days": c.get("basic_delivery_days"),
        "includes": c.get("deliverable_items"),
        "requirements": c.get("requirements"),
        "extras": [
            {"title": x["title"], "price": x["price"], "days": x.get("required_time_in_day_unit")}
            for x in c.get("extra_services", [])
        ],
        "options": {p["title"]: [v["title"] for v in p.get("values", [])] for p in c.get("properties", [])},
        "industries": [i["title"] for i in c.get("industries", [])],
        "skills": [s["title"] for s in c.get("skills", [])],
        "work_samples": [w.get("name") for w in c.get("work_samples", [])] or None,
    }


@tool("User projects")
async def pn_user_projects(
    username: Username,
    status: Annotated[
        Literal["finished", "open"],
        Field(description="finished = completed; open = taking bids."),
    ] = "finished",
    page: Page = 1,
    limit: Annotated[int, Field(description="Projects per page (max 30).", ge=1, le=30)] = 10,
) -> dict:
    """List the projects a Ponisha user is attached to: an employer's own or a freelancer's finished work.

    Next: pn_project for the brief and accepted price.
    """
    code = {"finished": 100, "open": 30}[status]
    r = await fetch(
        f"{API}/projects/{username}/list", {"status": code, "paginated": "1", "per_page": limit, "page": page}
    )
    pg = r["meta"]["pagination"]
    return {
        "username": username,
        "status": status,
        "total": pg["total_items"],
        "page": pg["current_page"],
        "pages": pg["total_pages"],
        "projects": [
            {
                "id": p["id"],
                "title": p["title"],
                "url": f"{SITE}/project/{p['id']}",
                "posted": _when(p.get("created_at")),
                "skills": [s["title"] for s in p.get("skills", [])],
            }
            for p in r["data"]
        ],
    }


@tool("Skill trend")
async def pn_trend(
    skill: Annotated[str, Field(description="One skill name, slug or id from pn_skills.", max_length=60)],
    points: Annotated[int, Field(description="History samples (50 projects each).", ge=2, le=8)] = 5,
) -> dict:
    """Show how demand and budgets for one skill changed over time on Ponisha, newest to oldest.

    Samples `points` pages of 50 projects (all statuses) across the newest 10000: period, posts per month, median
    budget (Toman) and bids. For today's numbers use pn_market.
    """
    sid = (await _skill_ids([skill]))[0]

    async def sample(n: int) -> dict:
        body = {
            "query": "",
            "page": n,
            "per_page": 50,
            "sort": "billboarded_at",
            "order": "desc",
            "filters": {"is_open_projects": False, "skills": [sid], "category": [], "promotions": []},
        }
        return await _project_search(body)

    first = await sample(1)
    total, pages = first["meta"]["pagination"]["total_items"], first["meta"]["pagination"]["total_pages"]
    wanted = sorted({round(1 + i * (pages - 1) / (points - 1)) for i in range(points)}) if pages > 1 else [1]
    out = []
    fetched = await asyncio.gather(*(sample(n) for n in wanted if n != 1))
    for n in wanted:
        rows = first["data"] if n == 1 else fetched.pop(0)["data"]
        times = [t / 1000 if t > 1e11 else t for t in (p.get("approved_at") for p in rows) if t]
        mids = [(p["amount_min"] + p["amount_max"]) / 2 for p in rows if p.get("amount_max")]
        days = max((max(times) - min(times)) / 86400, 1) if times else None
        out.append(
            {
                "from": _when(min(times)) if times else None,
                "to": _when(max(times)) if times else None,
                "projects_per_month": round(len(rows) / days * 30) if days and len(rows) == 50 else None,
                "median_budget": int(statistics.median(mids)) if mids else None,
                "median_bids": statistics.median([p["project_bids_count"] for p in rows]) if rows else None,
                "sample_size": len(rows),
            }
        )
    return {"skill": skill, "all_time_projects": total, "budget_unit": "Toman", "samples": out}
