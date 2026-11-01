import json

import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

TOOLS = {
    "pn_search_projects",
    "pn_project",
    "pn_bids",
    "pn_search_freelancers",
    "pn_profile",
    "pn_skills",
    "pn_categories",
    "pn_market",
    "pn_reviews",
    "pn_portfolios",
    "pn_services",
    "pn_service",
    "pn_user_projects",
    "pn_trend",
}
A = "/api/v1"


def body(call):
    return json.loads(call.content)


@pytest.fixture
def site(api):
    api["/v1/projects/search"] = fixture("projects.json")
    api["/v1/freelancers/search"] = fixture("freelancers.json")
    api[f"{A}/categories/all"] = fixture("skills.json")
    api[f"{A}/categories"] = fixture("categories.json")
    api[f"{A}/projects/762909"] = fixture("project.json")
    api[f"{A}/projects/762909/bids"] = fixture("bids.json")
    api[f"{A}/users/Nexdigital/profile"] = fixture("profile.json")
    api[f"{A}/users/rohammasmoei/profile"] = fixture("profile2.json")
    api[f"{A}/users/rohammasmoei/comments"] = fixture("comments.json")
    api[f"{A}/users/rohammasmoei/feedback"] = fixture("feedback.json")
    api[f"{A}/users/rohammasmoei/resume"] = fixture("resume.json")
    api[f"{A}/users/rohammasmoei/portfolio/list"] = fixture("portfolio_list.json")
    api[f"{A}/projects/rohammasmoei/list"] = fixture("user_projects.json")
    api[f"{A}/projects/desks/reviews_by_skill/102"] = fixture("reviews_by_skill.json")
    api["/v1/portfolios/search"] = fixture("portfolios.json")
    api[f"{A}/catalogs"] = fixture("catalogs.json")
    api[f"{A}/catalogs/762"] = fixture("catalog.json")
    return api


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.title and t.description.splitlines()[0].endswith("."), t.name
        assert "title" not in str(t.input_schema.get("properties", {}).values()), t.name


async def test_search_projects_resolves_skill_and_category(client, site):
    r = (
        await client.call_tool(
            "pn_search_projects", {"query": "x", "skills": ["python"], "category": "dev-and-it", "sort": "most_bids"}
        )
    ).structured_content
    b = body(site.calls[-1])
    assert b["filters"] == {"is_open_projects": True, "skills": ["102"], "category": ["1"], "promotions": []}
    assert (b["sort"], b["order"], b["query"]) == ("bid_count", "desc", "x")
    p = r["projects"][0]
    assert p["url"].endswith(f"/project/{p['id']}") and p["budget"]["min"] <= p["budget"]["max"]
    assert r["budget_unit"] == "Toman" and len(p["summary"]) <= 240


async def test_search_projects_budget_filter_scans_50(client, site):
    r = (await client.call_tool("pn_search_projects", {"min_budget": 10**12})).structured_content
    assert body(site.calls[-1])["per_page"] == 50
    assert r["projects"] == [] and r["matched_on_page"] == 0


async def test_unknown_skill_is_a_clear_error(client, site):
    r = await client.call_tool("pn_search_projects", {"skills": ["zzz-nope"]})
    assert r.is_error and "pn_skills" in r.content[0].text


async def test_project_has_employer_and_optional_bid_sample(client, site):
    r = (await client.call_tool("pn_project", {"project_id": 762909})).structured_content
    assert r["employer"]["username"] == "Nexdigital" and r["employer"]["projects_created"] == 3
    assert "bid_stats_first_20" not in r and not [c for c in site.calls if c.url.path.endswith("/bids")]
    assert r["posted"].startswith("2026-10-31") and r["budget"]["unit"] == "Toman"
    r = (await client.call_tool("pn_project", {"project_id": 762909, "include_bid_sample": True})).structured_content
    s = r["bid_stats_first_20"]
    assert s["min"] <= s["median"] <= s["max"]
    assert site.calls[-1].url.params["paginated"] == "1" or any(
        c.url.params.get("paginated") == "1" for c in site.calls
    )


async def test_bids_are_paginated(client, site):
    r = (await client.call_tool("pn_bids", {"project_id": 762909, "page": 2, "limit": 3})).structured_content
    q = site.calls[-1].url.params
    assert (q["paginated"], q["per_page"], q["page"]) == ("1", "3", "2")
    assert (
        r["total"] == 4 and r["bids"][0]["price"] > 0 and r["bids"][0]["url"].startswith("https://ponisha.ir/profile/")
    )


async def test_freelancers_level_and_skill_filters(client, site):
    r = (
        await client.call_tool("pn_search_freelancers", {"skills": ["python"], "level": "top", "has_portfolio": True})
    ).structured_content
    assert body(site.calls[-1])["filters"] == {"skills": ["102"], "has_portfolio": True, "levels": ["18"]}
    f = r["freelancers"][0]
    assert f["level"] == "TOP_FREELANCER" and 0 < f["rating"] <= 5 and f["score"] > 0


async def test_profile(client, site):
    r = (await client.call_tool("pn_profile", {"username": "rohammasmoei"})).structured_content
    assert r["level"] and r["completed_projects"] == 23 and r["portfolio_items"] == 57


async def test_skills_and_categories(client, site):
    r = (await client.call_tool("pn_skills", {"query": "PYTH"})).structured_content
    assert r["skills"] == [{"id": 102, "slug": "python", "title": "پایتون (Python)"}]
    c = (await client.call_tool("pn_categories", {})).structured_content
    assert c["categories"][0]["slug"] == "dev-and-it"


async def test_market(client, site):
    r = (await client.call_tool("pn_market", {"skill": "python"})).structured_content
    assert r["sampled"] == 3 and r["open_projects"] >= 3 and r["freelancers_with_skill"] > 0
    assert body(site.calls[-1])["filters"]["skills"] == ["102"]


async def test_reviews_for_user_and_skill(client, site):
    r = (await client.call_tool("pn_reviews", {"username": "rohammasmoei", "limit": 3})).structured_content
    assert r["summary"]["stars"]["5"] == 9 and r["summary"]["averages"]["quality"] == 4.4667
    assert r["reviews"][0]["comment"] and r["reviews"][0]["by"]["username"] and r["reviews"][0]["at"]
    r = (await client.call_tool("pn_reviews", {"skill": "python"})).structured_content
    assert r["reviews"][0]["ratings"]["quality"] and site.calls[-1].url.params["paginated"] == "1"
    bad = await client.call_tool("pn_reviews", {})
    assert bad.is_error


async def test_portfolios_search_and_user_list(client, site):
    r = (
        await client.call_tool("pn_portfolios", {"query": "x", "skills": ["python"], "category": "dev-and-it"})
    ).structured_content
    b = body(site.calls[-1])
    assert b["filters"] == {"skills": ["102"], "tags": [], "category": ["1"]} and b["sort"] == "score"
    i = r["items"][0]
    assert i["url"] == f"https://ponisha.ir/profile/{i['by']}/portfolio/{i['id']}" and "<" not in i["summary"]
    r = (await client.call_tool("pn_portfolios", {"username": "rohammasmoei", "limit": 3})).structured_content
    assert r["total"] == 57 and r["items"][0]["url"].startswith("https://ponisha.ir/profile/rohammasmoei/portfolio/")


async def test_services_filters_and_detail(client, site):
    r = (
        await client.call_tool("pn_services", {"min_price": 100, "min_rating": 4.5, "sort": "price_low"})
    ).structured_content
    q = site.calls[-1].url.params
    assert q["filter[basic_price_min]"] == "100" and q["filter[score]"] == "4.5" and q["order_by"] == "price"
    assert r["total"] == 3 and r["categories"] and r["services"][0]["price"] > 0
    none = (await client.call_tool("pn_services", {"category": "zzz-nope"})).structured_content
    assert none["total"] == 0
    d = (await client.call_tool("pn_service", {"service_id": 762})).structured_content
    assert d["extras"][0]["price"] > 0 and d["includes"] and d["seller"]["username"] == "arvandec"


async def test_user_projects_status_code(client, site):
    r = (await client.call_tool("pn_user_projects", {"username": "rohammasmoei", "limit": 3})).structured_content
    assert site.calls[-1].url.params["status"] == "100" and r["total"] == 23 and r["projects"][0]["url"]


async def test_trend_samples_spread_over_pages(client, site):
    r = (await client.call_tool("pn_trend", {"skill": "python", "points": 3})).structured_content
    pages = [body(c)["page"] for c in site.calls if c.url.path == "/v1/projects/search"]
    assert pages[-2:] == [4, 7] and len(r["samples"]) == 3 and r["samples"][0]["median_budget"] > 0


async def test_category_counts_and_freelancer_category(client, site):
    r = (await client.call_tool("pn_categories", {"with_counts": True})).structured_content
    assert r["categories"][0]["open_projects"] == 19 and r["categories"][0]["all_projects"] == 19
    await client.call_tool("pn_search_freelancers", {"category": "dev-and-it"})
    assert body(site.calls[-1])["filters"]["category"] == ["1"]


async def test_requests_look_like_the_site_frontend(client, site):
    await client.call_tool("pn_project", {"project_id": 762909})
    await client.call_tool("pn_search_projects", {})
    sent = {r.url.host: r.headers for r in site.calls}
    for h in sent.values():
        assert h["accept"] == "application/json, text/plain, */*" and h["content-type"] == "application/json"
        assert h["origin"] == "https://ponisha.ir" and h["referer"] == "https://ponisha.ir/"
        assert h["sec-fetch-site"] == "same-site" and h["sec-fetch-mode"] == "cors" and h["priority"] == "u=1, i"
    assert set(sent) == {"api.ponisha.ir", "search.ponisha.ir"}
