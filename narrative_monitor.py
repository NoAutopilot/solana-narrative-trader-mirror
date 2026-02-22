"""
Narrative Monitor — RSS Feed Scanner & Narrative Scorer
────────────────────────────────────────────────────────
Scans RSS feeds from multiple news sources, extracts trending keywords,
scores them by velocity and cross-source breadth, categorizes them,
and stores active narratives in the database.

Runs on a configurable interval (default 15 min).
"""

import re
import time
import logging
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from html import unescape

import feedparser

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import (
    RSS_FEEDS, SOURCE_VELOCITY_WEIGHTS, MIN_NARRATIVE_SCORE,
    NARRATIVE_SCAN_INTERVAL, VELOCITY_WEIGHT, MAX_VELOCITY_WEIGHT,
    CROSS_SOURCE_BOOST, CRYPTO_SOURCE_BOOST, CATEGORY_KEYWORDS,
    CATEGORY_DURABILITY, LOGS_DIR
)
import database as db

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "narrative_monitor.log"),
    level=logging.INFO,
    format="%(asctime)s [NARRATIVE] %(message)s"
)
logger = logging.getLogger("narrative_monitor")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

# ── Stop words for headline cleaning ─────────────────────────────────────────
HEADLINE_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall", "it",
    "its", "this", "that", "these", "those", "he", "she", "they", "we",
    "you", "i", "my", "your", "his", "her", "our", "their", "not", "no",
    "so", "if", "up", "out", "about", "into", "over", "after", "before",
    "between", "under", "again", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "than",
    "too", "very", "just", "also", "now", "new", "says", "said",
}


def clean_headline(text):
    """Strip HTML, normalize whitespace, extract key words."""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-zA-Z0-9 ]", " ", text)
    words = text.lower().split()
    key_words = [w for w in words if w not in HEADLINE_STOP_WORDS and len(w) > 2]
    return " ".join(key_words[:5])


def detect_category(keyword):
    """Assign a category based on keyword matching."""
    kw_lower = keyword.lower()
    for category, cat_keywords in CATEGORY_KEYWORDS.items():
        for ck in cat_keywords:
            if ck in kw_lower:
                return category
    return "default"


def get_durability(category):
    """Get durability in hours for a category."""
    return CATEGORY_DURABILITY.get(category, CATEGORY_DURABILITY["default"])


# ── RSS Scanning ─────────────────────────────────────────────────────────────

def scan_feeds():
    """
    Scan all RSS feeds and return a list of narrative candidates.
    Each candidate has: keyword, score, sources, velocity, category, durability.
    """
    headlines_by_source = {}
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            headlines = []
            for entry in feed.entries[:25]:
                title = entry.get("title", "")
                if title:
                    cleaned = clean_headline(title)
                    if cleaned and len(cleaned) > 5:
                        headlines.append(cleaned)
            headlines_by_source[source_name] = headlines
            logger.info(f"[{source_name}] Fetched {len(headlines)} headlines")
        except Exception as e:
            logger.error(f"[{source_name}] Feed error: {e}")
            headlines_by_source[source_name] = []

    keyword_sources = defaultdict(set)
    keyword_velocity = defaultdict(float)

    for source_name, headlines in headlines_by_source.items():
        weight = SOURCE_VELOCITY_WEIGHTS.get(source_name, 1.0)
        for headline in headlines:
            keyword_sources[headline].add(source_name)
            keyword_velocity[headline] = max(
                keyword_velocity[headline],
                70 * weight
            )

    narratives = []
    for keyword, sources in keyword_sources.items():
        velocity = keyword_velocity[keyword]
        max_velocity = velocity
        source_count = len(sources)
        cross_boost = 1.0 + (source_count - 1) * CROSS_SOURCE_BOOST
        crypto_sources = {"coindesk", "cointelegraph"}
        has_crypto = bool(sources & crypto_sources)
        crypto_boost = 1.0 + (CRYPTO_SOURCE_BOOST if has_crypto else 0)
        score = (velocity * VELOCITY_WEIGHT + max_velocity * MAX_VELOCITY_WEIGHT) * cross_boost * crypto_boost
        score = min(100, score)
        category = detect_category(keyword)
        durability = get_durability(category)

        if score >= MIN_NARRATIVE_SCORE:
            narratives.append({
                "keyword": keyword,
                "score": round(score, 1),
                "sources": list(sources),
                "velocity": round(velocity, 1),
                "durability": durability,
                "category": category,
            })

    narratives.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Scan complete: {len(narratives)} narratives above threshold")
    return narratives


def store_narratives(narratives):
    """Store narratives in the database (with dedup)."""
    stored = 0
    for n in narratives:
        db.log_narrative(
            keyword=n["keyword"],
            score=n["score"],
            sources=n["sources"],
            velocity=n["velocity"],
            durability=n["durability"],
        )
        stored += 1
    logger.info(f"Stored {stored} narratives in DB")
    return stored


def expire_old_narratives():
    """Mark narratives as expired based on their category durability."""
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("SELECT id, keyword, detected_at, durability FROM narratives WHERE expired = 0")
    rows = c.fetchall()
    expired_count = 0
    now = datetime.utcnow()
    for row in rows:
        detected = datetime.fromisoformat(row["detected_at"])
        durability_hours = row["durability"] or 24
        if (now - detected).total_seconds() > durability_hours * 3600:
            c.execute("UPDATE narratives SET expired = 1 WHERE id = ?", (row["id"],))
            expired_count += 1
    conn.commit()
    conn.close()
    if expired_count:
        logger.info(f"Expired {expired_count} old narratives")
    return expired_count


def get_active_narratives():
    """Return all active (non-expired) narratives with score >= threshold."""
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, keyword, score, sources, velocity, durability, detected_at
        FROM narratives
        WHERE expired = 0 AND score >= ?
        ORDER BY score DESC
    """, (MIN_NARRATIVE_SCORE,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Background Scanner ───────────────────────────────────────────────────────

class NarrativeScanner:
    """Runs narrative scanning in a background loop."""

    def __init__(self, on_scan_callback=None):
        self.on_scan_callback = on_scan_callback
        self.running = False
        self._scan_count = 0

    def _scan_cycle(self):
        try:
            expire_old_narratives()
            narratives = scan_feeds()
            store_narratives(narratives)
            self._scan_count += 1
            logger.info(f"Scan cycle {self._scan_count} complete: {len(narratives)} narratives")
            if self.on_scan_callback and narratives:
                try:
                    self.on_scan_callback(narratives)
                except Exception as e:
                    logger.error(f"Scan callback error: {e}")
        except Exception as e:
            logger.error(f"Scan cycle error: {e}")

    def start(self):
        self.running = True
        logger.info("Narrative scanner starting...")
        self._scan_cycle()
        while self.running:
            time.sleep(NARRATIVE_SCAN_INTERVAL)
            if self.running:
                self._scan_cycle()

    def start_background(self):
        t = threading.Thread(target=self.start, daemon=True)
        t.start()
        logger.info("Narrative scanner started in background thread")
        return t

    def stop(self):
        self.running = False

    def stats(self):
        active = get_active_narratives()
        return {
            "scan_count": self._scan_count,
            "active_narratives": len(active),
            "last_scan": datetime.utcnow().isoformat(),
        }


if __name__ == "__main__":
    db.init_db()
    print("=== Running single narrative scan ===")
    narratives = scan_feeds()
    print(f"\nFound {len(narratives)} narratives:\n")
    for n in narratives[:20]:
        print(f"  [{n['category']:10s}] score={n['score']:5.1f} | "
              f"vel={n['velocity']:5.1f} | sources={n['sources']} | "
              f"'{n['keyword']}'")
    store_narratives(narratives)
    print(f"\nStored {len(narratives)} narratives in DB")
