# Feed Prism — Public API Documentation

> **Base URL:** `https://feed-prism.vercel.app/api/v1`
>
> **Version:** v1 &nbsp;|&nbsp; **Auth:** API Key &nbsp;|&nbsp; **Rate Limit:** 60 requests/minute

---

## Table of Contents

- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Endpoints](#endpoints)
  - [GET /api/v1/articles](#get-apiv1articles)
- [Query Parameters](#query-parameters)
- [Response Format](#response-format)
- [Available Categories](#available-categories)
- [Available Sources](#available-sources)
- [Use Cases & Examples](#use-cases--examples)
  - [1. Fetch All Articles (Default)](#1-fetch-all-articles-default)
  - [2. Filter by a Single Category](#2-filter-by-a-single-category)
  - [3. Filter by Multiple Categories](#3-filter-by-multiple-categories)
  - [4. Filter by Specific Sources](#4-filter-by-specific-sources)
  - [5. Combine Categories + Sources](#5-combine-categories--sources)
  - [6. Custom Pagination](#6-custom-pagination)
  - [7. Build a Tech News Dashboard](#7-build-a-tech-news-dashboard)
  - [8. Monitor Cybersecurity Threats](#8-monitor-cybersecurity-threats)
  - [9. Track AI Research & Tools](#9-track-ai-research--tools)
  - [10. Build a Financial News Ticker](#10-build-a-financial-news-ticker)
  - [11. Health Outbreak Monitoring](#11-health-outbreak-monitoring)
  - [12. Full-Stack Integration (React)](#12-full-stack-integration-react)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## Quick Start

```bash
# 1. Get your API key from the Developer Portal:
#    https://feed-prism.vercel.app/dashboard/developers

# 2. Make your first request:
curl -X GET "https://feed-prism.vercel.app/api/v1/articles" \
  -H "x-api-key: YOUR_API_KEY"
```

That's it. You'll receive a JSON response with the latest news articles.

---

## Authentication

All requests require an **API key** passed via the `x-api-key` header.

| Header       | Required | Description                          |
|--------------|----------|--------------------------------------|
| `x-api-key`  | ✅ Yes   | Your Feed Prism API key              |

### Getting Your API Key

1. Log in to [Feed Prism](https://feed-prism.vercel.app/login)
2. Navigate to **Dashboard → Developers**
3. Click **"Generate API Key"**
4. Copy your key (format: `fp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

> ⚠️ **Keep your API key secret.** Do not expose it in client-side code, public repositories, or URLs. Always use it server-side or via environment variables.

### Authentication Errors

| HTTP Status | Meaning                           |
|-------------|-----------------------------------|
| `401`       | Missing `x-api-key` header        |
| `403`       | Invalid or revoked API key         |

---

## Rate Limiting

Your API key is rate-limited to **60 requests per minute** using a sliding window.

When you exceed the limit, you'll receive:

```json
{
  "status": "error",
  "error": "Rate limit exceeded. Maximum 60 requests per minute."
}
```

**Rate limit headers** are included in 429 responses:

| Header                  | Description                                    |
|-------------------------|------------------------------------------------|
| `X-RateLimit-Limit`     | Maximum requests allowed per window            |
| `X-RateLimit-Remaining` | Remaining requests in the current window       |
| `X-RateLimit-Reset`     | Unix timestamp when the window resets          |

---

## Endpoints

### GET /api/v1/articles

Retrieve news articles with optional filtering by category and source.

**Quality Filter:** All articles returned are guaranteed to have a body (description) of **at least 20 words**. Short stubs and empty articles are automatically excluded.

```
GET /api/v1/articles?categories=Technology&limit=10&page=1
```

---

## Query Parameters

| Parameter    | Type     | Default | Range   | Description                                          |
|--------------|----------|---------|---------|------------------------------------------------------|
| `categories` | `string` | —       | —       | Comma-separated list of category names to filter by  |
| `sources`    | `string` | —       | —       | Comma-separated list of source UUIDs to filter by    |
| `page`       | `number` | `1`     | ≥ 1     | Page number for pagination                           |
| `limit`      | `number` | `20`    | 1–50    | Number of articles per page                          |

- **No filters** = returns all articles across all categories and sources
- **Multiple categories** = `?categories=Technology,Security,AI %26 ML`
- **Multiple sources** = `?sources=uuid1,uuid2,uuid3`
- **Combine both** = `?categories=Technology&sources=uuid1,uuid2`

> **Note:** The `&` character in category names like `AI & ML` must be URL-encoded as `%26` in query strings.

---

## Response Format

### Success Response (200)

```json
{
  "status": "success",
  "data": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "OpenAI Announces GPT-5 with Real-Time Reasoning",
      "body": "OpenAI has unveiled GPT-5, its most advanced language model to date, featuring real-time reasoning capabilities and improved factual accuracy across scientific and mathematical domains...",
      "url": "https://example.com/article/openai-gpt5",
      "published_at": "2026-05-09T08:30:00+00:00",
      "category": "AI & ML",
      "source_id": "aaa6c343-5c7e-4f30-8407-e31337b847f5",
      "sources": {
        "name": "OpenAI Blog"
      }
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 1542,
    "totalPages": 78,
    "filter": "summary >= 20 words"
  }
}
```

### Response Fields

#### Article Object

| Field          | Type     | Description                                      |
|----------------|----------|--------------------------------------------------|
| `id`           | `string` | Unique article identifier (UUID)                 |
| `title`        | `string` | Article headline                                 |
| `body`         | `string` | Article description/summary (≥ 20 words)         |
| `url`          | `string` | Original article URL                             |
| `published_at` | `string` | ISO 8601 publication timestamp                   |
| `category`     | `string` | News category                                    |
| `source_id`    | `string` | Source identifier (UUID)                          |
| `sources`      | `object` | Nested source info                               |
| `sources.name` | `string` | Human-readable source name                       |

#### Meta Object

| Field        | Type     | Description                                       |
|--------------|----------|---------------------------------------------------|
| `page`       | `number` | Current page number                                |
| `limit`      | `number` | Articles per page                                  |
| `total`      | `number` | Estimated total matching articles                  |
| `totalPages` | `number` | Estimated total pages                              |
| `filter`     | `string` | Active quality filter description                  |

---

## Available Categories

Feed Prism organizes news into **12 categories**. Use the exact names below (case-sensitive) in the `categories` parameter.

| # | Category                    | Description                                      |
|---|------------------------------|--------------------------------------------------|
| 1 | `Technology`                 | General tech news, gadgets, and industry trends   |
| 2 | `AI & ML`                    | Artificial intelligence and machine learning research |
| 3 | `Global News`                | International news and world events              |
| 4 | `Outbreaks & Health`         | Health emergencies, disease outbreaks, WHO/CDC   |
| 5 | `Company News`               | Official announcements from major tech companies |
| 6 | `Startups`                   | Startup launches, VC funding, and entrepreneurship |
| 7 | `Security`                   | Cybersecurity threats, breaches, and advisories  |
| 8 | `Cloud & Infrastructure`     | Cloud platform status, DevOps, infrastructure    |
| 9 | `Developer & Engineering`    | Engineering blogs from top tech companies        |
| 10 | `AI Tools`                  | AI-powered tools, products, and launches         |
| 11 | `Business`                  | Business news, markets, and economics            |
| 12 | `Stocks & Trading`          | Stock market, trading, and financial analysis    |

> **URL encoding reminder:** Categories containing `&` must be encoded:
> - `AI & ML` → `AI+%26+ML` or `AI%20%26%20ML`
> - `Outbreaks & Health` → `Outbreaks+%26+Health`
> - `Cloud & Infrastructure` → `Cloud+%26+Infrastructure`
> - `Developer & Engineering` → `Developer+%26+Engineering`
> - `Stocks & Trading` → `Stocks+%26+Trading`

---

## Available Sources

Each source has a **UUID** you can use in the `sources` filter. Sources are grouped by category below.

> **Tip:** You can also use the Developer Portal at `/dashboard/developers` to browse sources interactively and generate code snippets automatically.

### Technology

| Source Name    | Source ID                                |
|----------------|------------------------------------------|
| Ars Technica   | `93e12f8a-27d6-408f-8ee9-65665304c895`   |
| Hacker News    | `20ed72ee-ab36-4c81-aa5b-9ee7f20e41ec`   |
| TechCrunch     | `c116a3bb-01f1-4273-b826-fd6d21d06cbd`   |
| The Verge      | `f441f4c6-6fa7-4c9c-92cd-2ec2c91924eb`   |
| VentureBeat    | `2c233403-9d42-43ef-8745-1badd642a79e`   |
| Wired          | `b2d5498f-2190-4bce-b4b9-2bcd6e29a5a7`   |

### AI & ML

| Source Name                | Source ID                                |
|----------------------------|------------------------------------------|
| Anthropic Blog             | `f518f6b8-66bd-400f-b586-f9e6068f5410`   |
| arXiv AI                   | `43d1acf9-95bd-4410-9687-03bcbfac1447`   |
| Google AI Blog             | `aaa6c343-5c7e-4f30-8407-e31337b847f5`   |
| Hugging Face Blog          | `e9cdde00-baca-45cd-913c-ccd253a512e3`   |
| Meta AI Research           | `2d61685f-0c26-4e38-9da2-d4909843d14a`   |
| MIT Technology Review - AI | `0e8d0681-6b17-4139-8232-bd9a9c690162`   |
| OpenAI Blog                | `eb18e1ed-b115-42ed-a3dd-e4d9b0a9532d`   |
| Papers with Code           | `7eebfac3-d976-4af6-8e8b-ebc9b1496523`   |
| VentureBeat AI             | `6dc35157-fc20-4e08-a8c5-5e31ca6fbddf`   |

### AI Tools

| Source Name                | Source ID                                |
|----------------------------|------------------------------------------|
| Google News - AI Tools     | `7b1b0bee-eecd-420a-ac01-ac34be7bd967`   |
| MarkTechPost - AI Tools    | `195fb361-9459-42af-8e87-ed3fb7460f41`   |
| Unite.AI - AI News & Tools | `ace370fd-a4df-4cfa-a736-971cda729505`   |

### Security

| Source Name                    | Source ID                                |
|--------------------------------|------------------------------------------|
| BleepingComputer               | `5c1f8508-3ebb-4a7c-9953-5d3e4a23796d`   |
| Dark Reading                   | `c95564bd-a600-4dcc-983b-716a968f6d23`   |
| Krebs on Security              | `33bbd0ad-2f1d-40a7-b8d9-9a571246d42a`   |
| The Hacker News (Security)     | `7a0208be-5838-4b75-bb29-7bd057a07fed`   |

### Outbreaks & Health

| Source Name    | Source ID                                |
|----------------|------------------------------------------|
| CDC Newsroom   | `303d7c07-4d9d-41bf-a732-a5e50023b2f2`   |
| WHO News       | `c35a1c75-ace0-445b-a00d-d2991436c5f0`   |

### Company News

| Source Name          | Source ID                                |
|----------------------|------------------------------------------|
| Amazon Press Center  | `52c716da-6568-44ef-93a9-5bc7ca39a4ff`   |
| Apple Newsroom       | `7c1dda82-f203-41ef-82c9-33c895091a1c`   |
| GitHub Blog          | `85ba7c27-7266-4594-88ea-79621d4f153c`   |
| Google Blog          | `4840ec72-e45d-4a50-a460-f3d91c10a00d`   |
| Meta Newsroom        | `f74e7cdd-fbdc-4e63-b297-6030254b9542`   |
| Microsoft Blog       | `f25979cb-1dba-40ef-a0c8-3ddfa33146fa`   |
| NVIDIA Blog          | `1ddd547b-b5c9-4152-8148-df975ede1b9e`   |

### Cloud & Infrastructure

| Source Name          | Source ID                                |
|----------------------|------------------------------------------|
| AWS Status           | `c2ad2c2e-eeb1-4848-940c-fb2bebe2664d`   |
| Azure Status         | `e543a891-01d5-49d6-b9fb-f26e46ba8953`   |
| Cloudflare Status    | `45671546-9b8c-49aa-8fde-9adeb2ac67b6`   |
| Google Cloud Status  | `d761395e-d06a-450d-b264-d97c26c66244`   |

### Developer & Engineering

| Source Name          | Source ID                                |
|----------------------|------------------------------------------|
| Airbnb Engineering   | `3d0b8bc3-4a77-4fe7-a177-88922f102d45`   |
| Netflix Tech Blog    | `722a750a-5f1e-4c36-a724-fd70c469f7d7`   |
| Stripe Engineering   | `b6521260-ab7f-43cb-ad98-bf7cf152c4fa`   |
| Uber Engineering     | `dad80206-9c04-4509-bf7e-faa0390eae4e`   |

### Startups

| Source Name          | Source ID                                |
|----------------------|------------------------------------------|
| First Round Review   | `76652527-c565-4535-b5d3-a249ca5516b3`   |
| Product Hunt         | `b8142a46-dd1d-41c4-95a7-0f9f8eb22e3c`   |
| YCombinator Blog     | `598fd7e5-aea2-46cb-b144-cd98fe1e8e3e`   |

### Business

| Source Name                | Source ID                                |
|----------------------------|------------------------------------------|
| Bloomberg Business         | `4225f3d7-c522-4892-acf1-2ad414242897`   |
| CNBC Business              | `9f0f19e3-9f58-429d-bac1-dc664bb68348`   |
| Financial Times - Business | `0255346e-87c2-4550-b013-9fb3b2043f0c`   |
| Forbes Business            | `7d5a0225-b820-483d-a36e-b6ee4bd7aa6a`   |

### Stocks & Trading

| Source Name                    | Source ID                                |
|--------------------------------|------------------------------------------|
| Investing.com - Stock Market   | `af752668-4179-403e-bce0-6f364b7401f4`   |
| MarketWatch - Top Stories      | `982fb89b-74cd-40f0-9fd3-1edcc55dc5a5`   |
| Seeking Alpha - Market News    | `820812d7-0da5-45b6-b767-4c6d7d934afe`   |
| Yahoo Finance - Stock Market   | `38e3f858-4ded-42b1-82ec-ca3bad8ddae3`   |

---

## Use Cases & Examples

### 1. Fetch All Articles (Default)

Get the latest 20 articles across all categories and sources.

**cURL:**
```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

**JavaScript (Fetch):**
```javascript
const response = await fetch("https://feed-prism.vercel.app/api/v1/articles", {
  headers: { "x-api-key": "fp_live_YOUR_KEY_HERE" },
});
const data = await response.json();
console.log(data);
```

**Python (Requests):**
```python
import requests

response = requests.get(
    "https://feed-prism.vercel.app/api/v1/articles",
    headers={"x-api-key": "fp_live_YOUR_KEY_HERE"},
)
data = response.json()
print(data)
```

---

### 2. Filter by a Single Category

Get only **Technology** news.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?categories=Technology" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

---

### 3. Filter by Multiple Categories

Get **Technology**, **Security**, and **AI & ML** articles.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?categories=Technology,Security,AI+%26+ML" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

**JavaScript:**
```javascript
const categories = ["Technology", "Security", "AI & ML"];
const url = `https://feed-prism.vercel.app/api/v1/articles?categories=${encodeURIComponent(categories.join(","))}`;

const response = await fetch(url, {
  headers: { "x-api-key": "fp_live_YOUR_KEY_HERE" },
});
const data = await response.json();
```

**Python:**
```python
import requests

response = requests.get(
    "https://feed-prism.vercel.app/api/v1/articles",
    headers={"x-api-key": "fp_live_YOUR_KEY_HERE"},
    params={"categories": "Technology,Security,AI & ML"},
)
data = response.json()
```

---

### 4. Filter by Specific Sources

Get articles only from **TechCrunch** and **The Verge**.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?sources=c116a3bb-01f1-4273-b826-fd6d21d06cbd,f441f4c6-6fa7-4c9c-92cd-2ec2c91924eb" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

---

### 5. Combine Categories + Sources

Get **AI & ML** articles, but only from **OpenAI Blog** and **Anthropic Blog**.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?categories=AI+%26+ML&sources=eb18e1ed-b115-42ed-a3dd-e4d9b0a9532d,f518f6b8-66bd-400f-b586-f9e6068f5410" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

This narrows results to the intersection: only AI & ML articles from those two specific sources.

---

### 6. Custom Pagination

Get page 3 with 10 articles per page.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?page=3&limit=10" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

**Pagination loop in JavaScript:**
```javascript
const API_KEY = "fp_live_YOUR_KEY_HERE";
const BASE = "https://feed-prism.vercel.app/api/v1/articles";

async function fetchAllPages(category) {
  let page = 1;
  let allArticles = [];

  while (true) {
    const url = `${BASE}?categories=${encodeURIComponent(category)}&page=${page}&limit=50`;
    const res = await fetch(url, {
      headers: { "x-api-key": API_KEY },
    });
    const json = await res.json();

    allArticles = allArticles.concat(json.data);

    if (page >= json.meta.totalPages) break;
    page++;
  }

  return allArticles;
}

const techArticles = await fetchAllPages("Technology");
console.log(`Fetched ${techArticles.length} Technology articles`);
```

---

### 7. Build a Tech News Dashboard

Fetch the latest tech news for a dashboard widget.

```javascript
// Server-side (Node.js / Next.js API route)
async function getTechNews() {
  const response = await fetch(
    "https://feed-prism.vercel.app/api/v1/articles?categories=Technology&limit=10",
    {
      headers: { "x-api-key": process.env.FEEDPRISM_API_KEY },
      next: { revalidate: 300 }, // Cache for 5 minutes (Next.js)
    }
  );

  const { data, meta } = await response.json();

  return data.map(article => ({
    title: article.title,
    body: article.body,
    source: article.sources.name,
    url: article.url,
    time: new Date(article.published_at).toRelativeTimeString(),
  }));
}
```

---

### 8. Monitor Cybersecurity Threats

Set up a security feed that polls every 5 minutes.

```python
import requests
import time

API_KEY = "fp_live_YOUR_KEY_HERE"
CATEGORIES = "Security"
POLL_INTERVAL = 300  # 5 minutes

seen_ids = set()

while True:
    response = requests.get(
        "https://feed-prism.vercel.app/api/v1/articles",
        headers={"x-api-key": API_KEY},
        params={
            "categories": CATEGORIES,
            "limit": 20,
        },
    )
    data = response.json()

    for article in data["data"]:
        if article["id"] not in seen_ids:
            seen_ids.add(article["id"])
            print(f"🚨 NEW: {article['title']}")
            print(f"   Source: {article['sources']['name']}")
            print(f"   URL: {article['url']}")
            print(f"   Body: {article['body'][:150]}...")
            print()

    time.sleep(POLL_INTERVAL)
```

---

### 9. Track AI Research & Tools

Combine AI & ML research with AI tool launches.

```bash
curl -X GET "https://feed-prism.vercel.app/api/v1/articles?categories=AI+%26+ML,AI+Tools&limit=30" \
  -H "x-api-key: fp_live_YOUR_KEY_HERE"
```

**Python — Export to CSV:**
```python
import requests
import csv

response = requests.get(
    "https://feed-prism.vercel.app/api/v1/articles",
    headers={"x-api-key": "fp_live_YOUR_KEY_HERE"},
    params={
        "categories": "AI & ML,AI Tools",
        "limit": 50,
    },
)
articles = response.json()["data"]

with open("ai_articles.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "body", "source", "category", "url", "published_at"])
    writer.writeheader()
    for a in articles:
        writer.writerow({
            "title": a["title"],
            "body": a["body"],
            "source": a["sources"]["name"],
            "category": a["category"],
            "url": a["url"],
            "published_at": a["published_at"],
        })

print(f"Exported {len(articles)} articles to ai_articles.csv")
```

---

### 10. Build a Financial News Ticker

Combine Business and Stock Market news for a scrolling ticker.

```javascript
async function getFinancialTicker() {
  const response = await fetch(
    "https://feed-prism.vercel.app/api/v1/articles?categories=Business,Stocks+%26+Trading&limit=15",
    {
      headers: { "x-api-key": "fp_live_YOUR_KEY_HERE" },
    }
  );
  const { data } = await response.json();

  // Format for ticker display
  return data.map(article => ({
    headline: article.title,
    source: article.sources.name,
    category: article.category,
    minutesAgo: Math.round(
      (Date.now() - new Date(article.published_at)) / 60000
    ),
  }));
}
```

---

### 11. Health Outbreak Monitoring

Dedicated feed for tracking health emergencies from WHO and CDC.

```python
import requests

response = requests.get(
    "https://feed-prism.vercel.app/api/v1/articles",
    headers={"x-api-key": "fp_live_YOUR_KEY_HERE"},
    params={
        "categories": "Outbreaks & Health",
        "limit": 50,
    },
)

data = response.json()
alerts = data["data"]

for alert in alerts:
    print(f"[{alert['sources']['name']}] {alert['title']}")
    print(f"  Published: {alert['published_at']}")
    print(f"  Details: {alert['body'][:200]}...")
    print(f"  Read more: {alert['url']}")
    print()
```

---

### 12. Full-Stack Integration (React)

Use Feed Prism as a backend for a React news component.

```jsx
// components/NewsFeed.jsx
"use client";

import { useState, useEffect } from "react";

export default function NewsFeed({ categories = [], limit = 10 }) {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    async function fetchNews() {
      setLoading(true);
      try {
        const params = new URLSearchParams({ page, limit });
        if (categories.length > 0) {
          params.set("categories", categories.join(","));
        }

        // ⚠️ Call YOUR backend, not Feed Prism directly from the client!
        const res = await fetch(`/api/news?${params}`);
        const data = await res.json();

        setArticles(data.data);
        setTotalPages(data.meta.totalPages);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchNews();
  }, [categories, page, limit]);

  if (loading) return <p>Loading news...</p>;
  if (error) return <p>Error: {error}</p>;

  return (
    <div>
      {articles.map((article) => (
        <article key={article.id}>
          <h3>
            <a href={article.url} target="_blank" rel="noopener noreferrer">
              {article.title}
            </a>
          </h3>
          <p>{article.body}</p>
          <small>
            {article.sources.name} · {article.category} ·{" "}
            {new Date(article.published_at).toLocaleDateString()}
          </small>
        </article>
      ))}

      <div>
        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>
          Previous
        </button>
        <span>Page {page} of {totalPages}</span>
        <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}>
          Next
        </button>
      </div>
    </div>
  );
}
```

**Your backend proxy route (keeps the API key server-side):**

```javascript
// app/api/news/route.js (Next.js)
import { NextResponse } from "next/server";

export async function GET(request) {
  const { searchParams } = new URL(request.url);

  const response = await fetch(
    `https://feed-prism.vercel.app/api/v1/articles?${searchParams}`,
    {
      headers: {
        "x-api-key": process.env.FEEDPRISM_API_KEY,
      },
    }
  );

  const data = await response.json();
  return NextResponse.json(data);
}
```

---

## Error Handling

| HTTP Code | Error                          | Cause                                            |
|-----------|--------------------------------|--------------------------------------------------|
| `400`     | Invalid parameters             | Malformed query params (e.g., `page=abc`)        |
| `401`     | Missing x-api-key header       | No `x-api-key` header in the request             |
| `403`     | Invalid or revoked API key     | API key doesn't exist or has been revoked        |
| `429`     | Rate limit exceeded            | More than 60 requests in the last minute         |
| `500`     | Internal Server Error          | Unexpected server error                          |

### Error Response Format

```json
{
  "status": "error",
  "error": "Human-readable error message"
}
```

### Handling Errors in Code

```javascript
const response = await fetch("https://feed-prism.vercel.app/api/v1/articles", {
  headers: { "x-api-key": "fp_live_YOUR_KEY_HERE" },
});

if (!response.ok) {
  const errorBody = await response.json();

  switch (response.status) {
    case 401:
      console.error("Missing API key. Add x-api-key header.");
      break;
    case 403:
      console.error("Invalid API key. Generate a new one at /dashboard/developers.");
      break;
    case 429:
      const retryAfter = response.headers.get("X-RateLimit-Reset");
      console.error(`Rate limited. Retry after ${new Date(Number(retryAfter))}`);
      break;
    default:
      console.error(`API Error: ${errorBody.error}`);
  }
  return;
}

const data = await response.json();
```

```python
import requests

response = requests.get(
    "https://feed-prism.vercel.app/api/v1/articles",
    headers={"x-api-key": "fp_live_YOUR_KEY_HERE"},
)

if response.status_code == 401:
    print("Missing API key")
elif response.status_code == 403:
    print("Invalid or revoked API key")
elif response.status_code == 429:
    print("Rate limited — wait and retry")
elif response.status_code != 200:
    print(f"Error {response.status_code}: {response.json().get('error')}")
else:
    data = response.json()
    print(f"Received {len(data['data'])} articles")
```

---

## Best Practices

### 1. Always Use Server-Side Calls
Never expose your API key in client-side JavaScript. Create a backend proxy route that adds the key.

### 2. Cache Responses
News doesn't change every second. Cache API responses for 2–5 minutes to reduce your request count and improve performance.

```javascript
// Next.js caching
const res = await fetch(url, {
  headers: { "x-api-key": API_KEY },
  next: { revalidate: 300 }, // Cache for 5 minutes
});
```

### 3. Use Pagination Efficiently
Start with a reasonable `limit` (10–20) and paginate as needed. Don't fetch `limit=50` if you only display 5 articles.

### 4. Filter Precisely
The more specific your filters, the faster and more relevant the results:
- ✅ `?categories=Security&limit=10` — focused, fast
- ❌ `?limit=50` — broad, slower, wastes your rate limit

### 5. Handle Errors Gracefully
Always check the `status` field in the response and handle HTTP error codes properly. Implement retry logic with exponential backoff for 429/500 errors.

### 6. Monitor Your Usage
The Developer Portal shows when your API key was last used. Check periodically to ensure no unauthorized usage.

### 7. Regenerate Keys Periodically
For security, regenerate your API key from the Developer Portal every few months. Update your environment variables after regeneration.

---

## Need Help?

- **Developer Portal:** [feed-prism.vercel.app/dashboard/developers](https://feed-prism.vercel.app/dashboard/developers) — Generate keys, browse sources, and test API calls interactively.
- **Issues?** Verify your API key is active and you haven't exceeded the rate limit.
