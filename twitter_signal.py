"""
Twitter Signal Checker — queries Twitter search for token-related buzz.

Returns a signal dict with:
  - tweet_count: number of tweets found mentioning the token/narrative
  - total_engagement: sum of likes + retweets across found tweets
  - max_engagement: highest single-tweet engagement
  - avg_engagement: average engagement per tweet
  - has_kol: whether any tweet author has >10k followers
  - top_tweet_text: text of the highest-engagement tweet (for debugging)
  - query_used: the search query that was used
  - checked_at: ISO timestamp

This module is OBSERVATION ONLY — it does not change trading behavior.
It logs data so we can retroactively analyze whether Twitter buzz
correlates with trade outcomes.
"""

import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.append('/opt/.manus/.sandbox-runtime')

logger = logging.getLogger("twitter_signal")

# Rate limiting: max 1 call per 3 seconds to avoid hammering the API
_last_call_time = 0
_MIN_INTERVAL = 3.0


def _rate_limit():
    """Simple rate limiter."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_time = time.time()


def _get_client():
    """Lazy-load the API client to avoid import errors if not available."""
    try:
        from data_api import ApiClient
        return ApiClient()
    except Exception as e:
        logger.warning(f"Could not load Twitter API client: {e}")
        return None


def _parse_tweets(data: Dict) -> list:
    """Extract tweet objects from the Twitter search API response."""
    tweets = []
    instructions = data.get('result', {}).get('timeline', {}).get('instructions', [])
    for inst in instructions:
        entries = inst.get('entries', [])
        for entry in entries:
            content = entry.get('content', {})
            item = content.get('itemContent', {})
            tweet_result = item.get('tweet_results', {}).get('result', {})
            if tweet_result and tweet_result.get('__typename') == 'Tweet':
                legacy = tweet_result.get('legacy', {})
                user_data = (tweet_result.get('core', {})
                             .get('user_results', {})
                             .get('result', {})
                             .get('legacy', {}))
                tweets.append({
                    'text': legacy.get('full_text', ''),
                    'likes': legacy.get('favorite_count', 0),
                    'retweets': legacy.get('retweet_count', 0),
                    'replies': legacy.get('reply_count', 0),
                    'created_at': legacy.get('created_at', ''),
                    'username': user_data.get('screen_name', ''),
                    'followers': user_data.get('followers_count', 0),
                })
    return tweets


def check_twitter_signal(token_name: str, token_symbol: str,
                         narrative_keyword: Optional[str] = None) -> Dict[str, Any]:
    """
    Check Twitter for mentions of a token or its narrative.
    
    Runs up to 2 queries:
    1. Token name/symbol (e.g., "DevilTrump" or "$DTRUMP")
    2. Narrative keyword if provided (e.g., "trump tariffs")
    
    Returns a signal dict with engagement metrics.
    """
    client = _get_client()
    if not client:
        return _empty_signal("no_api_client")

    all_tweets = []
    queries_used = []

    # Query 1: Search for token name or symbol
    # Use the more distinctive one (longer name usually better)
    token_query = token_name if len(token_name) > len(token_symbol) else token_symbol
    # Skip very short/generic names that would return noise
    if len(token_query) >= 4:
        tweets_1 = _search_twitter(client, token_query)
        if tweets_1 is not None:
            all_tweets.extend(tweets_1)
            queries_used.append(token_query)

    # Query 2: Search for narrative keyword + "solana" or "token" or "pump"
    if narrative_keyword and len(narrative_keyword) >= 5:
        # Make it crypto-specific to reduce noise
        narr_query = f"{narrative_keyword} solana"
        tweets_2 = _search_twitter(client, narr_query)
        if tweets_2 is not None:
            # Deduplicate by tweet text (rough)
            existing_texts = {t['text'][:50] for t in all_tweets}
            for t in tweets_2:
                if t['text'][:50] not in existing_texts:
                    all_tweets.append(t)
            queries_used.append(narr_query)

    if not all_tweets:
        return _empty_signal(",".join(queries_used) if queries_used else token_query)

    # Calculate signal metrics
    total_engagement = sum(t['likes'] + t['retweets'] for t in all_tweets)
    engagements = [t['likes'] + t['retweets'] for t in all_tweets]
    max_engagement = max(engagements)
    avg_engagement = total_engagement / len(all_tweets) if all_tweets else 0
    has_kol = any(t['followers'] >= 10000 for t in all_tweets)
    
    # Find top tweet by engagement
    top_tweet = max(all_tweets, key=lambda t: t['likes'] + t['retweets'])

    return {
        'tweet_count': len(all_tweets),
        'total_engagement': total_engagement,
        'max_engagement': max_engagement,
        'avg_engagement': round(avg_engagement, 1),
        'has_kol': has_kol,
        'top_tweet_text': top_tweet['text'][:200],
        'top_tweet_user': top_tweet['username'],
        'top_tweet_followers': top_tweet['followers'],
        'query_used': ",".join(queries_used),
        'checked_at': datetime.utcnow().isoformat(),
    }


def _search_twitter(client, query: str, max_retries: int = 2) -> Optional[list]:
    """Execute a Twitter search with rate limiting and error handling."""
    _rate_limit()
    
    for attempt in range(max_retries):
        try:
            result = client.call_api('Twitter/search_twitter', 
                                     query={'query': query, 'type': 'Latest'})
            
            # Check for API errors
            if isinstance(result, dict):
                code = result.get('code', '')
                if code == 'failed_precondition':
                    logger.warning(f"Twitter search failed for '{query}': {result.get('message', '')[:80]}")
                    return None
            
            tweets = _parse_tweets(result)
            logger.info(f"Twitter search '{query}': found {len(tweets)} tweets")
            return tweets
            
        except Exception as e:
            logger.warning(f"Twitter search error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return None


def _empty_signal(query: str) -> Dict[str, Any]:
    """Return a zero-signal dict when no tweets are found."""
    return {
        'tweet_count': 0,
        'total_engagement': 0,
        'max_engagement': 0,
        'avg_engagement': 0,
        'has_kol': False,
        'top_tweet_text': '',
        'top_tweet_user': '',
        'top_tweet_followers': 0,
        'query_used': query,
        'checked_at': datetime.utcnow().isoformat(),
    }


# --- Quick self-test ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with a known token
    print("Testing Twitter signal for 'DevilTrump' (DTRUMP)...")
    signal = check_twitter_signal("DevilTrump", "DTRUMP", "trump tariffs")
    print(json.dumps(signal, indent=2))
    
    print("\nTesting Twitter signal for 'RandomGarbage123' (RG123)...")
    signal2 = check_twitter_signal("RandomGarbage123", "RG123")
    print(json.dumps(signal2, indent=2))
    
    print("\nTesting Twitter signal for 'Bitcoin' (BTC)...")
    signal3 = check_twitter_signal("Bitcoin", "BTC", "bitcoin")
    print(json.dumps(signal3, indent=2))
