import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


def load_env_file(env_path: Path) -> dict:
    vals = dotenv_values(env_path)
    return {k: v for k, v in vals.items() if k and v is not None}


def run(cmd: list[str], env: dict) -> None:
    subprocess.check_call(cmd, env=env)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env_dir", default="out/sites", help="Directory containing per-site .env files")
    ap.add_argument("--site", default="", help="Optional: run only one site key (e.g. cluj -> cluj.env)")
    ap.add_argument("--draft_dir", default="drafts_legal", help="Where legal draft JSONs are written")
    ap.add_argument("--status", default="publish", choices=["draft", "publish"], help="WP page status")
    args = ap.parse_args()

    env_dir = Path(args.env_dir)
    if not env_dir.exists():
        raise SystemExit(f"Env dir not found: {env_dir}")

    env_files = sorted(env_dir.glob("*.env"))
    if args.site:
        wanted = env_dir / f"{args.site}.env"
        env_files = [wanted] if wanted.exists() else []
    if not env_files:
        raise SystemExit("No env files found to run.")

    for env_path in env_files:
        site_env = load_env_file(env_path)

        # Combine current environment + site environment
        env = os.environ.copy()
        env.update(site_env)

        site_key = site_env.get("SITE_KEY") or env_path.stem
        wp_base = site_env.get("WP_BASE_URL", "")
        print(f"\n=== {site_key} -> {wp_base} ===")

        # 1) render legal drafts using that env file
        run(
            [
                sys.executable,
                "src/render_legal_drafts.py",
                "--env",
                str(env_path),
                "--out",
                args.draft_dir,
            ],
            env=env,
        )

        # 2) publish drafts to that WP instance (env passed in, so publish_wp.py works unchanged)
        run(
            [
                sys.executable,
                "src/publish_wp.py",
                "--dir",
                args.draft_dir,
                "--status",
                args.status,
            ],
            env=env,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
