# -*- coding: utf-8 -*-
"""CLI запуск reviewer: python main.py --mr <IID> [--project <id>] [--gitlab-url <url>]"""

import argparse
import logging
import os

from dotenv import load_dotenv

from reviewer import run_review

load_dotenv()

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=LOG_LEVEL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MR review with RAG and LM")
    parser.add_argument("--mr", type=int, required=True, help="Merge Request IID")
    parser.add_argument("--project", type=str, default=None, help="GitLab project id/path override")
    parser.add_argument("--gitlab-url", type=str, default=None, help="GitLab URL override")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_review(args.mr, project_id=args.project, gitlab_url=args.gitlab_url)
    print(result)


if __name__ == "__main__":
    main()
