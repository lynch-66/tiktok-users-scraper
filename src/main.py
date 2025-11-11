thonimport argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Ensure the src directory (this file's directory) is on sys.path so we can import sibling packages
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from extractors.tiktok_parser import TikTokUserScraper  # type: ignore
from outputs.dataset_exporter import DatasetExporter  # type: ignore

def load_json_file(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(f"JSON file not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def setup_logging(level_str: str) -> None:
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def resolve_output_directory(arg_output_dir: str | None, config: Dict[str, Any]) -> str:
    if arg_output_dir:
        output_dir = arg_output_dir
    else:
        output_dir = config.get("output", {}).get("directory", "data")
    # If path is not absolute, resolve relative to project root
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(PROJECT_ROOT, output_dir)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok Users Scraper")
    parser.add_argument(
        "--input",
        default=os.path.join(PROJECT_ROOT, "data", "input.sample.json"),
        help="Path to input JSON file containing keywords and limits.",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(CURRENT_DIR, "config", "settings.example.json"),
        help="Path to configuration JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to store exported datasets (overrides config).",
    )
    parser.add_argument(
        "--output-format",
        default=None,
        choices=["json", "csv", "xlsx", "html", "xml"],
        help="Output format (overrides input and config).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Maximum number of users to fetch per keyword (overrides input and config).",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_json_file(args.config)
    log_level = config.get("logging", {}).get("level", "INFO")
    setup_logging(log_level)
    logger = logging.getLogger("tiktok_scraper_main")

    logger.info("Starting TikTok Users Scraper")

    # Load input keywords and options
    try:
        input_payload = load_json_file(args.input)
    except Exception as exc:
        logger.error("Failed to load input file %s: %s", args.input, exc)
        raise SystemExit(1)

    keywords = input_payload.get("keywords") or []
    if not isinstance(keywords, list) or not keywords:
        logger.error("Input file must contain a non-empty 'keywords' array.")
        raise SystemExit(1)

    # Resolve limits and formats with priority: CLI > input > config
    max_items = (
        args.max_items
        if args.max_items is not None
        else input_payload.get("maxItems")
        if input_payload.get("maxItems") is not None
        else config.get("scraper", {}).get("max_items", 50)
    )

    output_format = (
        args.output_format
        if args.output_format is not None
        else input_payload.get("outputFormat")
        if input_payload.get("outputFormat") is not None
        else config.get("output", {}).get("format", "json")
    )

    output_dir = resolve_output_directory(args.output_dir, config)

    logger.info(
        "Resolved configuration - keywords=%s, max_items=%s, output_format=%s, output_dir=%s",
        keywords,
        max_items,
        output_format,
        output_dir,
    )

    # Instantiate scraper
    tiktok_cfg = config.get("tiktok", {})
    scraper = TikTokUserScraper(
        base_url=tiktok_cfg.get("base_url", "https://www.tiktok.com/api/search/user/full/"),
        user_agent=tiktok_cfg.get(
            "user_agent",
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        ),
        timeout_seconds=tiktok_cfg.get("timeout", 10),
        sleep_between_requests=config.get("scraper", {}).get("sleep_between_requests", 1.0),
        logger=logging.getLogger("tiktok_scraper"),
    )

    all_users: List[Dict[str, Any]] = []

    for keyword in keywords:
        keyword_str = str(keyword).strip()
        if not keyword_str:
            logger.warning("Skipping empty keyword entry in input.")
            continue

        logger.info("Searching users for keyword='%s' with max_items=%s", keyword_str, max_items)
        try:
            users = scraper.search_users(keyword_str, max_items=max_items)
        except Exception as exc:
            logger.exception("Unexpected error while scraping keyword '%s': %s", keyword_str, exc)
            continue

        # Tag each user with the keyword used to discover them
        for user in users:
            user.setdefault("search_keyword", keyword_str)
        logger.info("Collected %d users for keyword '%s'", len(users), keyword_str)

        all_users.extend(users)

    if not all_users:
        logger.warning("No users were collected for any keyword. Nothing to export.")
        raise SystemExit(0)

    base_filename = f"tiktok_users_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    exporter = DatasetExporter(logger=logging.getLogger("dataset_exporter"))

    try:
        output_path = exporter.export(
            records=all_users,
            fmt=output_format,
            output_dir=output_dir,
            base_filename=base_filename,
        )
    except Exception as exc:
        logger.exception("Failed to export dataset: %s", exc)
        raise SystemExit(1)

    logger.info("Export complete. File saved to: %s", output_path)
    print(output_path)

if __name__ == "__main__":
    main()