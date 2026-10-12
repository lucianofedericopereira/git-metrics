# Git Metrics

A lightweight Python script to generate GitHub statistics as customizable SVG or PNG images.

## Features

- Fetches GitHub user statistics via API
- Analyzes language usage across all repositories
- Generates clean, customizable SVG or PNG output
- SVG follows the viewer's light/dark theme and fades in (respects reduced motion)
- 14-day contribution strip of complete days, shaded by quartile
- Supports custom CSS styling
- In-depth language analysis
- Lightweight with minimal dependencies
- High-quality PNG rendering with configurable scale

## Quick Start

### Local Usage

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Generate your stats (SVG or PNG):
```bash
# Generate SVG
python generate_stats.py \
  --token YOUR_GITHUB_TOKEN \
  --output assets/stats.svg

# Generate PNG
python generate_stats.py \
  --token YOUR_GITHUB_TOKEN \
  --output assets/stats.png \
  --format png
```

### Use as a GitHub Action (recommended)

The simplest way to consume this from your own profile repo — no fork, no checkout
plumbing. Add a workflow that references this repo with `uses:`:

```yaml
name: Update GitHub Stats
on:
  schedule:
    - cron: "0 0 * * *"  # Daily at midnight
  workflow_dispatch:

permissions:
  contents: write

jobs:
  stats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Generate stats
        uses: lucianofedericopereira/git-metrics@main
        with:
          token: ${{ secrets.GITHUB_TOKEN }}   # use a PAT with read:user for private activity
          username: your-username
          output: assets/stats.svg

      - name: Commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add assets/stats.svg
          git diff --quiet && git diff --staged --quiet || git commit -m "Update stats [skip ci]"
          git push
```

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `token` | Yes | - | GitHub token (default `GITHUB_TOKEN` = public data; PAT with `read:user` for private) |
| `username` | No | authenticated user | GitHub username to analyze |
| `output` | No | `stats.svg` | Output file path (`.svg` or `.png`) |
| `format` | No | auto from extension | `svg` or `png` |
| `custom-css` | No | `''` | Custom CSS injected into the SVG |
| `author-names` | No | `''` | Deprecated, ignored (commits already match every email linked to the account) |
| `scale` | No | `2.0` | PNG scale factor |
| `merge-languages` | No | `''` | Count one language as another, e.g. `Blade=PHP,Twig=PHP` |
| `python-version` | No | `3.x` | Python version to set up |

> Pin to a tag (e.g. `@v1`) instead of `@main` for reproducible builds.

### GitHub Actions Integration (checkout-and-run)

Alternatively, check the script out and run it directly. Add this workflow to
`.github/workflows/update-stats.yml`:

```yaml
name: Update GitHub Stats
on:
  schedule:
    - cron: "0 0 * * *"  # Daily at midnight
  workflow_dispatch:

permissions:
  contents: write

jobs:
  github-stats:
    name: Stats Update
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Checkout git-metrics
        uses: actions/checkout@v7
        with:
          repository: lucianofedericopereira/git-metrics
          path: git-metrics

      - name: Setup Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: pip install -r git-metrics/requirements.txt

      - name: Generate stats
        run: |
          python git-metrics/generate_stats.py \
            --token ${{ secrets.GITHUB_TOKEN }} \
            --output assets/stats.svg

      - name: Commit changes
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add assets/stats.svg
          git diff --quiet && git diff --staged --quiet || git commit -m "Update stats [skip ci]"
          git push
```

## Configuration Options

### Command Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--token` | Yes | - | GitHub personal access token |
| `--username` | No | Authenticated user | GitHub username to analyze |
| `--output` | No | `stats.svg` | Output file path (.svg or .png) |
| `--format` | No | Auto-detected | Output format: `svg` or `png` |
| `--scale` | No | `2.0` | Scale factor for PNG output (higher = better quality) |
| `--custom-css` | No | `''` | Custom CSS to style the SVG |
| `--author-names` | No | - | Deprecated, ignored (commits already match every email linked to the account) |
| `--merge-languages` | No | `''` | Count one language as another, e.g. `Blade=PHP,Twig=PHP` |

### GitHub Token

You need a GitHub personal access token with the following scopes:
- `public_repo` (for public repositories)
- `read:user` (for user information)

Create one at: https://github.com/settings/tokens

For GitHub Actions, use the built-in `${{ secrets.GITHUB_TOKEN }}` which has the necessary permissions.

## Customization

### Custom CSS Styling

The `--custom-css` parameter is appended to the SVG's `<style>`, after the defaults, so
plain rules override them. Text is SVG, so colour it with `fill`, not `color`:

```bash
python generate_stats.py \
  --token YOUR_TOKEN \
  --custom-css ".primary { fill: #bab7b1 } .muted { fill: #969289 }
    @media (prefers-color-scheme: dark) { .primary { fill: #ebdbb2 } }"
```

### Available CSS Classes

- `.sans` - Font stack for all text
- `.primary` - Name and language names (`#1f2328`, dark `#f0f6fc`)
- `.muted` - Secondary text: repo count, summary, section title, percentages (`#57544e`, dark `#a6a39b`)
- `.empty` - Empty contribution boxes and the language bar track (`#ebedf0`, dark `#2d333b`)
- `.rise`, `.a1`-`.a3` - Fade-in animation on the header, summary and languages groups (SVG only)

PNG output is rendered by cairosvg, which ignores `@media`, so a PNG always uses the light palette.

## Examples

### Example 1: Basic Stats

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --output my-stats.svg
```

### Example 2: Stats for Specific User

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --username octocat \
  --output octocat-stats.svg
```

### Example 3: Custom Styling

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --output assets/stats.svg \
  --custom-css "h1 { color: #ff6b6b !important; } h2 { color: #4ecdc4 !important; }"
```

### Example 4: Generate PNG Output

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --output assets/stats.png \
  --format png \
  --scale 3.0
```

### Example 5: Count Blade as PHP

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --merge-languages "Blade=PHP" \
  --output stats.svg
```

## What Statistics Are Included?

The generated image (SVG or PNG) includes:

- **Avatar and name**
- **Contribution strip** - Daily contributions for the last 14 complete days (UTC)
- **Repositories** - Number of repositories contributed to
- **Commits and stargazers** - With account age in months
- **Languages** - Total count, a usage bar, and the top 7 by bytes plus "Others", with percentages

## Comparison with lowlighter/metrics

| Feature | git-metrics | lowlighter/metrics |
|---------|-------------------|-------------------|
| Setup complexity | Simple Python script | Docker-based action |
| Customization | Full code access | Configuration options |
| Dependencies | Minimal (requests only) | Large Docker image |
| Performance | Fast | Slower (Docker overhead) |
| Transparency | 100% readable Python | Complex codebase |
| Features | Core stats + languages | 50+ plugins available |

Use this tool if you want:
- Full control over your stats generation
- Simple, understandable code you can modify
- Faster execution times
- No Docker dependencies

Use lowlighter/metrics if you need:
- Advanced plugins (calendar, achievements, etc.)
- Complex visualizations
- Ready-made feature set

## Troubleshooting

### Authentication Failed
Make sure your GitHub token is valid and has the correct scopes:
- `public_repo`
- `read:user`

### Rate Limiting
GitHub API has rate limits (5,000 requests/hour for authenticated users). If you have many repositories, you might hit this limit. The script will show warnings for repositories it couldn't process.

### SVG Not Rendering
- Make sure the output path exists or the script will create it
- Check that the SVG file has valid XML syntax
- Some platforms may not support `<foreignObject>` in SVG

### PNG Generation Fails
- Make sure `cairosvg` is installed: `pip install cairosvg`
- On Linux, you may need to install cairo development files: `sudo apt-get install libcairo2-dev`
- On macOS: `brew install cairo`
- Try regenerating with a lower `--scale` value if memory issues occur

## Requirements

- Python 3.10+
- requests 2.34.2
- cairosvg 2.9.1 (for PNG output only)

## License

MIT License - feel free to use and modify this in your projects!

## Contributing

Contributions welcome! Feel free to:
- Report bugs
- Request new statistics/features
- Submit pull requests
- Improve documentation
