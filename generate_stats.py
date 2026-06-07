#!/usr/bin/env python3
import os
import sys
import requests
import json
import base64
import colorsys
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
import argparse
from io import BytesIO
from language_colors import OFFICIAL_LANGUAGE_COLORS
try:
    from cairosvg import svg2png
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False


# Contribution-grid colours: empty + 4 intensities (GitHub green, matches the original strip).
GRID_LEVELS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]


def fmt_num(n: int) -> str:
    """Format an integer using '.' as the thousands separator (e.g. 12345 -> '12.345')."""
    return f"{n:,}".replace(",", ".")


def level_for_count(count: int, max_count: int) -> int:
    """Map a daily contribution count to an intensity level 0-4 (harvested from contrib-main)."""
    if count <= 0 or max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def load_token(cli_token: Optional[str] = None) -> Optional[str]:
    """Resolve a GitHub token from CLI arg, env, or ~/.config (harvested from contrib-main).

    Order: --token > GITHUB_TOKEN/REDIRECT_GITHUB_TOKEN env > ~/.config/github-token.txt
    """
    if cli_token:
        return cli_token.strip()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("REDIRECT_GITHUB_TOKEN")
    if token:
        return token.strip()
    token_path = os.path.expanduser("~/.config/github-token.txt")
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
            return token or None
    except OSError:
        return None


class GitHubStatsGenerator:
    def __init__(self, token: str, username: Optional[str] = None) -> None:
        self.token = token
        self.username = username
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = 'https://api.github.com'

        if not self.username:
            self.username = self._get_authenticated_user()

    def _get_authenticated_user(self) -> str:
        """Get the authenticated user's username"""
        response = requests.get(f'{self.base_url}/user', headers=self.headers)
        response.raise_for_status()
        return str(response.json()['login'])

    def get_user_info(self) -> Dict[str, Any]:
        """Fetch comprehensive user information"""
        response = requests.get(f'{self.base_url}/users/{self.username}', headers=self.headers)
        response.raise_for_status()
        data = response.json()

        # Calculate account age
        created_at = datetime.strptime(data['created_at'], "%Y-%m-%dT%H:%M:%SZ")
        account_age = datetime.now() - created_at
        months_ago = int(account_age.days / 30)

        # Get avatar as base64
        avatar_url = data.get('avatar_url', '')
        avatar_data = ''
        if avatar_url:
            try:
                avatar_response = requests.get(avatar_url)
                if avatar_response.status_code == 200:
                    avatar_data = base64.b64encode(avatar_response.content).decode('utf-8')
            except:
                pass

        return {
            'login': data['login'],
            'name': data.get('name', data['login']),
            'followers': data['followers'],
            'following': data['following'],
            'public_repos': data['public_repos'],
            'public_gists': data['public_gists'],
            'created_at': data['created_at'],
            'months_ago': months_ago,
            'avatar_url': avatar_url,
            'avatar_data': avatar_data
        }

    def get_repositories(self) -> List[Dict[str, Any]]:
        """Fetch all user repositories (including private if authenticated)"""
        repos: List[Dict[str, Any]] = []
        page = 1

        # Check if we're fetching for the authenticated user
        try:
            auth_user = self._get_authenticated_user()
            is_auth_user = (self.username == auth_user or not self.username)
        except:
            is_auth_user = False

        while page <= 10:  # Limit to avoid rate limits
            # Use /user/repos for authenticated user to get private repos
            params: Dict[str, Any]
            if is_auth_user:
                endpoint = f'{self.base_url}/user/repos'
                params = {'page': page, 'per_page': 100, 'visibility': 'all', 'sort': 'updated'}
            else:
                endpoint = f'{self.base_url}/users/{self.username}/repos'
                params = {'page': page, 'per_page': 100, 'type': 'all', 'sort': 'updated'}

            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            repos.extend(data)
            page += 1
            if len(data) < 100:
                break
        return repos

    def get_detailed_stats(self, author_names: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed statistics"""
        repos = self.get_repositories()

        stats: Dict[str, Any] = {
            'total_commits': 0,
            'total_prs_opened': 0,
            'total_prs_reviewed': 0,
            'total_issues_opened': 0,
            'total_comments': 0,
            'total_stars': 0,
            'total_watchers': 0,
            'total_forks': 0,
            'total_size_kb': 0,
            'repos_contributed_to': 0,
            'orgs': 0,
            'licenses': defaultdict(int),
            'releases': 0,
            'packages': 0,
            'sponsors': 0,
            'sponsoring': 0,
            'starred_repos': 0,
            'watching_repos': 0
        }

        # Count contributed repos (owner or contributor)
        stats['repos_contributed_to'] = len(repos)

        for repo in repos:
            stats['total_stars'] += repo.get('stargazers_count', 0)
            stats['total_watchers'] += repo.get('watchers_count', 0)
            stats['total_forks'] += repo.get('forks_count', 0)
            stats['total_size_kb'] += repo.get('size', 0)

            license_info = repo.get('license')
            if license_info and license_info.get('spdx_id'):
                stats['licenses'][license_info['spdx_id']] += 1

        # Get commit count
        try:
            commit_params: Dict[str, Any] = {'q': f'author:{self.username}', 'per_page': 1}
            search_response = requests.get(
                f'{self.base_url}/search/commits',
                headers={**self.headers, 'Accept': 'application/vnd.github.cloak-preview+json'},
                params=commit_params
            )
            if search_response.status_code == 200:
                stats['total_commits'] = search_response.json().get('total_count', 0)
        except Exception as e:
            print(f"Warning: Could not fetch commit count", file=sys.stderr)

        # Get issues and PRs
        try:
            issue_params: Dict[str, Any] = {'q': f'author:{self.username} type:issue', 'per_page': 1}
            issues_response = requests.get(
                f'{self.base_url}/search/issues',
                headers=self.headers,
                params=issue_params
            )
            if issues_response.status_code == 200:
                stats['total_issues_opened'] = issues_response.json().get('total_count', 0)

            pr_params: Dict[str, Any] = {'q': f'author:{self.username} type:pr', 'per_page': 1}
            prs_response = requests.get(
                f'{self.base_url}/search/issues',
                headers=self.headers,
                params=pr_params
            )
            if prs_response.status_code == 200:
                stats['total_prs_opened'] = prs_response.json().get('total_count', 0)
        except Exception as e:
            print(f"Warning: Could not fetch issue/PR counts", file=sys.stderr)

        # Get organizations
        try:
            orgs_response = requests.get(f'{self.base_url}/users/{self.username}/orgs', headers=self.headers)
            if orgs_response.status_code == 200:
                stats['orgs'] = len(orgs_response.json())
        except:
            pass

        preferred_license = 'MIT'
        if stats['licenses']:
            preferred_license = max(stats['licenses'].items(), key=lambda x: x[1])[0]

        return {**stats, 'preferred_license': preferred_license}

    def get_language_stats(self) -> Tuple[List[Dict[str, Any]], int, int, int]:
        """Calculate language statistics"""
        repos = self.get_repositories()
        language_bytes: Dict[str, int] = defaultdict(int)
        total_files = 0
        total_commits = 0

        for repo in repos:
            try:
                response = requests.get(
                    f'{self.base_url}/repos/{repo["owner"]["login"]}/{repo["name"]}/languages',
                    headers=self.headers
                )
                response.raise_for_status()
                languages = response.json()

                for lang, bytes_count in languages.items():
                    language_bytes[lang] += bytes_count
            except:
                continue

        total_bytes = sum(language_bytes.values())
        if total_bytes == 0:
            return [], 0, 0, 0

        language_stats: List[Dict[str, Any]] = []
        for lang, bytes_count in sorted(language_bytes.items(), key=lambda x: x[1], reverse=True):
            percentage = (bytes_count / total_bytes) * 100
            language_stats.append({
                'name': lang,
                'percentage': percentage,
                'bytes': bytes_count
            })

        return language_stats, total_bytes, total_files, total_commits

    def get_recent_contributions(self, days: int = 14) -> List[int]:
        """Fetch real daily contribution counts for the last `days` days via the GraphQL API.

        Returns a list of integers (oldest to newest, length `days`). On any failure
        returns an empty list so the caller can fall back gracefully.
        """
        to = datetime.utcnow()
        frm = to - timedelta(days=days + 7)  # small buffer so the calendar covers the window
        query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar {
                weeks { contributionDays { contributionCount date } }
              }
            }
          }
        }
        """
        variables: Dict[str, Any] = {
            'login': self.username,
            'from': frm.replace(microsecond=0).isoformat() + 'Z',
            'to': to.replace(microsecond=0).isoformat() + 'Z',
        }
        try:
            resp = requests.post(
                'https://api.github.com/graphql',
                json={'query': query, 'variables': variables},
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            user = data.get('data', {}).get('user')
            if 'errors' in data or not user:
                return []
            weeks = user['contributionsCollection']['contributionCalendar']['weeks']
        except Exception:
            print("Warning: Could not fetch contribution calendar", file=sys.stderr)
            return []

        counts: Dict[str, int] = {}
        for week in weeks:
            for day in week.get('contributionDays', []):
                counts[day['date']] = int(day.get('contributionCount', 0))

        # Take the last `days` calendar days ending today (UTC), oldest to newest.
        result: List[int] = []
        for i in range(days - 1, -1, -1):
            d = (to.date() - timedelta(days=i)).isoformat()
            result.append(counts.get(d, 0))
        return result


class MetricsStyleSVGGenerator:
    # Official GitHub/Linguist language colours live in language_colors.py (the full
    # ~670-language table). _mute_color() softens them at render time so the card keeps
    # its muted aesthetic while every language retains its recognisable hue.
    OFFICIAL_LANGUAGE_COLORS = OFFICIAL_LANGUAGE_COLORS

    # Reserved neutral grey for the grouped "Others" segment.
    OTHERS_COLOR = '#858585'

    def __init__(self, custom_css: str = '') -> None:
        self.custom_css = custom_css

    @staticmethod
    def _mute_color(hex_color: str) -> str:
        """Soften a colour toward the card's muted aesthetic, preserving its hue.

        Lowers saturation and clamps brightness to a mid band, so bright official
        brand colours become muted while staying distinct from one another.
        """
        r = int(hex_color[1:3], 16) / 255
        g = int(hex_color[3:5], 16) / 255
        b = int(hex_color[5:7], 16) / 255
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        s *= 0.55                       # desaturate
        v = max(0.42, min(v, 0.74))     # clamp brightness into a muted mid band
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return '#{:02X}{:02X}{:02X}'.format(int(r * 255), int(g * 255), int(b * 255))

    def get_language_color(self, language: str) -> str:
        """Return a muted colour for a language.

        Known languages use the official GitHub colour, softened by _mute_color().
        "Others" stays neutral grey. Anything else gets a deterministic muted colour
        derived from its name, so two unlisted languages never share a flat grey.
        """
        official = self.OFFICIAL_LANGUAGE_COLORS.get(language)
        if official:
            return self._mute_color(official)
        if language == 'Others':
            return self.OTHERS_COLOR
        # Deterministic muted colour: stable hue from the name, fixed low saturation.
        digest = hashlib.md5(language.encode('utf-8')).hexdigest()
        hue = (int(digest, 16) % 360) / 360.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.42, 0.66)
        return '#{:02X}{:02X}{:02X}'.format(int(r * 255), int(g * 255), int(b * 255))

    def generate_contribution_grid(self, daily_counts: Optional[List[int]]) -> str:
        """Generate contribution grid (14 boxes) coloured by real daily contribution counts.

        `daily_counts` is a list of ints (oldest to newest). If empty/short it is
        left-padded with zeros so the strip always renders 14 boxes.
        """
        counts = list(daily_counts or [])
        if len(counts) < 14:
            counts = [0] * (14 - len(counts)) + counts
        counts = counts[-14:]
        max_count = max(counts) if counts else 0

        boxes = ''
        for i, count in enumerate(counts):
            level = level_for_count(count, max_count)
            color = GRID_LEVELS[level]
            x = 260 + (i * 13)  # More spacing for bigger boxes
            boxes += f'<rect x="{x}" y="18" width="11" height="11" fill="{color}" rx="2"/>'  # Bigger boxes, moved up to name line

        return boxes

    def generate_stats_svg(self, user_info: Dict[str, Any], detailed_stats: Dict[str, Any],
                           language_stats: List[Dict[str, Any]], total_bytes: int,
                           total_files: int, total_commits: int,
                           contribution_days: Optional[List[int]] = None) -> str:
        """Generate SVG matching lowlighter/metrics layout"""

        # Avatar with circular clip path
        avatar_img = ''
        if user_info['avatar_data']:
            avatar_img = f'''
            <defs>
                <clipPath id="avatar-clip">
                    <circle cx="25" cy="25" r="15"/>
                </clipPath>
            </defs>
            <image x="10" y="10" width="30" height="30"
                   href="data:image/png;base64,{user_info["avatar_data"]}"
                   clip-path="url(#avatar-clip)"/>'''

        # Contribution grid (real recent daily activity)
        contribution_grid = self.generate_contribution_grid(contribution_days)

        # Language progress bar with rounded corners (taller)
        # Show max 8 labels: top 7 languages + "Others" for the rest
        MAX_MAIN_LANGUAGES = 7
        main_languages = language_stats[:MAX_MAIN_LANGUAGES]

        # Group remaining languages into "Others"
        others_percentage = 0
        for lang in language_stats[MAX_MAIN_LANGUAGES:]:
            others_percentage += lang['percentage']

        # Add "Others" if there are grouped languages
        display_languages = main_languages.copy()
        if others_percentage > 0:
            display_languages.append({
                'name': 'Others',
                'percentage': others_percentage,
                'bytes': 0
            })

        lang_bars = ''
        total_width = 420
        x_offset = 10

        # Create background bar first (taller with better border radius)
        lang_bars += f'<rect x="{x_offset}" y="0" width="{total_width}" height="12" fill="#ebedf0" rx="6"/>'

        # Create a clipping path for rounded corners
        lang_bars += f'<defs><clipPath id="rounded-bar"><rect x="{x_offset}" y="0" width="{total_width}" height="12" rx="6"/></clipPath></defs>'

        # Overlay language segments with clipping (ordered left to right, most to least used)
        for lang in display_languages:
            width = (lang['percentage'] / 100) * total_width
            color = self.get_language_color(lang['name'])
            lang_bars += f'<rect x="{x_offset}" y="0" width="{width}" height="12" fill="{color}" clip-path="url(#rounded-bar)"/>'
            x_offset += width

        # Language list (grid layout - 4 columns, ordered most to least, Others at end)
        lang_items = ''
        for i, lang in enumerate(display_languages):
            col = i % 4
            row = i // 4
            x = 60 + (col * 110)
            y = 134 + (row * 16)  # Sits just below the language bar
            color = self.get_language_color(lang['name'])
            lang_items += f'''
            <circle cx="{x}" cy="{y}" r="5" fill="{color}"/>
            <text x="{x + 10}" y="{y + 4}" class="lang-item">{lang['name']}</text>'''

        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="170" viewBox="0 0 480 170">
    <defs>
        <style>
            * {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            }}
            .header {{
                fill: #bab7b1;
                font-size: 16px;
                font-weight: 400;
            }}
            .subtext {{
                fill: #969289;
                font-size: 12px;
            }}
            .section-title {{
                fill: #969289;
                font-size: 13px;
                font-weight: 400;
            }}
            .stat-line {{
                fill: #969289;
                font-size: 12px;
            }}
            .lang-item {{
                fill: #969289;
                font-size: 11px;
            }}
            {self.custom_css}
        </style>
    </defs>

    <!-- Background (transparent) -->
    <rect width="480" height="170" fill="none"/>

    <!-- Profile Picture -->
    {avatar_img}

    <!-- Header -->
    <text x="50" y="30" class="header">{user_info['name']}</text>

    <!-- Contribution Grid (on same line as name) -->
    {contribution_grid}
    <text x="260" y="42" class="subtext" style="font-size: 11px;">Contributed to {detailed_stats['repos_contributed_to']} repositories</text>

    <text x="20" y="65" class="subtext">{fmt_num(detailed_stats['total_commits'])} Commits, {fmt_num(detailed_stats['total_stars'])} stargazers since joining GitHub {user_info['months_ago']} months ago</text>

    <!-- Languages Section -->
    <text x="20" y="95" class="section-title">{len(language_stats)} Languages</text>

    <!-- Language progress bar -->
    <g transform="translate(10, 112)">
        {lang_bars}
    </g>

    <!-- Language list -->
    {lang_items}
</svg>'''

        return svg_content


def convert_svg_to_png(svg_content: str, output_path: str, scale: float = 2) -> None:
    """Convert SVG to PNG"""
    if not CAIROSVG_AVAILABLE:
        raise ImportError("cairosvg required for PNG. Install: pip install cairosvg")

    print(f"Converting to PNG (scale={scale})...")
    svg2png(bytestring=svg_content.encode('utf-8'), write_to=output_path, scale=scale)


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate GitHub statistics (metrics-style)')
    parser.add_argument('--token', help='GitHub personal access token (falls back to $GITHUB_TOKEN or ~/.config/github-token.txt)')
    parser.add_argument('--username', help='GitHub username')
    parser.add_argument('--output', default='stats.png', help='Output file (.svg or .png)')
    parser.add_argument('--format', choices=['svg', 'png'], help='Output format')
    parser.add_argument('--custom-css', default='', help='Custom CSS')
    parser.add_argument('--author-names', help='Author names for commit filtering')
    parser.add_argument('--scale', type=float, default=2.0, help='PNG scale')

    args = parser.parse_args()

    output_format = args.format or ('png' if args.output.endswith('.png') else 'svg')

    if output_format == 'png' and not CAIROSVG_AVAILABLE:
        print("Error: PNG requires cairosvg. Install: pip install cairosvg", file=sys.stderr)
        sys.exit(1)

    token = load_token(args.token)
    if not token:
        print("Error: no GitHub token found. Pass --token, set $GITHUB_TOKEN, "
              "or create ~/.config/github-token.txt", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching stats for {args.username or 'authenticated user'}...")

    stats_gen = GitHubStatsGenerator(token, args.username)

    print("Fetching user info...")
    user_info = stats_gen.get_user_info()

    print("Analyzing statistics...")
    detailed_stats = stats_gen.get_detailed_stats(args.author_names)

    print("Analyzing languages...")
    language_stats, total_bytes, total_files, total_commits = stats_gen.get_language_stats()

    print("Fetching recent contributions...")
    contribution_days = stats_gen.get_recent_contributions(days=14)

    print("Generating image...")
    svg_gen = MetricsStyleSVGGenerator(args.custom_css)
    svg_content = svg_gen.generate_stats_svg(user_info, detailed_stats, language_stats,
                                             total_bytes, total_files, total_commits,
                                             contribution_days=contribution_days)

    output_path = args.output
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)

    if output_format == 'png':
        convert_svg_to_png(svg_content, output_path, scale=args.scale)
        print(f"✓ PNG generated: {output_path}")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"✓ SVG generated: {output_path}")

    print(f"  - Repos: {user_info['public_repos']}")
    print(f"  - Commits: {detailed_stats['total_commits']}")
    print(f"  - Languages: {len(language_stats)}")


if __name__ == '__main__':
    main()
