# -*- coding: utf-8 -*-
"""Отладка: печатает обсуждения MR."""

import os
import sys

from dotenv import load_dotenv

from gitlab_client import GitLabClient

load_dotenv()

GITLAB_URL = os.getenv("GITLAB_URL", "http://gitlab.local").rstrip("/")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
PROJECT_ID = os.getenv("GITLAB_PROJECT_ID", "")


def main():
    if len(sys.argv) < 2 or "--mr" not in sys.argv:
        print("Использование: python tools/debug/list_mr_discussions.py --mr <IID>")
        sys.exit(1)
    mr_iid = int(sys.argv[sys.argv.index("--mr") + 1])

    if not GITLAB_TOKEN or not PROJECT_ID:
        print("Укажите GITLAB_TOKEN и GITLAB_PROJECT_ID")
        sys.exit(1)

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    discussions = client.get_merge_request_discussions(PROJECT_ID, mr_iid)
    drafts = client.get_merge_request_draft_notes(PROJECT_ID, mr_iid)
    print(f"MR !{mr_iid}: {len(discussions)} discussions, {len(drafts)} draft notes")


if __name__ == "__main__":
    main()
