# Git Metrics

A lightweight Python script to generate GitHub statistics as customizable SVG or PNG images.

## Features

- Fetches GitHub user statistics via API
- Analyzes language usage across all repositories
- Generates clean, customizable SVG or PNG output
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

### GitHub Actions Integration

Add this workflow to `.github/workflows/update-stats.yml`:

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
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: pip install -r git-metrics-to-svg/requirements.txt

      - name: Generate stats
        run: |
          python git-metrics-to-svg/generate_stats.py \
            --token ${{ secrets.GITHUB_TOKEN }} \
            --output assets/stats.svg \
            --custom-css "h1.field, h1 span { color: #bab7b1!important }
            h2.field, h3.field { color: #969289!important }
            .field svg { fill:#969289!important }
            footer {display: none!important}"

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
| `--author-names` | No | - | Comma-separated author names for commit counting |

### GitHub Token

You need a GitHub personal access token with the following scopes:
- `public_repo` (for public repositories)
- `read:user` (for user information)

Create one at: https://github.com/settings/tokens

For GitHub Actions, use the built-in `${{ secrets.GITHUB_TOKEN }}` which has the necessary permissions.

## Customization

### Custom CSS Styling

The `--custom-css` parameter allows you to customize the appearance of your stats SVG:

```bash
python generate_stats.py \
  --token YOUR_TOKEN \
  --custom-css "
    h1.field, h1 span { color: #bab7b1!important }
    h2.field, h3.field { color: #969289!important }
    .field svg { fill:#969289!important }
    footer {display: none!important }
  "
```

### Available CSS Classes

- `.container` - Main container
- `h1.field` - Main heading
- `h2.field`, `h3.field` - Section headings
- `.stats-grid` - Stats grid layout
- `.stat-item` - Individual stat boxes
- `.stat-label` - Stat labels
- `.stat-value` - Stat values
- `.language-item` - Language list items
- `.language-name` - Language names
- `.language-percentage` - Language percentages

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

### Example 5: With Author Attribution

```bash
python generate_stats.py \
  --token ghp_xxxxxxxxxxxxx \
  --author-names "John Doe, johndoe, john.doe@example.com" \
  --output stats.svg
```

## What Statistics Are Included?

The generated image (SVG or PNG) includes:

- **Public Repositories** - Total number of public repos
- **Followers** - Number of followers
- **Following** - Number of users you follow
- **Public Gists** - Number of public gists
- **Most Used Languages** - Top 8 languages by bytes of code with percentages

## Comparison with lowlighter/metrics

| Feature | git-metrics-to-svg | lowlighter/metrics |
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

- Python 3.6+
- requests 2.31.0+
- cairosvg 2.7.1+ (for PNG output only)

## License

MIT License - feel free to use and modify this in your projects!

## Contributing

Contributions welcome! Feel free to:
- Report bugs
- Request new statistics/features
- Submit pull requests
- Improve documentation
