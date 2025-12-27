#!/usr/bin/env python3
"""
Test script to generate GitHub stats locally before committing.

Usage:
    python local_stats.py                    # Will prompt for token
    python local_stats.py YOUR_TOKEN         # Pass token directly
    GITHUB_TOKEN=xxx python local_stats.py   # Use environment variable
"""

import os
import sys

def main():
    print("=" * 60)
    print("GitHub Stats Generator - Local Test")
    print("=" * 60)
    print()

    # Get GitHub token from args, environment, gh CLI, or prompt
    token = None

    if len(sys.argv) > 1:
        token = sys.argv[1]
        print("✓ Using token from command line argument")
    elif os.environ.get('GITHUB_TOKEN'):
        token = os.environ.get('GITHUB_TOKEN')
        print("✓ Using GITHUB_TOKEN from environment")
    else:
        # Try to get token from GitHub CLI
        try:
            import subprocess
            result = subprocess.run(['gh', 'auth', 'token'],
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
                print("✓ Using token from GitHub CLI (gh auth token)")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if not token:
        print()
        print("No token found. You can provide it in these ways:")
        print("1. Command line: python local_stats.py YOUR_TOKEN")
        print("2. Environment:  GITHUB_TOKEN=xxx python local_stats.py")
        print("3. GitHub CLI:   gh auth login  (then run this script)")
        print("4. Type it now:")
        print()
        token = input("GitHub Token (or press Enter to skip): ").strip()

    if not token:
        print()
        print("Error: GitHub token is required!")
        print()
        print("Easiest option - Install and login with GitHub CLI:")
        print("  sudo apt install gh    # or: brew install gh")
        print("  gh auth login")
        print("  python local_stats.py")
        print()
        print("Or create a token at: https://github.com/settings/tokens")
        sys.exit(1)

    print()

    # Get username (optional)
    username = input("GitHub username (press Enter to use authenticated user): ").strip()

    # Output format
    print()
    print("Output format:")
    print("1. PNG (recommended)")
    print("2. SVG")
    choice = input("Choose format (1 or 2) [1]: ").strip() or "1"

    if choice == "1":
        output_format = "png"
        output_file = "test-stats.png"
    else:
        output_format = "svg"
        output_file = "test-stats.svg"

    # Custom CSS (matching your publish.yml config)
    custom_css = """
    h1.field, h1 span { color: #bab7b1!important }
    h2.field, h3.field { color: #969289!important }
    .field svg { fill:#969289!important }
    footer {display: none!important }
    """

    # Build command
    cmd_parts = [
        sys.executable,  # Current Python interpreter
        "generate_stats.py",
        "--token", token,
        "--output", output_file,
        "--format", output_format,
        "--custom-css", custom_css.strip()
    ]

    if username:
        cmd_parts.extend(["--username", username])

    # Author names (matching your config)
    author_names = "Luciano Pereira, Luciano Federico Pereira, lucianofedericopereira, lucianofedericopereira@users.noreply.github.com, lucianopereira@posteo.es"
    cmd_parts.extend(["--author-names", author_names])

    print()
    print("=" * 60)
    print("Running stats generator...")
    print("=" * 60)
    print()

    # Run the command
    import subprocess
    try:
        result = subprocess.run(cmd_parts, check=True)

        print()
        print("=" * 60)
        print(f"✓ Success! Stats saved to: {output_file}")
        print("=" * 60)
        print()

        # Check if file exists and show size
        if os.path.exists(output_file):
            size_kb = os.path.getsize(output_file) / 1024
            print(f"File size: {size_kb:.1f} KB")
            print()
            print("Features included in this version:")
            print("  ✓ Circular profile picture with proper spacing")
            print("  ✓ Taller rounded language progress bars (12px, fully rounded)")
            print("  ✓ Transparent background")
            print("  ✓ Clean text (no emoji icons)")
            print("  ✓ 14 contribution boxes (11x11px, inline with username)")
            print("  ✓ Activity colors only (no empty/white boxes)")
            print("  ✓ Includes private repositories")
            print("  ✓ Streamlined stats (removed releases/packages)")
            print("  ✓ Custom colors from your workflow")
            print()

            # Try to open the file
            if output_format == "png":
                print("To view the PNG file, run:")
                print(f"  xdg-open {output_file}  # Linux")
                print(f"  open {output_file}      # macOS")
                print(f"  start {output_file}     # Windows")
            else:
                print("To view the SVG file, open it in your browser:")
                print(f"  file://{os.path.abspath(output_file)}")

            print()

            # Ask if user wants to view it
            view = input("Open the file now? (y/n) [n]: ").strip().lower()
            if view == 'y':
                import platform
                system = platform.system()

                if system == "Linux":
                    subprocess.run(["xdg-open", output_file])
                elif system == "Darwin":  # macOS
                    subprocess.run(["open", output_file])
                elif system == "Windows":
                    os.startfile(output_file)

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 60)
        print("✗ Error generating stats!")
        print("=" * 60)
        print()
        print("Please check the error messages above.")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("Cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
