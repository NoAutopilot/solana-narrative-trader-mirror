"""
Token Scanner
─────────────
Connects to PumpPortal's real-time websocket and listens for new token
creation events on pump.fun. For each new token, it:

  1. Extracts name, symbol, mint address, creator, metadata
  2. Scores the token against active narratives (narrative matching)
  3. Passes matched tokens to the rug filter
  4. Logs every evaluation to the database

Narrative Matching:
  - Tokenizes the token name and symbol
  - Computes fuzzy overlap with each active narrative keyword
  - Returns a match score 0-100
"""

import json
import time
import logging
import threading
import re
from datetime import datetime
from difflib import SequenceMatcher

import websocket

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import (
    PUMPPORTAL_WS_URL, MIN_MATCH_SCORE, LOGS_DIR
)
import database as db

os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOGS_DIR, "token_scanner.log"),
    level=logging.INFO,
    format="%(asctime)s [SCANNER] %(message)s"
)
logger = logging.getLogger("scanner")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)


# ── Narrative Matching ────────────────────────────────────────────────────────

def tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens, removing noise."""
    text = re.sub(r"[^a-zA-Z0-9 ]", " ", text.lower())
    tokens = set(text.split())
    stop = {"the", "a", "an", "of", "in", "on", "at", "to", "for",
            "is", "are", "inu", "coin", "token", "sol", "fun"}
    return tokens - stop


def keyword_match_score(token_name: str, token_symbol: str,
                         narrative_keyword: str) -> float:
    """
    Returns a 0-100 match score between a token and a narrative keyword.

    v2: Fixed false positive problem. Previous version matched any 3-letter
    narrative word as a substring (e.g. "all" in "chronically", "arm" in
    "marmot"). Now requires:
      - Substring word matches must be >= 5 chars ("trump" ok, "all" rejected)
      - Word must match as a WHOLE WORD in the token name, not just substring
      - Symbol initialism requires >= 3 chars and exact match only

    Strategy:
      1. Full narrative phrase in name/symbol → 100
      2. Whole-word match of significant narrative word (>=5 chars) in token → 90
      3. Whole-word match of medium narrative word (4 chars) in token → 80
      4. Symbol exact-matches a narrative word (>=4 chars) → 82
      5. Symbol is initialism of narrative words (exact, >=3 chars) → 75
      6. Token overlap (Jaccard, whole words only) → scaled 0-85
      7. Sequence similarity fallback → scaled 0-65
    """
    name_lower   = token_name.lower().strip()
    symbol_lower = token_symbol.lower().strip()
    narrative_lc = narrative_keyword.lower().strip()
    narrative_words = [w for w in narrative_lc.split() if len(w) > 2]

    # Tokenize name into individual words for whole-word matching
    import re as _re
    name_words = set(_re.sub(r"[^a-zA-Z0-9 ]", " ", name_lower).split())
    # Also create a version without spaces for compound word detection
    name_no_spaces = _re.sub(r"[^a-z0-9]", "", name_lower)

    # Generic words that appear in narratives but are meaningless for matching
    MATCH_STOP_WORDS = {
        "call", "make", "take", "give", "come", "goes", "turn", "move",
        "show", "look", "find", "keep", "tell", "know", "help", "want",
        "need", "like", "live", "play", "work", "send", "hold", "pull",
        "push", "drop", "fall", "rise", "gain", "loss", "deal", "plan",
        "bill", "vote", "rule", "fund", "bank", "bond", "rate", "risk",
        "test", "safe", "free", "full", "half", "hard", "fast", "late",
        "near", "past", "wide", "long", "last", "high", "down", "well",
        "good", "best", "year", "week", "days", "time", "step", "next",
        "back", "still", "even", "also", "just", "more", "most", "much",
        "real", "blue", "wall", "line", "side", "mark", "post", "spot",
        "zero", "huge", "boom", "bust", "peak", "base", "core", "edge",
        "sign", "size", "star", "stop", "term", "tool", "type", "unit",
        "view", "role", "road", "race", "link", "list", "lock",
    }

    # 1. Direct substring: full narrative phrase in name/symbol
    if narrative_lc in name_lower or narrative_lc in symbol_lower:
        return 100.0
    # Full token name found in narrative (token is a key entity)
    if len(name_lower) >= 4 and name_lower in narrative_lc:
        return 95.0

    # 2-3. Whole-word matching: narrative word must appear as a standalone
    #      word in the token name, not as a substring of another word
    for word in narrative_words:
        if word in MATCH_STOP_WORDS:
            continue
        if len(word) >= 5 and word in name_words:
            # Strong match: significant word like "trump", "bitcoin", "tariff"
            return 90.0
        if len(word) == 4 and word in name_words:
            # Medium match: 4-letter word like "elon", "doge"
            return 80.0

    # 2b. Compound word detection: check if a significant narrative word
    #     appears as a prefix or suffix in a compound token name
    #     e.g. "DevilTrump" → "deviltrump" contains "trump"
    for word in narrative_words:
        if word in MATCH_STOP_WORDS:
            continue
        if len(word) >= 5 and word in name_no_spaces:
            # Verify it's at a word boundary (start/end of compound)
            idx = name_no_spaces.find(word)
            if idx == 0 or idx + len(word) == len(name_no_spaces):
                return 85.0  # Slightly lower than whole-word match

    # 4. Symbol exact-matches a narrative word (not substring)
    if len(symbol_lower) >= 4:
        for word in narrative_words:
            if word in MATCH_STOP_WORDS:
                continue
            if symbol_lower == word:
                return 82.0

    # 5. Symbol is initialism of narrative words (exact match, min 3 chars)
    if len(symbol_lower) >= 3:
        initials = "".join(w[0] for w in narrative_words if w)
        if symbol_lower == initials and len(initials) >= 3:
            return 75.0

    # 6. Token overlap (Jaccard) — uses whole-word tokenization
    name_tokens      = tokenize(token_name)
    narrative_tokens = tokenize(narrative_keyword)
    if name_tokens and narrative_tokens:
        intersection = name_tokens & narrative_tokens
        # Only count intersections with words >= 4 chars
        meaningful = {w for w in intersection if len(w) >= 4}
        if meaningful:
            union = name_tokens | narrative_tokens
            jaccard = len(meaningful) / len(union) if union else 0
            if jaccard > 0:
                return round(min(85, jaccard * 250), 1)

    # 7. Sequence similarity (only for reasonably similar strings)
    if len(name_lower) >= 5 and len(narrative_lc) >= 5:
        seq_score = SequenceMatcher(None, name_lower, narrative_lc).ratio()
        if seq_score > 0.55:  # Raised threshold from 0.45
            return round(seq_score * 70, 1)

    return 0.0


def match_token_to_narratives(token_name: str, token_symbol: str,
                               narratives: list[dict]) -> tuple[dict | None, float]:
    """
    Find the best matching narrative for a token.
    Returns (best_narrative, best_score) or (None, 0).
    """
    best_narrative = None
    best_score     = 0.0

    for narrative in narratives:
        score = keyword_match_score(token_name, token_symbol,
                                    narrative["keyword"])
        if score > best_score:
            best_score     = score
            best_narrative = narrative

    return best_narrative, best_score


# ── PumpPortal Websocket Client ───────────────────────────────────────────────

class TokenScanner:
    """
    Subscribes to PumpPortal's new token creation stream.
    On each new token, runs narrative matching and queues matched tokens
    for rug filtering and potential execution.
    """

    def __init__(self, on_match_callback=None, on_all_tokens_callback=None):
        """
        on_match_callback:      called with (token_data, narrative, match_score)
                                for every token that passes narrative matching.
        on_all_tokens_callback: called with (token_data) for EVERY token seen,
                                regardless of narrative match. Used for research.
        """
        self.on_match_callback       = on_match_callback
        self.on_all_tokens_callback  = on_all_tokens_callback
        self.ws                = None
        self.running           = False
        self._reconnect_delay  = 5
        self._narrative_cache  = []
        self._narrative_ts     = 0
        self._tokens_seen      = 0
        self._tokens_matched   = 0

    def _refresh_narratives(self):
        """Refresh narrative cache every 5 minutes."""
        now = time.time()
        if now - self._narrative_ts > 300:
            from narrative_monitor import get_active_narratives
            self._narrative_cache = get_active_narratives()
            self._narrative_ts    = now
            logger.info(f"Narrative cache refreshed: {len(self._narrative_cache)} active")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # PumpPortal sends different event types; we want token creation
        tx_type = data.get("txType", "")
        if tx_type != "create":
            return

        self._tokens_seen += 1
        token_name   = data.get("name", "")
        token_symbol = data.get("symbol", "")
        mint_address = data.get("mint", "")
        creator      = data.get("traderPublicKey", "")
        initial_buy  = data.get("initialBuy", 0)
        market_cap   = data.get("marketCapSol", 0)
        uri          = data.get("uri", "")

        if not mint_address or not token_name:
            return

        logger.info(f"New token: {token_name} ({token_symbol}) | {mint_address[:12]}...")

        # Build token_data early so on_all_tokens_callback gets full context
        token_data_full = {
            "mint_address":  mint_address,
            "token_name":    token_name,
            "token_symbol":  token_symbol,
            "creator":       creator,
            "initial_buy":   initial_buy,
            "market_cap_sol": market_cap,
            "uri":           uri,
            "detected_at":   datetime.utcnow().isoformat(),
        }

        # Fire all-tokens callback for research data collection
        if self.on_all_tokens_callback:
            try:
                self.on_all_tokens_callback(token_data_full)
            except Exception as e:
                logger.error(f"on_all_tokens_callback error: {e}")
            return  # Paper trader handles everything from here

        # Refresh narrative cache
        self._refresh_narratives()

        if not self._narrative_cache:
            logger.debug("No active narratives — skipping matching")
            db.log_evaluation(
                mint_address=mint_address, token_name=token_name,
                token_symbol=token_symbol, narrative_id=None,
                narrative_score=0, match_score=0, rug_flags={},
                rug_passed=False, initial_liquidity_usd=0,
                initial_market_cap_usd=market_cap, dev_holding_pct=0,
                holder_count=0, is_bundled=False,
                decision="skip_narrative",
                decision_reason="No active narratives in cache"
            )
            return

        # Narrative matching
        best_narrative, match_score = match_token_to_narratives(
            token_name, token_symbol, self._narrative_cache
        )

        token_data = {
            "mint_address":  mint_address,
            "token_name":    token_name,
            "token_symbol":  token_symbol,
            "creator":       creator,
            "initial_buy":   initial_buy,
            "market_cap_sol": market_cap,
            "uri":           uri,
            "detected_at":   datetime.utcnow().isoformat(),
        }

        if match_score < MIN_MATCH_SCORE:
            db.log_evaluation(
                mint_address=mint_address, token_name=token_name,
                token_symbol=token_symbol,
                narrative_id=best_narrative["id"] if best_narrative else None,
                narrative_score=best_narrative["score"] if best_narrative else 0,
                match_score=match_score, rug_flags={}, rug_passed=False,
                initial_liquidity_usd=0, initial_market_cap_usd=market_cap,
                dev_holding_pct=0, holder_count=0, is_bundled=False,
                decision="skip_score",
                decision_reason=f"Match score {match_score:.1f} < threshold {MIN_MATCH_SCORE}"
            )
            return

        # Narrative match — pass to callback (rug filter + execution decision)
        self._tokens_matched += 1
        logger.info(
            f"NARRATIVE MATCH: {token_name} ({token_symbol}) "
            f"| match={match_score:.1f} | narrative='{best_narrative['keyword']}'"
        )

        if self.on_match_callback:
            self.on_match_callback(token_data, best_narrative, match_score)

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"WebSocket closed: {close_status_code} {close_msg}")
        # Do NOT set self.running = False here — let the reconnect loop handle it

    def _on_open(self, ws):
        logger.info("WebSocket connected to PumpPortal")
        self._reconnect_delay = 5  # Reset backoff on successful connect
        # Subscribe to new token creation events
        subscribe_msg = json.dumps({"method": "subscribeNewToken"})
        ws.send(subscribe_msg)
        logger.info("Subscribed to new token stream")

    def start(self):
        """Start the scanner with auto-reconnect."""
        self.running = True
        while self.running:
            try:
                logger.info(f"Connecting to {PUMPPORTAL_WS_URL}...")
                self.ws = websocket.WebSocketApp(
                    PUMPPORTAL_WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket exception: {e}")

            if self.running:
                logger.info(f"Reconnecting in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(60, self._reconnect_delay * 2)

    def start_background(self):
        """Start the scanner in a background thread."""
        t = threading.Thread(target=self.start, daemon=True)
        t.start()
        logger.info("Token scanner started in background thread")
        return t

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()

    def stats(self) -> dict:
        return {
            "tokens_seen":    self._tokens_seen,
            "tokens_matched": self._tokens_matched,
            "match_rate":     (self._tokens_matched / self._tokens_seen
                               if self._tokens_seen > 0 else 0),
            "narratives_active": len(self._narrative_cache),
        }


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    db.init_db()

    # Quick unit test of narrative matching
    print("=== Narrative Matching Unit Tests ===")
    test_cases = [
        ("TrumpCoin",    "TRUMP",   "trump tariffs"),
        ("ElonDoge",     "EDOGE",   "elon musk"),
        ("KeepAndroid",  "KAND",    "keep android open"),
        ("RandomToken",  "RAND",    "bitcoin price slips"),
        ("BitcoinBull",  "BTCBULL", "bitcoin gains"),
        ("SuperBowlInu", "SBINU",   "superbowl championship"),
    ]
    for name, sym, narrative in test_cases:
        score = keyword_match_score(name, sym, narrative)
        status = "MATCH" if score >= MIN_MATCH_SCORE else "skip"
        print(f"  [{status}] {name:15s} vs '{narrative}' → {score:.1f}")

    print("\n=== Starting live token stream (Ctrl+C to stop) ===")

    def on_match(token_data, narrative, score):
        print(f"\n*** MATCH ***")
        print(f"  Token:     {token_data['token_name']} ({token_data['token_symbol']})")
        print(f"  Mint:      {token_data['mint_address']}")
        print(f"  Narrative: {narrative['keyword']} (score={narrative['score']})")
        print(f"  Match:     {score:.1f}")

    scanner = TokenScanner(on_match_callback=on_match)
    try:
        scanner.start()
    except KeyboardInterrupt:
        scanner.stop()
        stats = scanner.stats()
        print(f"\nStats: {stats}")
