#!/usr/bin/env python3
"""SerpAPI Google Images Light: image search through the images_results endpoint.

Usage:
    python3 serp_images.py "query" [--num 5] [--min-width 400]

Requires SERPAPI_API_KEY in .env or as an environment variable.
Uses the Google Images Light endpoint (cheaper than the classic search).
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse

# Load .env if present
def load_env():
    for env_path in [
        os.path.join(os.path.dirname(__file__), '..', '.env'),
        os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'),
    ]:
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            break

load_env()

API_KEY = os.environ.get('SERPAPI_API_KEY', '')


def search_images(query: str, num: int = 5, min_width: int = 0) -> list[dict]:
    """Image search through SerpAPI Google Images.

    Returns a list of dicts with: url, thumbnail, title, width, height, source.
    """
    if not API_KEY:
        print("ERROR: SERPAPI_API_KEY not configured. Add it to .env or to the environment.", file=sys.stderr)
        sys.exit(1)

    params = urllib.parse.urlencode({
        'engine': 'google_images_light',
        'q': query,
        'api_key': API_KEY,
        'num': min(num * 3, 100),  # Ask for more, to filter afterwards
    })

    url = f'https://serpapi.com/search.json?{params}'

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    results = []
    for img in data.get('images_results', []):
        width = img.get('original_width', 0) or 0
        height = img.get('original_height', 0) or 0

        if min_width and width < min_width:
            continue

        results.append({
            'url': img.get('original', ''),
            'thumbnail': img.get('thumbnail', ''),
            'title': img.get('title', ''),
            'width': width,
            'height': height,
            'source': img.get('source', ''),
        })

        if len(results) >= num:
            break

    return results


def verify_url(url: str) -> bool:
    """Checks that a URL returns HTTP 200."""
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description='Image search through SerpAPI Google Images')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--num', type=int, default=5, help='Number of results (default: 5)')
    parser.add_argument('--min-width', type=int, default=0, help='Minimum width in pixels')
    parser.add_argument('--verify', action='store_true', help='Check that each URL is reachable')
    parser.add_argument('--json', action='store_true', help='Raw JSON output')
    args = parser.parse_args()

    results = search_images(args.query, args.num, args.min_width)

    if args.verify:
        results = [r for r in results if verify_url(r['url'])]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        if not results:
            print(f"No image found for: {args.query}")
            return

        for i, r in enumerate(results, 1):
            size = f"{r['width']}x{r['height']}" if r['width'] else "?"
            print(f"{i}. [{size}] {r['url']}")
            if r['title']:
                print(f"   {r['title']}")
            if r['source']:
                print(f"   Source: {r['source']}")
            print()


if __name__ == '__main__':
    main()
