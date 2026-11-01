import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_skill_search_then_projects(client):
    sk = (await client.call_tool("pn_skills", {"query": "python"})).structured_content["skills"]
    assert any(s["slug"] == "python" for s in sk)
    r = (await client.call_tool("pn_search_projects", {"skills": ["python"], "limit": 5})).structured_content
    assert r["total"] > 0 and r["projects"] and all("پایتون (Python)" in p["skills"] for p in r["projects"]), r


async def test_live_project_and_bids(client):
    p = (await client.call_tool("pn_search_projects", {"sort": "fewest_bids", "limit": 1})).structured_content[
        "projects"
    ][0]
    d = (await client.call_tool("pn_project", {"project_id": p["id"]})).structured_content
    assert d["title"] == p["title"] and d["employer"]["username"] and d["description"]
    b = (await client.call_tool("pn_bids", {"project_id": p["id"], "limit": 3})).structured_content
    assert abs(b["total"] - d["bids"]) <= 2 and b["bids"] and b["bids"][0]["price"] > 0


async def test_live_freelancers_and_profile(client):
    r = (await client.call_tool("pn_search_freelancers", {"level": "top", "limit": 3})).structured_content
    assert r["total"] > 10 and all(f["level"] == "TOP_FREELANCER" for f in r["freelancers"])
    u = (await client.call_tool("pn_profile", {"username": r["freelancers"][0]["username"]})).structured_content
    assert u["completed_projects"] > 0 and u["skills"]


async def test_live_categories_and_market(client):
    c = (await client.call_tool("pn_categories", {})).structured_content["categories"]
    assert {x["slug"] for x in c} >= {"dev-and-it", "design-and-creativity"}
    m = (await client.call_tool("pn_market", {"skill": "wordpress"})).structured_content
    assert m["open_projects"] > 0 and m["budget_toman"]["median"] > 0


async def test_live_reviews_portfolios_projects(client):
    r = (await client.call_tool("pn_reviews", {"username": "rohammasmoei", "limit": 3})).structured_content
    assert r["total"] >= 10 and r["summary"]["stars"] and r["reviews"][0]["comment"]
    s = (await client.call_tool("pn_reviews", {"skill": "python", "limit": 3})).structured_content
    assert s["reviews"][0]["ratings"]["quality"]
    p = (await client.call_tool("pn_portfolios", {"skills": ["python"], "limit": 3})).structured_content
    assert p["total"] > 100 and p["items"][0]["by"]
    u = (await client.call_tool("pn_user_projects", {"username": "rohammasmoei", "limit": 3})).structured_content
    assert u["total"] > 10 and u["projects"]


async def test_live_services_and_trend(client):
    s = (await client.call_tool("pn_services", {"sort": "price_low", "limit": 5})).structured_content
    assert s["total"] > 20 and s["services"][0]["price"] <= s["services"][-1]["price"]
    d = (await client.call_tool("pn_service", {"service_id": s["services"][0]["id"]})).structured_content
    assert d["price"] == s["services"][0]["price"]
    t = (await client.call_tool("pn_trend", {"skill": "python", "points": 3})).structured_content
    assert len(t["samples"]) == 3 and t["samples"][0]["median_budget"] > 0
    c = (await client.call_tool("pn_categories", {"with_counts": True})).structured_content["categories"]
    assert all(x["all_projects"] >= x["open_projects"] for x in c)
