#!/usr/bin/env python3
import os
import sys
import requests
import base64
import colorsys
import hashlib
from html import escape
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Any, Dict, List, Optional
import argparse
from language_colors import OFFICIAL_LANGUAGE_COLORS
try:
    from cairosvg import svg2png
    CAIROSVG_AVAILABLE = True
except (ImportError, OSError):  # OSError: cairosvg installed but libcairo missing
    CAIROSVG_AVAILABLE = False


# Contribution-grid colours: empty + 4 intensities (GitHub green, matches the original strip).
GRID_LEVELS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

# Seconds before any GitHub request gives up.
TIMEOUT = 20


def fmt_num(n: int) -> str:
    """Format an integer using '.' as the thousands separator (e.g. 12345 -> '12.345')."""
    return f"{n:,}".replace(",", ".")


def level_thresholds(counts: List[int]) -> List[float]:
    """Quartile cut points over the non-zero counts, so one outlier day can't wash out the rest."""
    active = sorted(c for c in counts if c > 0)
    if not active:
        return [0.0, 0.0, 0.0]
    return [active[min(len(active) - 1, (len(active) * q) // 4)] for q in (1, 2, 3)]


def level_for_count(count: int, thresholds: List[float]) -> int:
    """Map a daily contribution count to an intensity level 0-4."""
    if count <= 0:
        return 0
    return 1 + sum(1 for t in thresholds if count > t)


def parse_merges(spec: Optional[str]) -> Dict[str, str]:
    """Parse "Blade=PHP, Twig=PHP" into {'Blade': 'PHP', 'Twig': 'PHP'}."""
    merges: Dict[str, str] = {}
    for pair in (spec or '').split(','):
        if '=' in pair:
            src, dst = (part.strip() for part in pair.split('=', 1))
            if src and dst:
                merges[src] = dst
    return merges


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
        self._auth_user: Optional[str] = None
        self._repos: Optional[List[Dict[str, Any]]] = None

        if not self.username:
            self.username = self._get_authenticated_user()

    def _get_authenticated_user(self) -> str:
        """Get the authenticated user's username"""
        if self._auth_user is None:
            response = requests.get(f'{self.base_url}/user', headers=self.headers, timeout=TIMEOUT)
            response.raise_for_status()
            self._auth_user = str(response.json()['login'])
        return self._auth_user

    def get_user_info(self) -> Dict[str, Any]:
        """Fetch comprehensive user information"""
        response = requests.get(f'{self.base_url}/users/{self.username}', headers=self.headers, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Calculate account age
        created_at = datetime.strptime(data['created_at'], "%Y-%m-%dT%H:%M:%SZ")
        account_age = datetime.now() - created_at
        months_ago = int(account_age.days / 30)

        # Get avatar as base64 (96px is enough for a 48px circle at 2x)
        avatar_url = data.get('avatar_url', '')
        avatar_data = ''
        avatar_mime = 'image/png'
        if avatar_url:
            try:
                sep = '&' if '?' in avatar_url else '?'
                avatar_response = requests.get(f'{avatar_url}{sep}s=96', timeout=TIMEOUT)
                if avatar_response.status_code == 200:
                    avatar_data = base64.b64encode(avatar_response.content).decode('utf-8')
                    avatar_mime = avatar_response.headers.get('Content-Type', avatar_mime).split(';')[0]
            except requests.RequestException:
                pass

        return {
            'login': data['login'],
            'name': data.get('name') or data['login'],
            'followers': data['followers'],
            'following': data['following'],
            'public_repos': data['public_repos'],
            'public_gists': data['public_gists'],
            'created_at': data['created_at'],
            'months_ago': months_ago,
            'avatar_url': avatar_url,
            'avatar_data': avatar_data,
            'avatar_mime': avatar_mime
        }

    def get_repositories(self) -> List[Dict[str, Any]]:
        """Fetch all user repositories (including private if authenticated), once per run"""
        if self._repos is not None:
            return self._repos
        repos: List[Dict[str, Any]] = []
        page = 1

        # Check if we're fetching for the authenticated user
        try:
            auth_user = self._get_authenticated_user()
            is_auth_user = (self.username == auth_user or not self.username)
        except requests.RequestException:
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

            response = requests.get(endpoint, headers=self.headers, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            repos.extend(data)
            page += 1
            if len(data) < 100:
                break
        self._repos = repos
        return repos

    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get the repository, stargazer and commit totals shown on the card"""
        repos = self.get_repositories()
        stats: Dict[str, Any] = {
            'repos_contributed_to': len(repos),
            'total_stars': sum(repo.get('stargazers_count', 0) for repo in repos),
            'total_commits': 0,
        }

        try:
            commit_params: Dict[str, Any] = {'q': f'author:{self.username}', 'per_page': 1}
            search_response = requests.get(
                f'{self.base_url}/search/commits',
                headers={**self.headers, 'Accept': 'application/vnd.github.cloak-preview+json'},
                params=commit_params,
                timeout=TIMEOUT,
            )
            if search_response.status_code == 200:
                stats['total_commits'] = search_response.json().get('total_count', 0)
        except requests.RequestException:
            print("Warning: Could not fetch commit count", file=sys.stderr)

        return stats

    def get_language_stats(self, merges: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """Calculate language statistics; `merges` folds one language's bytes into another."""
        merges = merges or {}
        repos = self.get_repositories()
        language_bytes: Dict[str, int] = defaultdict(int)

        for repo in repos:
            try:
                response = requests.get(
                    f'{self.base_url}/repos/{repo["owner"]["login"]}/{repo["name"]}/languages',
                    headers=self.headers,
                    timeout=TIMEOUT,
                )
                response.raise_for_status()
                languages = response.json()

                for lang, bytes_count in languages.items():
                    language_bytes[merges.get(lang, lang)] += bytes_count
            except requests.RequestException:
                print(f"Warning: Could not fetch languages for {repo['name']}", file=sys.stderr)

        total_bytes = sum(language_bytes.values())
        if total_bytes == 0:
            return []

        language_stats: List[Dict[str, Any]] = []
        for lang, bytes_count in sorted(language_bytes.items(), key=lambda x: x[1], reverse=True):
            percentage = (bytes_count / total_bytes) * 100
            language_stats.append({
                'name': lang,
                'percentage': percentage,
                'bytes': bytes_count
            })

        return language_stats

    def get_recent_contributions(self, days: int = 14) -> List[int]:
        """Fetch daily contribution counts for the last `days` complete days (ending yesterday, UTC).

        Returns a list of integers (oldest to newest, length `days`). On any failure
        returns an empty list so the caller can fall back gracefully.
        """
        to = datetime.now(timezone.utc).replace(tzinfo=None)
        last_day = to.date() - timedelta(days=1)
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
                timeout=TIMEOUT,
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

        # Take the last `days` calendar days ending yesterday (UTC), oldest to newest.
        result: List[int] = []
        for i in range(days - 1, -1, -1):
            d = (last_day - timedelta(days=i)).isoformat()
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

    # Canvas matches the profile resume.svg: 960 wide, content spans x=40..880.
    WIDTH = 960
    LEFT = 40
    RIGHT = 880
    GRID_DAYS = 14

    def generate_contribution_grid(self, daily_counts: Optional[List[int]]) -> str:
        """Generate the 14-day strip, right-aligned on the header row, coloured by real daily counts.

        `daily_counts` is a list of ints (oldest to newest). If empty/short it is
        left-padded with zeros so the strip always renders 14 boxes.
        """
        counts = list(daily_counts or [])
        if len(counts) < self.GRID_DAYS:
            counts = [0] * (self.GRID_DAYS - len(counts)) + counts
        counts = counts[-self.GRID_DAYS:]
        thresholds = level_thresholds(counts)

        size, gap = 18, 6
        x0 = self.RIGHT - (self.GRID_DAYS * size + (self.GRID_DAYS - 1) * gap)
        boxes = ''
        for i, count in enumerate(counts):
            level = level_for_count(count, thresholds)
            paint = 'class="empty"' if level == 0 else f'fill="{GRID_LEVELS[level]}"'
            boxes += f'\n    <rect {paint} x="{x0 + i * (size + gap)}" y="20" width="{size}" height="{size}" rx="4"/>'
        return boxes

    def generate_stats_svg(self, user_info: Dict[str, Any], detailed_stats: Dict[str, Any],
                           language_stats: List[Dict[str, Any]],
                           contribution_days: Optional[List[int]] = None,
                           animate: bool = True) -> str:
        """Generate the stats card in the same visual language as the profile resume.svg."""
        name = escape(user_info['name'])

        # Avatar with circular clip path
        avatar_img = ''
        name_x = self.LEFT
        if user_info['avatar_data']:
            avatar_img = f'''
    <clipPath id="avatar-clip"><circle cx="64" cy="44" r="24"/></clipPath>
    <image x="40" y="20" width="48" height="48" clip-path="url(#avatar-clip)"
           href="data:{user_info.get('avatar_mime', 'image/png')};base64,{user_info['avatar_data']}"/>'''
            name_x = 108

        contribution_grid = self.generate_contribution_grid(contribution_days)

        # Show max 8 labels: top 7 languages + "Others" for the rest
        MAX_MAIN_LANGUAGES = 7
        display_languages = language_stats[:MAX_MAIN_LANGUAGES]
        others_percentage = sum(lang['percentage'] for lang in language_stats[MAX_MAIN_LANGUAGES:])
        if others_percentage > 0:
            display_languages = display_languages + [{'name': 'Others', 'percentage': others_percentage, 'bytes': 0}]

        bar_y, bar_h = 192, 24
        bar_w = self.RIGHT - self.LEFT
        segments = ''
        x = float(self.LEFT)
        for i, lang in enumerate(display_languages):
            width = (lang['percentage'] / 100) * bar_w
            # 1px overlap into the next segment hides anti-aliasing seams
            drawn = width + (1 if i < len(display_languages) - 1 else 0)
            segments += (f'\n      <rect x="{x:.1f}" y="{bar_y}" width="{drawn:.1f}" height="{bar_h}" '
                         f'fill="{self.get_language_color(lang["name"])}"/>')
            x += width

        # Language legend: 4 columns, most to least used, Others last
        legend_y, row_h, col_w = 248, 32, 210
        lang_items = ''
        for i, lang in enumerate(display_languages):
            lx = self.LEFT + (i % 4) * col_w
            ly = legend_y + (i // 4) * row_h
            lang_items += f'''
    <circle cx="{lx + 8}" cy="{ly - 6}" r="8" fill="{self.get_language_color(lang['name'])}"/>
    <text class="sans primary" x="{lx + 26}" y="{ly}" font-size="16">{escape(lang['name'])}<tspan class="muted"> {lang['percentage']:.1f}%</tspan></text>'''

        rows = max(1, (len(display_languages) + 3) // 4)
        height = legend_y + (rows - 1) * row_h + 24

        rise = 'rise ' if animate else ''
        commits = fmt_num(detailed_stats['total_commits'])
        stars = fmt_num(detailed_stats['total_stars'])

        return f'''<svg viewBox="0 0 {self.WIDTH} {height}" width="{self.WIDTH}" height="{height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GitHub metrics — {name}: {commits} commits, {len(language_stats)} languages">
  <style>
    .sans {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", "DejaVu Sans", Helvetica, Arial, sans-serif; }}
    .primary {{ fill: #1f2328; }}
    .muted   {{ fill: #57544e; }}
    .empty   {{ fill: #ebedf0; }}
    @media (prefers-color-scheme: dark) {{
      .primary {{ fill: #f0f6fc; }}
      .muted   {{ fill: #a6a39b; }}
      .empty   {{ fill: #2d333b; }}
    }}

    .rise {{ opacity: 0; animation: rise .7s cubic-bezier(.2,.7,.2,1) forwards; }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    .a1 {{ animation-delay: .05s; }}
    .a2 {{ animation-delay: .15s; }}
    .a3 {{ animation-delay: .25s; }}
    @media (prefers-reduced-motion: reduce) {{ .rise {{ animation: none; opacity: 1; }} }}
    {self.custom_css}
  </style>

  <!-- HEADER -->
  <g class="{rise}a1">{avatar_img}
    <text class="sans primary" x="{name_x}" y="52" font-size="24">{name}</text>{contribution_grid}
    <text class="sans muted" x="{self.RIGHT}" y="66" font-size="15" text-anchor="end">Contributed to {detailed_stats['repos_contributed_to']} repositories</text>
  </g>
  <!-- SUMMARY -->
  <g class="{rise}a2">
    <text class="sans muted" x="{self.LEFT}" y="116" font-size="16">{commits} Commits, {stars} stargazers since joining GitHub {user_info['months_ago']} months ago</text>
  </g>
  <!-- LANGUAGES -->
  <g class="{rise}a3">
    <text class="sans muted" x="{self.LEFT}" y="168" font-size="24">{len(language_stats)} Languages</text>
    <clipPath id="lang-bar"><rect x="{self.LEFT}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{bar_h // 2}"/></clipPath>
    <g clip-path="url(#lang-bar)">
      <rect class="empty" x="{self.LEFT}" y="{bar_y}" width="{bar_w}" height="{bar_h}"/>{segments}
    </g>{lang_items}
  </g>
</svg>
'''


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
    parser.add_argument('--output', default='stats.svg', help='Output file (.svg or .png)')
    parser.add_argument('--format', choices=['svg', 'png'], help='Output format')
    parser.add_argument('--custom-css', default='', help='Custom CSS')
    parser.add_argument('--author-names', help='Deprecated and ignored: commits are already matched to every email linked to the account')
    parser.add_argument('--scale', type=float, default=2.0, help='PNG scale')
    parser.add_argument('--merge-languages', default='', help='Count one language as another, e.g. "Blade=PHP,Twig=PHP"')

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
    detailed_stats = stats_gen.get_detailed_stats()

    print("Analyzing languages...")
    language_stats = stats_gen.get_language_stats(parse_merges(args.merge_languages))

    print("Fetching recent contributions...")
    contribution_days = stats_gen.get_recent_contributions(days=14)

    print("Generating image...")
    svg_gen = MetricsStyleSVGGenerator(args.custom_css)
    svg_content = svg_gen.generate_stats_svg(user_info, detailed_stats, language_stats,
                                             contribution_days=contribution_days,
                                             animate=(output_format == 'svg'))

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
