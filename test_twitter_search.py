import sys
sys.path.append('/opt/.manus/.sandbox-runtime')
from data_api import ApiClient
import json

client = ApiClient()

# search_twitter exists! Just needs the right params
param_combos = [
    {'query': 'trump'},
    {'q': 'trump'},
    {'keyword': 'trump'},
    {'search_query': 'trump'},
    {'query': 'trump', 'type': 'Latest'},
    {'query': 'trump', 'section': 'latest'},
    {'query': 'trump', 'count': '10'},
    {'query': 'trump', 'search_type': 'Latest'},
]

for i, params in enumerate(param_combos):
    try:
        result = client.call_api('Twitter/search_twitter', query=params)
        msg = result.get('message', '') if isinstance(result, dict) else ''
        code = result.get('code', '') if isinstance(result, dict) else ''
        if 'Cannot read' not in msg and code != 'failed_precondition':
            print(f"OK Combo {i} {params}")
            with open('/tmp/twitter_search_ok.json', 'w') as f:
                json.dump(result, f, indent=2)
        else:
            print(f"FAIL Combo {i}: {msg[:80]}")
    except Exception as e:
        print(f"ERR Combo {i}: {str(e)[:80]}")
