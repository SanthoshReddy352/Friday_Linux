from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin

import requests


DEFAULT_API_BASE_URL = "https://api.worldmonitor.app"
DEFAULT_WEB_BASE_URL = "https://www.worldmonitor.app"
DEFAULT_FEED_API_BASE_URL = "https://worldmonitor.app"
DEFAULT_NEWS_WINDOW_HOURS = 20
USER_AGENT = "FRIDAY-WorldMonitor/1.0 (+https://github.com/koala73/worldmonitor)"

CATEGORY_LABELS = {
    "global": "global news",
    "tech": "tech news",
    "finance": "finance news",
    "commodity": "commodity news",
    "energy": "energy news",
    "good": "good news",
}

CATEGORY_SOURCES = {
    "global": ["https://worldmonitor.app/"],
    "tech": ["https://tech.worldmonitor.app/"],
    "finance": ["https://finance.worldmonitor.app/"],
    "commodity": ["https://commodity.worldmonitor.app/"],
    "energy": ["https://energy.worldmonitor.app/"],
    "good": ["https://happy.worldmonitor.app/"],
}

CATEGORY_FEED_VARIANTS = {
    "global": ["full"],
    "tech": ["tech"],
    "finance": ["finance"],
    "commodity": ["commodity", "finance"],
    "energy": ["energy", "commodity", "finance"],
    "good": ["happy"],
}

CATEGORY_FILTER_TERMS = {
    "tech": ("ai", "tech", "software", "chip", "cyber", "cloud", "startup", "semiconductor", "robot", "data"),
    "finance": ("market", "stock", "bond", "rate", "bank", "fed", "ecb", "inflation", "earnings", "forex", "crypto"),
    "commodity": ("commodity", "gold", "silver", "copper", "metal", "mining", "wheat", "corn", "oil", "gas", "lithium"),
    "energy": ("energy", "oil", "gas", "crude", "brent", "wti", "lng", "power", "electricity", "renewable", "opec"),
}

THREAT_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class WorldMonitorService:
    def __init__(self, config=None):
        self.config = config

    def get_global_news_brief(
        self,
        focus="",
        country_code="",
        limit=6,
        min_threat="",
    ):
        return self.get_global_news_digest(
            focus=focus,
            country_code=country_code,
            limit=limit,
            min_threat=min_threat,
        )["display_text"]

    def get_news_digest(
        self,
        category="global",
        focus="",
        country_code="",
        limit=8,
        min_threat="",
        window_hours=DEFAULT_NEWS_WINDOW_HOURS,
    ):
        category = self.normalize_category(category)
        limit = self._safe_limit(limit)
        window_hours = self._safe_window_hours(window_hours)

        if country_code or min_threat:
            if category == "global":
                return self._get_api_digest(
                    focus=focus,
                    country_code=country_code,
                    limit=limit,
                    min_threat=min_threat,
                )
            return self._empty_category_digest(category, focus, limit, window_hours)

        try:
            articles, source_url = self._fetch_feed_digest_articles(category)
        except Exception:
            articles, source_url = [], ""

        if not articles:
            try:
                articles, source_url = self._fetch_category_articles(category)
            except Exception:
                if category != "global":
                    raise
                articles, source_url = [], ""

        if articles:
            articles = self._filter_articles(
                articles,
                focus=focus,
                window_hours=window_hours,
                limit=limit,
            )
            if articles:
                return self._format_category_digest(
                    category=category,
                    articles=articles,
                    source_url=source_url,
                    focus=focus,
                    window_hours=window_hours,
                )

        if category == "global":
            return self._get_api_digest(
                focus=focus,
                country_code=country_code,
                limit=limit,
                min_threat=min_threat,
            )
        return self._empty_category_digest(category, focus, limit, window_hours)

    def get_global_news_digest(
        self,
        focus="",
        country_code="",
        limit=6,
        min_threat="",
    ):
        return self.get_news_digest(
            category="global",
            focus=focus,
            country_code=country_code,
            limit=limit,
            min_threat=min_threat,
        )

    def _get_api_digest(
        self,
        focus="",
        country_code="",
        limit=6,
        min_threat="",
    ):
        payload = self._fetch_bootstrap(["insights"])
        insights = (payload.get("data") or {}).get("insights") or {}
        stories = self._filter_stories(
            insights.get("topStories") or [],
            focus=focus,
            country_code=country_code,
            min_threat=min_threat,
        )
        limit = self._safe_limit(limit)
        stories = stories[:limit]
        return {
            "display_text": self._format_brief(insights, stories, focus=focus, country_code=country_code),
            "speech_segments": self._format_speech_segments(insights, stories, focus=focus, country_code=country_code),
            "stories": stories,
            "dashboard_url": self.dashboard_url_for_category("global"),
            "source_url": self.dashboard_url_for_category("global"),
            "category": "global",
        }

    def _fetch_feed_digest_articles(self, category):
        errors = []
        for variant in self._feed_variants(category):
            try:
                articles, source_url = self._fetch_feed_digest_variant(category, variant)
                if articles:
                    return articles, source_url
            except Exception as exc:
                errors.append(f"{variant}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))
        return [], self.dashboard_url_for_category(category)

    def _fetch_feed_digest_variant(self, category, variant):
        api_base = self._config_str("world_monitor.feed_api_base_url", DEFAULT_FEED_API_BASE_URL).rstrip("/")
        timeout = self._config_float("world_monitor.timeout_s", 12.0)
        params = urlencode({"variant": variant, "lang": "en"})
        url = f"{api_base}/api/news/v1/list-feed-digest?{params}"
        dashboard_url = self.dashboard_url_for_category(category)
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": dashboard_url,
            "Origin": dashboard_url.rstrip("/"),
        }
        api_key = self._config_str("world_monitor.api_key", "") or self._config_str("world_monitor_api_key", "")
        if api_key:
            headers["X-WorldMonitor-Key"] = api_key

        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return [], dashboard_url
        return self._articles_from_feed_digest(data, category, variant), dashboard_url

    def _articles_from_feed_digest(self, data, category, variant):
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        categories = payload.get("categories") if isinstance(payload, dict) else {}
        if not isinstance(categories, dict):
            return []

        articles = []
        for category_name, category_payload in categories.items():
            items = []
            if isinstance(category_payload, dict):
                raw_items = category_payload.get("items") or category_payload.get("articles") or []
                if isinstance(raw_items, list):
                    items = raw_items
            elif isinstance(category_payload, list):
                items = category_payload

            for item in items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("headline") or item.get("primaryTitle") or "").strip()
                if not title or self._looks_like_promotional_text(title):
                    continue
                summary = str(
                    item.get("summary")
                    or item.get("description")
                    or item.get("snippet")
                    or item.get("content")
                    or ""
                ).strip()
                source = str(item.get("source") or item.get("primarySource") or item.get("publisher") or "").strip()
                published_at = self._parse_datetime(
                    item.get("publishedAt")
                    or item.get("published_at")
                    or item.get("pubDate")
                    or item.get("date")
                    or item.get("createdAt")
                )
                article = {
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "url": str(item.get("link") or item.get("url") or item.get("primaryLink") or "").strip(),
                    "published_at": published_at,
                    "age_text": "",
                    "feed_category": str(category_name or ""),
                    "is_alert": bool(item.get("isAlert") or item.get("alert")),
                    "threat": item.get("threat") if isinstance(item.get("threat"), dict) else {},
                    "variant": variant,
                }
                if self._matches_category_article(article, category, variant):
                    articles.append(article)
        return self._dedupe_articles(articles)

    def _fetch_category_articles(self, category):
        errors = []
        for source_url in self._source_candidates(category):
            try:
                articles = self._fetch_articles_from_url(source_url)
                if articles:
                    return articles, source_url
            except Exception as exc:
                errors.append(f"{source_url}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))
        return [], self._source_candidates(category)[0]

    def _fetch_articles_from_url(self, source_url):
        timeout = self._config_float("world_monitor.timeout_s", 12.0)
        response = requests.get(
            source_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        headers = getattr(response, "headers", {}) or {}
        content_type = headers.get("Content-Type", "") if isinstance(headers, dict) else ""
        if "json" in str(content_type).lower():
            return []
        html_text = getattr(response, "text", "")
        if not isinstance(html_text, str) or len(html_text.strip()) < 20:
            return []
        return self._extract_articles_from_html(html_text, source_url)

    def _extract_articles_from_html(self, html_text, base_url):
        articles = []
        articles.extend(self._extract_json_ld_articles(html_text, base_url))
        articles.extend(self._extract_text_articles(html_text, base_url))
        return self._dedupe_articles(articles)

    def _extract_json_ld_articles(self, html_text, base_url):
        articles = []
        for match in re.finditer(
            r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        ):
            raw = unescape(match.group(1)).strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            for item in self._walk_json_articles(data):
                title = str(item.get("headline") or item.get("name") or "").strip()
                if not title:
                    continue
                publisher = item.get("publisher") or {}
                if isinstance(publisher, dict):
                    source = str(publisher.get("name") or "").strip()
                else:
                    source = str(publisher or "").strip()
                articles.append({
                    "title": title,
                    "summary": str(item.get("description") or "").strip(),
                    "source": source,
                    "url": urljoin(base_url, str(item.get("url") or "")),
                    "published_at": self._parse_datetime(item.get("datePublished") or item.get("dateModified")),
                    "age_text": "",
                })
        return articles

    def _walk_json_articles(self, value):
        if isinstance(value, list):
            for item in value:
                yield from self._walk_json_articles(item)
            return
        if not isinstance(value, dict):
            return
        item_type = value.get("@type") or value.get("type") or ""
        if isinstance(item_type, list):
            type_text = " ".join(str(item) for item in item_type)
        else:
            type_text = str(item_type)
        if re.search(r"\b(?:NewsArticle|Article|ReportageNewsArticle)\b", type_text):
            yield value
        for key in ("@graph", "itemListElement", "mainEntity", "hasPart"):
            if key in value:
                yield from self._walk_json_articles(value[key])

    def _extract_text_articles(self, html_text, base_url):
        parser = _VisibleTextParser()
        parser.feed(html_text)
        parser.close()
        lines = self._clean_body_lines(parser.lines)
        articles = []
        for index, line in enumerate(lines):
            if not self._looks_like_headline(line):
                continue
            lookahead = lines[index + 1:index + 7]
            age_text, published_at = self._find_relative_age(lookahead + [line])
            source = self._find_source(lookahead)
            summary = self._find_summary(lookahead, line)
            articles.append({
                "title": line,
                "summary": summary,
                "source": source,
                "url": base_url,
                "published_at": published_at,
                "age_text": age_text,
                "source_index": index,
            })
        return articles

    def _clean_body_lines(self, lines):
        cleaned = []
        noise = {
            "home", "login", "sign in", "menu", "navigation", "worldmonitor",
            "world monitor", "share", "read more", "source", "loading",
            "advertisement", "privacy policy", "terms", "contact",
        }
        for line in lines:
            text = self._clean_text(line)
            lowered = text.lower()
            if not text or lowered in noise:
                continue
            if len(text) < 3 or len(text) > 360:
                continue
            if re.fullmatch(r"[\W_]+", text):
                continue
            cleaned.append(text)
        return cleaned

    def _looks_like_headline(self, text):
        lowered = text.lower()
        if self._looks_like_promotional_text(text):
            return False
        if self._extract_relative_age(text)[1] is not None:
            return False
        if lowered in CATEGORY_LABELS.values():
            return False
        if re.search(r"\b(?:subscribe|newsletter|cookie|privacy|terms|advertisement|read more)\b", lowered):
            return False
        if len(text) < 22 or len(text) > 180:
            return False
        if text.count(" ") < 3:
            return False
        return bool(re.search(r"[A-Za-z]", text))

    def _find_relative_age(self, lines):
        for line in lines:
            age_text, delta = self._extract_relative_age(line)
            if delta is not None:
                return age_text, datetime.now(timezone.utc) - delta
        return "", None

    def _extract_relative_age(self, text):
        match = re.search(
            r"\b(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\s*ago\b",
            str(text or ""),
            re.IGNORECASE,
        )
        if not match:
            return "", None
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("s"):
            delta = timedelta(seconds=amount)
            noun = "second"
        elif unit.startswith("m"):
            delta = timedelta(minutes=amount)
            noun = "minute"
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
            noun = "hour"
        elif unit.startswith("d"):
            delta = timedelta(days=amount)
            noun = "day"
        else:
            delta = timedelta(weeks=amount)
            noun = "week"
        return f"{amount} {noun}{'' if amount == 1 else 's'} ago", delta

    def _find_source(self, lines):
        for line in lines[:4]:
            if self._extract_relative_age(line)[1] is not None:
                continue
            text = re.sub(r"\s*[-|•]\s*", " ", line).strip()
            if 2 <= len(text) <= 45 and text.count(" ") <= 5 and not text.endswith("."):
                return text
        return ""

    def _find_summary(self, lines, title):
        title_key = self._dedupe_key(title)
        for line in lines:
            if self._extract_relative_age(line)[1] is not None:
                continue
            if self._dedupe_key(line) == title_key:
                continue
            if self._looks_like_headline(line):
                continue
            if 35 <= len(line) <= 260 and re.search(r"[A-Za-z]", line):
                return line
        return ""

    def _filter_articles(self, articles, focus="", window_hours=DEFAULT_NEWS_WINDOW_HOURS, limit=8):
        focus = str(focus or "").strip().lower()
        now = datetime.now(timezone.utc)
        recent = []
        untimed = []
        for article in articles:
            haystack = f"{article.get('title', '')} {article.get('summary', '')} {article.get('source', '')}".lower()
            if focus and focus not in haystack:
                continue
            published_at = article.get("published_at")
            if published_at is None:
                untimed.append(article)
                continue
            age_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
            if age_hours <= window_hours:
                recent.append(article)

        pool = recent + untimed if recent else untimed
        pool = sorted(
            pool,
            key=lambda article: (
                self._article_priority(article),
                article.get("published_at") or datetime.fromtimestamp(0, tz=timezone.utc),
                -int(article.get("source_index") or 0),
            ),
            reverse=True,
        )
        return pool[:limit]

    def _article_priority(self, article):
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        threat = article.get("threat") if isinstance(article.get("threat"), dict) else {}
        threat_level = str(threat.get("level") or "").lower()
        priority_terms = (
            "breaking", "critical", "war", "strike", "attack", "explosion", "crisis",
            "sanction", "tariff", "market", "inflation", "oil", "gas", "power",
            "chip", "ai", "cyber", "earnings", "rates", "central bank",
        )
        score = sum(1 for term in priority_terms if term in text)
        if article.get("is_alert"):
            score += 5
        if "critical" in threat_level:
            score += 4
        elif "high" in threat_level:
            score += 3
        elif "medium" in threat_level:
            score += 1
        return score

    def _format_category_digest(self, category, articles, source_url, focus="", window_hours=DEFAULT_NEWS_WINDOW_HOURS):
        label = CATEGORY_LABELS[category]
        focus_text = f" for {focus}" if focus else ""
        title = f"WorldMonitor {label} briefing{focus_text}"
        lines = [
            title,
            f"Source: {source_url}",
            f"Window: last {window_hours} hours",
            "Critical summaries:",
        ]
        speech = [
            f"Here is your {label} briefing{focus_text} from the last {window_hours} hours."
        ]

        for index, article in enumerate(articles, start=1):
            summary = self._article_summary_sentence(article)
            meta = self._article_meta(article)
            display_line = f"{index}. {summary}"
            if meta:
                display_line += f" ({meta})"
            lines.append(display_line)
            speech.append(f"{index}. {summary}{f' {meta}.' if meta else ''}")

        return {
            "display_text": "\n".join(lines),
            "speech_segments": [self._clean_for_speech(segment) for segment in speech],
            "stories": articles,
            "dashboard_url": self.dashboard_url_for_category(category),
            "source_url": source_url,
            "category": category,
        }

    def _empty_category_digest(self, category, focus, limit, window_hours):
        source_url = self._source_candidates(category)[0]
        label = CATEGORY_LABELS[category]
        focus_text = f" for {focus}" if focus else ""
        message = f"I could not find recent {label} summaries{focus_text} from the last {window_hours} hours."
        return {
            "display_text": message,
            "speech_segments": [message],
            "stories": [],
            "dashboard_url": self.dashboard_url_for_category(category),
            "source_url": source_url,
            "category": category,
        }

    def _article_summary_sentence(self, article):
        title = self._sentence(str(article.get("title") or "Untitled story").strip())
        summary = self._sentence(str(article.get("summary") or "").strip())
        title_key = self._dedupe_key(title)
        summary_key = self._dedupe_key(summary)
        if summary and title_key not in summary_key and summary_key not in title_key:
            return f"{title} {summary}"
        return title

    def _article_meta(self, article):
        parts = []
        source = str(article.get("source") or "").strip()
        if source:
            parts.append(f"reported by {source}")
        age = str(article.get("age_text") or "").strip()
        if not age and article.get("published_at"):
            age = self._age_from_datetime(article["published_at"])
        if age:
            parts.append(age)
        return ", ".join(parts)

    def _sentence(self, text):
        text = self._clean_text(text)
        if not text:
            return ""
        return text if text.endswith((".", "!", "?")) else f"{text}."

    def _clean_for_speech(self, text):
        text = self._clean_text(text)
        return re.sub(
            r"\b(\d+)\s*(h|hr|hrs)\s*ago\b",
            lambda match: f"{match.group(1)} hour{'s' if match.group(1) != '1' else ''} ago",
            text,
            flags=re.IGNORECASE,
        )

    def _age_from_datetime(self, dt):
        if dt is None:
            return ""
        seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        if seconds < 90:
            return "1 minute ago"
        minutes = seconds // 60
        if minutes < 90:
            return f"{minutes} minutes ago"
        hours = minutes // 60
        if hours < 48:
            return f"{hours} hour{'' if hours == 1 else 's'} ago"
        days = hours // 24
        return f"{days} day{'' if days == 1 else 's'} ago"

    def _dedupe_articles(self, articles):
        deduped = []
        seen = set()
        for article in articles:
            title = self._clean_text(article.get("title") or "")
            if not title:
                continue
            key = self._dedupe_key(title)
            if key in seen:
                continue
            seen.add(key)
            article = dict(article)
            article["title"] = title
            article["summary"] = self._clean_text(article.get("summary") or "")
            article["source"] = self._clean_text(article.get("source") or "")
            deduped.append(article)
        return deduped

    def _fetch_bootstrap(self, keys):
        api_base = self._config_str("world_monitor.api_base_url", DEFAULT_API_BASE_URL).rstrip("/")
        web_base = self._config_str("world_monitor.web_base_url", DEFAULT_WEB_BASE_URL).rstrip("/")
        timeout = self._config_float("world_monitor.timeout_s", 12.0)
        params = urlencode({"keys": ",".join(keys)})
        url = f"{api_base}/api/bootstrap?{params}"

        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        api_key = self._config_str("world_monitor.api_key", "") or self._config_str("world_monitor_api_key", "")
        if api_key:
            headers["X-WorldMonitor-Key"] = api_key
        elif self._config_bool("world_monitor.public_dashboard_fallback", True):
            headers["Referer"] = f"{web_base}/"

        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("WorldMonitor returned an unexpected response.")
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data

    def _filter_stories(self, stories, focus="", country_code="", min_threat=""):
        focus = str(focus or "").strip().lower()
        country_code = str(country_code or "").strip().upper()
        min_rank = THREAT_RANK.get(str(min_threat or "").strip().lower(), -1)
        filtered = []

        for story in stories:
            if not isinstance(story, dict):
                continue
            if country_code and str(story.get("countryCode") or "").upper() != country_code:
                continue
            threat = str(story.get("threatLevel") or "info").lower()
            if min_rank >= 0 and THREAT_RANK.get(threat, 0) < min_rank:
                continue
            haystack = " ".join(
                str(story.get(key) or "")
                for key in ("primaryTitle", "primarySource", "category", "threatLevel", "countryCode")
            ).lower()
            if focus and focus not in haystack:
                continue
            filtered.append(story)

        return sorted(
            filtered,
            key=lambda item: int(item.get("importanceScore") or 0),
            reverse=True,
        )

    def _format_brief(self, insights, stories, focus="", country_code=""):
        generated_at = self._format_datetime(insights.get("generatedAt"))
        scope = []
        if focus:
            scope.append(f"focus: {focus}")
        if country_code:
            scope.append(f"country: {str(country_code).upper()}")
        scope_text = f" ({', '.join(scope)})" if scope else ""

        lines = [f"WorldMonitor intelligence brief{scope_text}"]
        if generated_at:
            lines.append(f"Generated: {generated_at}")

        world_brief = str(insights.get("worldBrief") or "").strip()
        if world_brief:
            lines.append(f"AI summary: {world_brief}")

        cluster_count = insights.get("clusterCount")
        multi_source_count = insights.get("multiSourceCount")
        if cluster_count is not None or multi_source_count is not None:
            lines.append(
                f"Signals: {cluster_count or 0} clusters, {multi_source_count or 0} multi-source confirmations."
            )

        if not stories:
            lines.append("No matching WorldMonitor stories were returned for that filter.")
            return "\n".join(lines)

        lines.append("Top stories:")
        for index, story in enumerate(stories, start=1):
            title = str(story.get("primaryTitle") or "Untitled story").strip()
            source = str(story.get("primarySource") or "Unknown source").strip()
            threat = str(story.get("threatLevel") or "info").upper()
            category = str(story.get("category") or "news").strip()
            country = str(story.get("countryCode") or "").strip().upper()
            date_text = self._format_date(story.get("pubDate"))
            link = str(story.get("primaryLink") or "").strip()
            meta = ", ".join(part for part in (threat, category, country, date_text) if part)
            line = f"{index}. {title} — {source}"
            if meta:
                line += f" [{meta}]"
            if link:
                line += f"\n   Source: {link}"
            lines.append(line)

        return "\n".join(lines)

    def _format_speech_segments(self, insights, stories, focus="", country_code=""):
        scope = []
        if focus:
            scope.append(str(focus).strip())
        if country_code:
            scope.append(str(country_code).upper())
        scope_text = f" for {' and '.join(scope)}" if scope else ""

        segments = []
        world_brief = str(insights.get("worldBrief") or "").strip()
        if world_brief:
            segments.append(f"Opening WorldMonitor. Here is the global intelligence picture{scope_text}. {world_brief}")
        else:
            segments.append(f"Opening WorldMonitor for the latest world news{scope_text}.")

        for index, story in enumerate(stories, start=1):
            title = str(story.get("primaryTitle") or "Untitled story").strip()
            source = str(story.get("primarySource") or "").strip()
            threat = str(story.get("threatLevel") or "").strip().lower()
            category = str(story.get("category") or "").strip().lower()
            country = str(story.get("countryCode") or "").strip().upper()
            date_text = self._format_date(story.get("pubDate"))

            details = []
            if threat and threat != "info":
                details.append(f"{threat} threat")
            if category:
                details.append(category)
            if country:
                details.append(country)
            if date_text:
                details.append(date_text)

            detail_text = f" This is marked as {', '.join(details)}." if details else ""
            source_text = f" Reported by {source}." if source else ""
            segments.append(f"Story {index}: {title}.{detail_text}{source_text}")

        if not stories:
            segments.append("WorldMonitor did not return matching stories for that filter.")

        return segments

    def normalize_category(self, category):
        text = str(category or "").strip().lower()
        aliases = {
            "world": "global",
            "global": "global",
            "general": "global",
            "technology": "tech",
            "tech": "tech",
            "finance": "finance",
            "financial": "finance",
            "markets": "finance",
            "market": "finance",
            "commodity": "commodity",
            "commodities": "commodity",
            "energy": "energy",
            "good": "good",
            "happy": "good",
            "positive": "good",
        }
        return aliases.get(text, "global")

    def dashboard_url_for_category(self, category):
        return self._source_candidates(category)[0]

    def _format_datetime(self, value):
        dt = self._parse_datetime(value)
        if dt is None:
            return "" if value in (None, "") else str(value)
        date_text = self._format_date_from_datetime(dt)
        return f"{date_text}, {dt.hour:02d}:{dt.minute:02d} UTC"

    def _format_date(self, value):
        dt = self._parse_datetime(value)
        if dt is None:
            return "" if value in (None, "") else str(value)
        return self._format_date_from_datetime(dt)

    def _parse_datetime(self, value):
        if value in (None, ""):
            return None
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 10_000_000_000:
                    timestamp = timestamp / 1000.0
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                text = str(value).replace("Z", "+00:00")
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _format_date_from_datetime(self, dt):
        day = dt.day
        return f"{day}{self._ordinal_suffix(day)} {dt.strftime('%B')} {dt.year}"

    def _ordinal_suffix(self, day):
        if 10 <= day % 100 <= 20:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    def _safe_limit(self, value):
        try:
            return max(1, min(12, int(value)))
        except Exception:
            return 6

    def _safe_window_hours(self, value):
        try:
            return max(1, min(48, int(value)))
        except Exception:
            return DEFAULT_NEWS_WINDOW_HOURS

    def _source_candidates(self, category):
        category = self.normalize_category(category)
        configured = self._config_value(f"world_monitor.sources.{category}", None)
        candidates = []
        if isinstance(configured, (list, tuple)):
            candidates.extend(str(item).strip() for item in configured if str(item).strip())
        elif configured:
            candidates.append(str(configured).strip())
        candidates.extend(CATEGORY_SOURCES[category])
        normalized = []
        seen = set()
        for url in candidates:
            url = url.rstrip("/") + "/"
            if url not in seen:
                normalized.append(url)
                seen.add(url)
        return normalized

    def _feed_variants(self, category):
        category = self.normalize_category(category)
        configured = self._config_value(f"world_monitor.feed_variants.{category}", None)
        candidates = []
        if isinstance(configured, (list, tuple)):
            candidates.extend(str(item).strip() for item in configured if str(item).strip())
        elif configured:
            candidates.append(str(configured).strip())
        candidates.extend(CATEGORY_FEED_VARIANTS[category])
        variants = []
        seen = set()
        for variant in candidates:
            if variant and variant not in seen:
                variants.append(variant)
                seen.add(variant)
        return variants

    def _matches_category_article(self, article, category, variant):
        category = self.normalize_category(category)
        if category in {"global", "good"}:
            return True
        if variant == category and category != "energy":
            return True
        haystack = " ".join(
            str(article.get(key) or "")
            for key in ("title", "summary", "source", "feed_category")
        ).lower()
        terms = CATEGORY_FILTER_TERMS.get(category) or ()
        return any(term in haystack for term in terms)

    def _looks_like_promotional_text(self, text):
        lowered = str(text or "").lower()
        promotional_patterns = (
            r"\bworld monitor\b.*\bdashboard\b",
            r"\breal-time global intelligence dashboard\b",
            r"\bai-powered real-time global intelligence\b",
            r"\bused by \d",
            r"\bupgrade to world monitor pro\b",
            r"\bfeatures\b",
            r"\bcurated rss news feeds\b",
            r"\bcountry instability index\b",
        )
        return any(re.search(pattern, lowered) for pattern in promotional_patterns)

    def _clean_text(self, text):
        return re.sub(r"\s+", " ", unescape(str(text or ""))).strip()

    def _dedupe_key(self, text):
        return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()[:180]

    def _config_value(self, key, default=None):
        config = self.config
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default

    def _config_str(self, key, default=""):
        value = self._config_value(key, default)
        return str(value or "").strip()

    def _config_float(self, key, default):
        try:
            return float(self._config_str(key, default))
        except Exception:
            return float(default)

    def _config_bool(self, key, default=False):
        config = self.config
        if config and hasattr(config, "get"):
            value = config.get(key, default)
        else:
            value = default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}


class _VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "div", "figcaption", "footer",
        "h1", "h2", "h3", "h4", "header", "li", "main", "p", "section", "time",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self._parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in self.BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = " ".join(str(data or "").split())
        if text:
            self._parts.append(text)

    def close(self):
        self._flush()
        super().close()

    def _flush(self):
        if not self._parts:
            return
        text = " ".join(self._parts).strip()
        if text:
            self.lines.append(text)
        self._parts = []
