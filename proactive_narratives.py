"""
Proactive Narrative Engine — Event-First, Token-Second
──────────────────────────────────────────────────────
Instead of: token appears → check if it matches a stale headline
We do:      breaking event detected → generate expected token keywords → watch for them

Architecture:
  1. DETECT: Scan news sources for BREAKING events (< 30 min old, high velocity)
  2. PREDICT: For each breaking event, generate a set of expected token names/symbols
     that pump.fun degens would create (e.g., "Trump tariff" → TRUMP, TARIFF, MAGA, etc.)
  3. WATCH: Pre-register these keywords as "hot triggers" with priority scores
  4. MATCH: When a new token arrives, check hot triggers FIRST (O(1) lookup)
     before falling back to the slower narrative matching

This gives us:
  - Sub-second matching for anticipated tokens (hash lookup vs string scanning)
  - Priority weighting: first-mover tokens on a breaking event get higher confidence
  - Decay: hot triggers expire after 30 min (the window where pump.fun reacts)
  - Measurement: we can track "anticipated vs surprise" match rates
"""

import time
import logging
import threading
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("proactive_narratives")

# ── Configuration ─────────────────────────────────────────────────────────────
HOT_TRIGGER_TTL_MIN     = 30    # Hot triggers expire after 30 min
MAX_HOT_TRIGGERS        = 500   # Cap to prevent memory bloat
PRIORITY_BOOST          = 1.5   # Multiplier for proactive matches vs reactive
MIN_EVENT_VELOCITY      = 70    # Only generate triggers for high-velocity events

# ── Common pump.fun naming patterns ──────────────────────────────────────────
# Degens create tokens using these patterns when an event breaks:
#   - Direct name: "Trump", "Elon", "Bitcoin"
#   - Abbreviation: "BTC", "ETH", "SOL"
#   - Meme suffix: "TrumpInu", "ElonDoge", "BitcoinMoon"
#   - Action word: "TrumpPump", "ElonBuy", "BTCBull"
#   - Emoji-style: "TrumpFire", "ElonRocket"
MEME_SUFFIXES = ["inu", "doge", "moon", "pump", "bull", "bear", "fire",
                 "rocket", "king", "god", "chad", "pepe", "wojak", "based",
                 "coin", "token", "sol", "ai", "meme"]

MEME_PREFIXES = ["baby", "super", "mega", "ultra", "dark", "based", "chad",
                 "official", "real", "the"]


class HotTrigger:
    """A pre-registered keyword we're watching for."""
    __slots__ = ["keyword", "keyword_lower", "event_keyword", "created_at",
                 "priority", "category", "matched_count", "source_event"]

    def __init__(self, keyword: str, event_keyword: str, priority: float,
                 category: str, source_event: str):
        self.keyword = keyword
        self.keyword_lower = keyword.lower()
        self.event_keyword = event_keyword
        self.created_at = datetime.utcnow()
        self.priority = priority
        self.category = category
        self.matched_count = 0
        self.source_event = source_event

    def is_expired(self) -> bool:
        age_min = (datetime.utcnow() - self.created_at).total_seconds() / 60
        return age_min > HOT_TRIGGER_TTL_MIN

    def age_minutes(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds() / 60


class ProactiveNarrativeEngine:
    """
    Maintains a set of "hot triggers" — anticipated token keywords
    generated from breaking events.
    """

    def __init__(self):
        self._hot_triggers = {}       # keyword_lower -> HotTrigger
        self._event_history = []      # Track which events generated triggers
        self._lock = threading.Lock()
        self._stats = {
            "events_processed": 0,
            "triggers_generated": 0,
            "proactive_matches": 0,
            "reactive_matches": 0,    # Fallback to old system
            "triggers_expired": 0,
        }

    # ── Core: Generate triggers from a breaking event ────────────────────────
    def process_breaking_event(self, event_keyword: str, velocity: float,
                               category: str, sources: list[str]) -> list[str]:
        """
        Given a breaking news event, generate anticipated token keywords.
        Returns list of generated trigger keywords.
        """
        if velocity < MIN_EVENT_VELOCITY:
            return []

        self._stats["events_processed"] += 1

        # Extract key words from the event
        words = [w for w in event_keyword.lower().split() if len(w) > 4]  # Min 5 chars to reduce false positives
        # Filter out common stop words and generic verbs
        stop_words = {"the", "and", "for", "are", "but", "not", "you", "all",
                      "can", "had", "her", "was", "one", "our", "out", "has",
                      "his", "how", "its", "may", "new", "now", "old", "see",
                      "way", "who", "did", "get", "let", "say", "she", "too",
                      "use", "with", "from", "this", "that", "will", "been",
                      "have", "into", "just", "more", "most", "much", "must",
                      "next", "over", "such", "take", "than", "them", "then",
                      "they", "very", "when", "what", "about", "after", "could",
                      "every", "first", "other", "their", "these", "which",
                      "would", "being", "still", "where", "while", "takes",
                      "says", "said", "also", "back", "even", "some", "only",
                      "off", "shrugs", "keep", "open", "step", "slips",
                      "hikes", "goes", "come", "came", "make", "made",
                      "show", "shows", "look", "looks", "like", "need",
                      "want", "give", "gave", "tell", "told", "find",
                      "know", "think", "call", "turn", "move", "live",
                      "long", "last", "high", "down", "here", "well",
                      "good", "best", "year", "week", "days", "time",
                      "price", "market", "report", "news", "update",
                      "official", "coin", "token", "crypto",
                      # Additional generic words that cause false positives
                      "real", "blue", "wall", "rate", "rise", "fall",
                      "deal", "plan", "bill", "vote", "rule", "fund",
                      "bank", "bond", "gold", "data", "test", "safe",
                      "risk", "loss", "gain", "push", "pull", "drop",
                      "jump", "boom", "bust", "peak", "base", "core",
                      "edge", "line", "link", "list", "lock", "mark",
                      "play", "post", "race", "road", "role", "sell",
                      "side", "sign", "size", "spot", "star", "stop",
                      "term", "tool", "type", "unit", "view", "work",
                      "zero", "free", "full", "half", "hard", "huge",
                      "fast", "late", "near", "past", "wide", "arms",
                      "identity", "linkedin", "record", "advance",
                      "project", "detect", "system", "global",
                      "small", "large", "major", "stake", "boost",
                      "shift", "quiet", "strike", "court", "authority"}
        key_words = [w for w in words if w not in stop_words]

        if not key_words:
            return []

        generated = []
        # Priority based on velocity and source breadth
        base_priority = (velocity / 100) * (1 + len(sources) * 0.1)

        with self._lock:
            # 1. Direct keywords (highest priority)
            for word in key_words[:5]:  # Top 5 words
                self._add_trigger(word, event_keyword, base_priority * 1.0,
                                  category, event_keyword)
                generated.append(word)

                # 2. Capitalized version (how degens name tokens)
                cap = word.capitalize()
                self._add_trigger(cap, event_keyword, base_priority * 0.95,
                                  category, event_keyword)
                generated.append(cap)

            # 3. Combined keywords (e.g., "TrumpTariff" from "trump tariff")
            if len(key_words) >= 2:
                for i in range(min(3, len(key_words))):
                    for j in range(i + 1, min(4, len(key_words))):
                        combo = key_words[i].capitalize() + key_words[j].capitalize()
                        self._add_trigger(combo, event_keyword,
                                          base_priority * 0.85, category, event_keyword)
                        generated.append(combo)

            # 4. Meme variants (lower priority — more speculative)
            primary_word = key_words[0].capitalize()
            for suffix in MEME_SUFFIXES[:8]:  # Top 8 suffixes
                meme_name = primary_word + suffix.capitalize()
                self._add_trigger(meme_name, event_keyword,
                                  base_priority * 0.70, category, event_keyword)
                generated.append(meme_name)

            # 5. Common abbreviations
            if len(key_words) >= 2:
                abbrev = "".join(w[0].upper() for w in key_words[:4])
                if len(abbrev) >= 2:
                    self._add_trigger(abbrev, event_keyword,
                                      base_priority * 0.75, category, event_keyword)
                    generated.append(abbrev)

        self._stats["triggers_generated"] += len(generated)
        self._event_history.append({
            "event": event_keyword,
            "velocity": velocity,
            "category": category,
            "triggers_count": len(generated),
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Keep event history bounded
        if len(self._event_history) > 100:
            self._event_history = self._event_history[-50:]

        logger.info(
            f"[PROACTIVE] Event: '{event_keyword}' | velocity={velocity:.0f} | "
            f"generated {len(generated)} triggers | total_active={len(self._hot_triggers)}"
        )
        return generated

    def _add_trigger(self, keyword: str, event_keyword: str, priority: float,
                     category: str, source_event: str):
        """Add a hot trigger, replacing if higher priority."""
        key = keyword.lower()
        existing = self._hot_triggers.get(key)
        if existing and existing.priority >= priority and not existing.is_expired():
            return  # Keep the higher-priority existing trigger

        self._hot_triggers[key] = HotTrigger(
            keyword=keyword,
            event_keyword=event_keyword,
            priority=priority,
            category=category,
            source_event=source_event,
        )

        # Enforce cap
        if len(self._hot_triggers) > MAX_HOT_TRIGGERS:
            self._cleanup_expired()

    # ── Matching: Check a token against hot triggers ─────────────────────────
    def check_token(self, token_name: str, token_symbol: str) -> dict | None:
        """
        Check if a token matches any hot trigger.
        Returns match info dict or None.

        This is O(n) over trigger count but with short-circuit on exact matches.
        For 500 triggers this is sub-millisecond.
        """
        name_lower = token_name.lower().strip()
        sym_lower = token_symbol.lower().strip()

        best_match = None
        best_score = 0

        with self._lock:
            for key, trigger in list(self._hot_triggers.items()):
                if trigger.is_expired():
                    continue

                score = 0
                trigger_kw = trigger.keyword_lower

                # Skip triggers that are too short (< 4 chars) for substring matching
                # They can still exact-match on symbol
                is_short_trigger = len(trigger_kw) < 4

                # Exact match on name or symbol (always allowed)
                if name_lower == trigger_kw or sym_lower == trigger_kw:
                    score = 100
                # Token name contains trigger keyword (only for long triggers)
                elif not is_short_trigger and trigger_kw in name_lower:
                    score = 90
                # Trigger keyword contains token name (token is abbreviation)
                elif name_lower in trigger_kw and len(name_lower) >= 3:
                    score = 80
                # Symbol match
                elif trigger_kw in sym_lower:
                    score = 85
                # Partial overlap (at least 4 chars)
                elif len(trigger_kw) >= 4 and len(name_lower) >= 4:
                    # Check if significant portion overlaps
                    if trigger_kw[:4] in name_lower or name_lower[:4] in trigger_kw:
                        score = 65

                if score > best_score:
                    best_score = score
                    best_match = trigger

            if best_match and best_score >= 60:
                best_match.matched_count += 1
                self._stats["proactive_matches"] += 1

                return {
                    "trigger_keyword": best_match.keyword,
                    "event_keyword": best_match.event_keyword,
                    "match_score": best_score * best_match.priority,
                    "raw_score": best_score,
                    "priority": best_match.priority,
                    "category": best_match.category,
                    "trigger_age_min": best_match.age_minutes(),
                    "is_proactive": True,
                    "source_event": best_match.source_event,
                }

        return None

    # ── Maintenance ──────────────────────────────────────────────────────────
    def _cleanup_expired(self):
        """Remove expired triggers."""
        expired = [k for k, v in self._hot_triggers.items() if v.is_expired()]
        for k in expired:
            del self._hot_triggers[k]
        self._stats["triggers_expired"] += len(expired)

    def cleanup(self):
        """Public cleanup method — call periodically."""
        with self._lock:
            self._cleanup_expired()

    def get_active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._hot_triggers.values() if not t.is_expired())

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "active_triggers": self.get_active_count(),
            "total_triggers": len(self._hot_triggers),
        }

    def get_active_triggers(self) -> list[dict]:
        """Return active triggers sorted by priority for dashboard display."""
        with self._lock:
            active = [
                {
                    "keyword": t.keyword,
                    "event": t.event_keyword,
                    "priority": round(t.priority, 2),
                    "age_min": round(t.age_minutes(), 1),
                    "matched": t.matched_count,
                    "category": t.category,
                }
                for t in self._hot_triggers.values()
                if not t.is_expired()
            ]
        active.sort(key=lambda x: x["priority"], reverse=True)
        return active[:50]  # Top 50 for display


# ── Integration with narrative_monitor ────────────────────────────────────────
def feed_narratives_to_engine(engine: ProactiveNarrativeEngine,
                               narratives: list[dict]):
    """
    Called after each narrative scan. Feeds high-velocity narratives
    into the proactive engine to generate hot triggers.
    """
    new_triggers = 0
    for n in narratives:
        velocity = n.get("velocity", 0) or n.get("score", 0)
        if velocity >= MIN_EVENT_VELOCITY:
            triggers = engine.process_breaking_event(
                event_keyword=n["keyword"],
                velocity=velocity,
                category=n.get("category", "other"),
                sources=n.get("sources", []),
            )
            new_triggers += len(triggers)

    if new_triggers > 0:
        logger.info(
            f"[PROACTIVE] Fed {len(narratives)} narratives → "
            f"{new_triggers} new triggers | "
            f"active={engine.get_active_count()}"
        )
    return new_triggers


# ── Singleton for import ─────────────────────────────────────────────────────
_engine = ProactiveNarrativeEngine()

def get_engine() -> ProactiveNarrativeEngine:
    return _engine

