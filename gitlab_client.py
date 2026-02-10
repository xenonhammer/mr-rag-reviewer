# -*- coding: utf-8 -*-
"""Клиент GitLab API: MR, diff, дерево репозитория, файлы, комментарии."""

import base64
import logging
from typing import Any

import gitlab

log = logging.getLogger("gitlab")


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "attributes"):
        return obj.attributes
    if isinstance(obj, dict):
        return obj
    return obj


class GitLabClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._gl = gitlab.Gitlab(self.base_url, private_token=token)
        try:
            self._gl.auth()
        except Exception as e:
            log.warning("gitlab.auth: %s", e)

    def _project(self, project_id: str):
        return self._gl.projects.get(project_id)

    def _mr(self, project_id: str, mr_iid: int):
        return self._project(project_id).mergerequests.get(mr_iid)

    def get_project(self, project_id: str) -> dict:
        return _to_dict(self._project(project_id))

    def get_merge_request(self, project_id: str, mr_iid: int) -> dict:
        return _to_dict(self._mr(project_id, mr_iid))

    def get_merge_request_changes(self, project_id: str, mr_iid: int) -> dict:
        mr = self._mr(project_id, mr_iid)
        out = mr.changes()
        if isinstance(out, dict):
            return out
        return _to_dict(out) if out is not None else {}

    def get_merge_request_discussions(self, project_id: str, mr_iid: int, per_page: int = 100) -> list:
        mr = self._mr(project_id, mr_iid)
        discussions = mr.discussions.list(get_all=True, per_page=per_page)
        return [_to_dict(d) for d in discussions]

    def get_merge_request_draft_notes(self, project_id: str, mr_iid: int) -> list:
        mr = self._mr(project_id, mr_iid)
        notes = mr.draft_notes.list(get_all=True)
        return [_to_dict(n) for n in notes]

    def get_repository_tree(self, project_id: str, ref: str, recursive: bool = True) -> list[dict]:
        project = self._project(project_id)
        try:
            items = project.repository_tree(ref=ref, recursive=recursive, all=True)
        except Exception:
            items = []
        return [_to_dict(x) for x in items] if items else []

    def get_file_raw(self, project_id: str, file_path: str, ref: str) -> str:
        project = self._project(project_id)
        f = project.files.get(file_path=file_path, ref=ref)
        content = base64.b64decode(f.content)
        return content.decode("utf-8", errors="replace")

    def create_mr_discussion(self, project_id: str, mr_iid: int, body: str) -> dict:
        mr = self._mr(project_id, mr_iid)
        discussion = mr.discussions.create({"body": body})
        return _to_dict(discussion)

    def create_mr_discussion_with_position(
        self,
        project_id: str,
        mr_iid: int,
        body: str,
        *,
        base_sha: str,
        start_sha: str,
        head_sha: str,
        new_path: str,
        new_line: int = 1,
        old_path: str | None = None,
        old_line: int | None = None,
        line_code: str | None = None,
    ) -> dict:
        mr = self._mr(project_id, mr_iid)
        position: dict[str, Any] = {
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "position_type": "text",
            "new_path": new_path,
            "new_line": new_line,
        }
        if old_path is not None:
            position["old_path"] = old_path
        if old_line is not None:
            position["old_line"] = old_line
        if line_code:
            position["line_code"] = line_code
            position["line_range"] = {
                "start": {
                    "line_code": line_code,
                    "type": "new",
                    "old_line": old_line,
                    "new_line": new_line,
                },
                "end": {
                    "line_code": line_code,
                    "type": "new",
                    "old_line": old_line,
                    "new_line": new_line,
                },
            }
        discussion = mr.discussions.create({"body": body, "position": position})
        return _to_dict(discussion)

    def create_mr_draft_note(
        self,
        project_id: str,
        mr_iid: int,
        body: str,
        *,
        base_sha: str,
        start_sha: str,
        head_sha: str,
        new_path: str,
        new_line: int,
        old_path: str,
    ) -> dict | None:
        mr = self._mr(project_id, mr_iid)
        position = {
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "position_type": "text",
            "new_path": new_path,
            "old_path": old_path,
            "new_line": new_line,
        }
        try:
            draft = mr.draft_notes.create({"note": body, "position": position})
            return _to_dict(draft)
        except Exception as e:
            log.warning("Draft note create failed: %s", e)
            return None
