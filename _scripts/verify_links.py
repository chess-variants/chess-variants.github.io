#!/usr/bin/env python3
"""
Verify external links in YAML data files.
Checks links in guis.yml, engines.yml, resources.yml, and servers.yml.
"""

import yaml
import requests
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple

# Configuration
TIMEOUT = 10  # seconds
MAX_RETRIES = 3  # number of attempts before marking as failed
RETRY_DELAY = 2  # seconds between retries
FILES_TO_CHECK = ['guis.yml', 'engines.yml', 'resources.yml', 'servers.yml']
DATA_DIR = Path('_data')

def check_url(url: str, attempt: int = 1) -> Tuple[bool, str]:
    """
    Check if a URL is accessible with retry logic.

    Args:
        url: The URL to check
        attempt: Current attempt number (used for retry tracking)

    Returns:
        Tuple of (success, error_message)
    """
    last_error = ""

    for current_attempt in range(attempt, MAX_RETRIES + 1):
        try:
            response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
            # If HEAD doesn't work, try GET
            if response.status_code >= 400:
                response = requests.get(url, timeout=TIMEOUT, allow_redirects=True)

            if response.status_code < 400:
                if current_attempt > 1:
                    print(f"    ✓ OK (succeeded on attempt {current_attempt})")
                return True, ""
            else:
                last_error = f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            last_error = "Timeout"
        except requests.exceptions.ConnectionError:
            last_error = "Connection error"
        except requests.exceptions.TooManyRedirects:
            last_error = "Too many redirects"
        except requests.exceptions.RequestException as e:
            last_error = f"Request error: {str(e)}"
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"

        # If this wasn't the last attempt, wait before retrying
        if current_attempt < MAX_RETRIES:
            print(f"    ⟳ Attempt {current_attempt} failed ({last_error}), retrying...")
            time.sleep(RETRY_DELAY)

    # All retries exhausted
    return False, f"{last_error} (failed after {MAX_RETRIES} attempts)"

def extract_links(data: Dict) -> List[Tuple[str, str, str]]:
    """
    Extract links from YAML data structure.

    Args:
        data: Parsed YAML data

    Returns:
        List of tuples (item_title, link_field, url)
    """
    links = []

    if 'items' in data:
        for item in data['items']:
            title = item.get('title', 'Unknown')

            # Check 'link' field
            if 'link' in item and item['link']:
                links.append((title, 'link', item['link']))

            # Check 'github' field (construct URL)
            if 'github' in item and item['github']:
                github_url = f"https://github.com/{item['github']}"
                links.append((title, 'github', github_url))

    return links

def verify_file_links(file_path: Path) -> List[Dict[str, str]]:
    """
    Verify all links in a YAML file.

    Args:
        file_path: Path to the YAML file

    Returns:
        List of failed links with details
    """
    failed_links = []

    print(f"Checking {file_path.name}...")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"  ❌ Error reading file: {e}")
        return failed_links

    links = extract_links(data)

    for title, field, url in links:
        print(f"  Checking {title} ({field}): {url}")
        success, error = check_url(url)

        if success:
            print(f"    ✓ OK")
        else:
            print(f"    ✗ FAILED: {error}")
            failed_links.append({
                'file': file_path.name,
                'title': title,
                'field': field,
                'url': url,
                'error': error
            })

    return failed_links

def main():
    """Main function to verify all links."""
    print("=" * 80)
    print("Link Verification Report")
    print("=" * 80)
    print()

    all_failed_links = []

    for filename in FILES_TO_CHECK:
        file_path = DATA_DIR / filename

        if not file_path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue

        failed = verify_file_links(file_path)
        all_failed_links.extend(failed)
        print()

    print("=" * 80)
    print("Summary")
    print("=" * 80)

    if all_failed_links:
        print(f"\n❌ Found {len(all_failed_links)} failed link(s):\n")

        for idx, link in enumerate(all_failed_links, 1):
            print(f"{idx}. [{link['file']}] {link['title']} ({link['field']})")
            print(f"   URL: {link['url']}")
            print(f"   Error: {link['error']}")
            print()

        # Output for GitHub Actions
        print("::group::Failed Links (Markdown)")
        print("\n### Failed Links\n")
        for idx, link in enumerate(all_failed_links, 1):
            print(f"{idx}. **{link['title']}** (`{link['file']}` - `{link['field']}`)")
            print(f"   - URL: [{link['url']}]({link['url']})")
            print(f"   - Error: {link['error']}")
        print("::endgroup::")

        sys.exit(1)
    else:
        print("\n✅ All links are accessible!\n")
        sys.exit(0)

if __name__ == '__main__':
    main()
