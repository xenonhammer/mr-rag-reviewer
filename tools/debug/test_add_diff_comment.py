# -*- coding: utf-8 -*-
"""Отладка: пробует добавить inline-комментарий в diff MR."""

import argparse
import os
import re
import sys

from dotenv import load_dotenv

from gitlab_client import GitLabClient

load_dotenv()

GITLAB_URL = os.getenv("GITLAB_URL", "http://gitlab.local")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
PROJECT_ID = os.getenv("GITLAB_PROJECT_ID", "")


def first_changed_new_line_from_diff(diff_text: str) -> int | None:
    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[i])
        if not m:
            i += 1
            continue
        new_line = int(m.group(1))
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line.startswith("+") and not line.startswith("+++"):
                return new_line
            if line.startswith("+") or line.startswith(" "):
                new_line += 1
            i += 1
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mr", type=int, required=True)
    parser.add_argument("--body", type=str, default="*Тестовый комментарий к строке diff*")
    args = parser.parse_args()

    if not GITLAB_TOKEN or not PROJECT_ID:
        print("Укажите GITLAB_TOKEN и GITLAB_PROJECT_ID", file=sys.stderr)
        sys.exit(1)

    client = GitLabClient(GITLAB_URL, GITLAB_TOKEN)
    changes = client.get_merge_request_changes(PROJECT_ID, args.mr)
    diffs = changes.get("changes", [])
    if not diffs:
        print("Нет изменений в MR", file=sys.stderr)
        sys.exit(1)

    diff_refs = changes.get("diff_refs") or {}
    base_sha = diff_refs.get("base_sha")
    start_sha = diff_refs.get("start_sha")
    head_sha = diff_refs.get("head_sha")
    if not (base_sha and start_sha and head_sha):
        print("diff_refs недоступен", file=sys.stderr)
        sys.exit(1)

    target = diffs[0]
    new_path = target.get("new_path") or target.get("old_path")
    old_path = target.get("old_path") or new_path
    line = first_changed_new_line_from_diff(target.get("diff", "")) or 1

    client.create_mr_discussion_with_position(
        PROJECT_ID,
        args.mr,
        args.body,
        base_sha=base_sha,
        start_sha=start_sha,
        head_sha=head_sha,
        new_path=new_path,
        new_line=line,
        old_path=old_path,
        old_line=None,
        line_code=None,
    )
    print("OK")


if __name__ == "__main__":
    main()
