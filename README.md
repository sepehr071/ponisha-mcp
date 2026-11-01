<!-- mcp-name: io.github.sepehr071/ponisha-mcp -->

# ponisha-mcp: Ponisha (پونیشا) freelance marketplace MCP server for AI agents

**ponisha-mcp is an unofficial, read-only MCP server that gives AI agents the public data of Ponisha (ponisha.ir), Iran's freelance marketplace.**<br>
Its 14 tools search projects (text, skills, category, budget, sort), show a project with the employer's track record, list the offers made on it, search freelancers, read profiles, reviews and portfolios, browse fixed-price service packages, and summarize demand, budgets and trends for a skill.<br>
No API key or Ponisha account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[For AI agents](#for-ai-agents) · [Quick start](#quick-start) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for ponisha.ir: project search, project details, bids, freelancer search, public profiles, skills and categories, skill market summary.
- **Install:** `uvx ponisha-mcp` or `claude mcp add ponisha -- uvx ponisha-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none. Optional `PONISHA_MCP_PROXY` (HTTP proxy URL, or a comma-separated list); system proxy settings are ignored.
- **Access:** read-only. It cannot log in, bid, post projects or message anyone, so no confirmation is needed before calling any tool.
- **Tools:** 14, all prefixed `pn_`. Typical sequences: `pn_skills` -> `pn_search_projects` -> `pn_project` -> `pn_bids`; `pn_search_freelancers` -> `pn_profile`; `pn_skills` -> `pn_market` / `pn_trend`; `pn_profile` -> `pn_reviews` + `pn_portfolios`; `pn_services` -> `pn_service`.
- **Use when:** the user wants freelance projects to bid on in Iran, what a kind of work pays, how crowded a project is, whether an employer is reliable, or who to hire for a skill.
- **Do not use when:** the user wants to apply, message or post (read-only), or needs private contact data.
- **Output:** compact JSON. Money is Toman. Times are Tehran time. Text is Persian user content.

## Quick start

```bash
claude mcp add ponisha -- uvx ponisha-mcp
```

Any MCP client: command `uvx`, args `["ponisha-mcp"]`.

## Tools

| Tool | What it does |
|---|---|
| `pn_search_projects` | Projects by text, skills, category, open/all, budget range, sort. |
| `pn_project` | One project: brief, budget, deadline, employer track record, optional bid price sample. |
| `pn_bids` | Offers on a project: price, days, pitch, bidder level and rating (paged). |
| `pn_search_freelancers` | Freelancers by text, skills, level, portfolio, ranked by score. |
| `pn_profile` | Public profile of a freelancer or employer. |
| `pn_skills` | Skill name -> slug/id (about 700 skills). |
| `pn_categories` | Top-level categories, or the sub-categories of one. |
| `pn_market` | Open projects, budget quartiles, competition and related skills for one skill. |
| `pn_trend` | Posting rate, median budget and bids for a skill sampled across its whole history. |
| `pn_reviews` | Reviews of a user with score breakdown, or recent reviews for a skill. |
| `pn_portfolios` | Search about 500k portfolio items, or list one user's. |
| `pn_services` | Fixed-price service packages by category, price, rating. |
| `pn_service` | One package: deliverables, requirements, paid add-ons. |
| `pn_user_projects` | An employer's or freelancer's finished/open projects. |

## FAQ

**Is it official?** No. It reads the same public API the ponisha.ir web app uses for anonymous visitors.

**Why are bids slow?** Ponisha serves the bids list slowly (seconds, up to 30 s on projects with 100+ bids). Keep `limit` small.

**Why does the budget filter only look at one page?** The site has no budget filter. The tool scans up to 50 projects per page and keeps those whose range fits.

## فارسی

**ponisha-mcp** یک سرور MCP غیررسمی و فقط‌خواندنی برای پونیشا (ponisha.ir) است. با آن می‌توانید پروژه‌ها را با کلمه، مهارت، دسته و بودجه جستجو کنید، پیشنهادهای ثبت‌شده و سابقه کارفرما را ببینید، فریلنسرها و پروفایل‌های عمومی را جستجو کنید و وضعیت بازار یک مهارت را بسنجید. بدون کلید API و حساب کاربری. نصب: `uvx ponisha-mcp`.

مبلغ‌ها به تومان و زمان‌ها به وقت تهران (میلادی) هستند. این ابزار ثبت پیشنهاد، پیام یا ثبت پروژه انجام نمی‌دهد.

Author: Sepehr Radmard (سپهر رادمرد) · github.com/sepehr071 · linkedin.com/in/sepehr-radmard
