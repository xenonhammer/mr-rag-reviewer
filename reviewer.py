# -*- coding: utf-8 -*-
"""Логика ревью MR: RAG + LM + публикация комментариев в GitLab."""

import logging
import os
import re
from dotenv import load_dotenv
from openai import OpenAI

from gitlab_client import GitLabClient
from rag import RepoRAG, is_code_file, skip_path

load_dotenv()

log = logging.getLogger("mr-reviewer")

GITLAB_URL = os.getenv("GITLAB_URL", "http://gitlab.local")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
PROJECT_ID = os.getenv("GITLAB_PROJECT_ID", "")
LM_BASE_URL = os.getenv("LM_BASE_URL", "http://127.0.0.1:1234/v1")
LM_MODEL = os.getenv("LM_MODEL", "openai/gpt-oss-20b")
LM_MAX_CTX = int(os.getenv("LM_MAX_CTX", "4096"))
CHARS_PER_TOKEN = 3
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "12"))
FILE_SECTION_MARKER = "## Файл: "


def first_new_line_from_diff(diff_text: str) -> int | None:
    for line in diff_text.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if m:
            return int(m.group(1))
    return None


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


def parse_review_by_file(review_text: str) -> tuple[str, list[tuple[str, str]]]:
    general = review_text
    file_blocks: list[tuple[str, str]] = []
    if FILE_SECTION_MARKER not in review_text:
        return general.strip(), file_blocks
    parts = review_text.split(FILE_SECTION_MARKER)
    general = parts[0].strip()
    for block in parts[1:]:
        block = block.strip()
        if not block:
            continue
        first_line = block.split("\n")[0].strip()
        path = first_line.split("\n")[0].strip()
        body_start = block.find("\n")
        body = block[body_start:].strip() if body_start >= 0 else ""
        if path:
            file_blocks.append((path, f"### Ревью по файлу\n\n{body}"))
    return general, file_blocks


def build_prompt(changed_paths_str: str, rag_context: str, title: str, description: str, diff_text: str) -> tuple[str, str]:
    system = """Ты — строгий код-ревьюер. Тебе дают контекст репозитория (RAG), описание merge request и diff. Твоя задача — проверить изменения только по перечисленным критериям и комментировать лишь при реальных нарушениях.

Стиль: обращайся на «ты», будь конкретным и прямолинейным. Все комментарии — на русском, в Markdown. Если по критерию нарушений нет — пиши «Нет замечаний». Не придумывай проблемы там, где их нет.

Критерии (проверяй строго по ним):

Безопасность: инъекции (SQL, команды, шаблоны), небезопасная валидация/санитизация ввода, ошибки в аутентификации или авторизации, подозрительные зависимости, чувствительные данные в логах или ответах, eval/exec с пользовательским вводом.

Производительность: неэффективные алгоритмы или структуры данных, лишние операции в циклах, отсутствие кеширования или пагинации, возможные утечки памяти, блокирующие вызовы, тяжёлые операции без ограничений.

Качество кода: нарушение DRY, KISS, SOLID, антипаттерны, избыточная сложность, некорректная обработка ошибок, дублирование логики.

Читаемость: неочевидные имена, магические числа/строки, слишком длинные функции, запутанная структура.

Формат ответа:
1) Обязательная секция:
## Общая оценка MR
Кратко: суть изменений и соответствие описанию MR (1-3 предложения).

2) Только для файлов с замечаниями:
## Файл: <полный путь к файлу>
### Производительность
- Замечания со ссылкой на строки или «Нет замечаний».
### Безопасность
- Замечания со ссылкой на строки или «Нет замечаний».
### Качество кода
- Замечания со ссылкой на строки или «Нет замечаний».
### Читаемость
- Замечания со ссылкой на строки или «Нет замечаний».
"""

    user_content = f"""## Изменённые файлы (анализируй только их)
{changed_paths_str}

## Контекст репозитория (релевантные фрагменты)
{rag_context[:15000]}

## Merge Request: {title}

### Описание
{description or '(нет описания)'}

### Diff
{diff_text[:20000]}
"""
    return system, user_content


def run_review(mr_iid: int, project_id: str | None = None, gitlab_url: str | None = None) -> dict:
    effective_project_id = project_id or PROJECT_ID
    effective_gitlab_url = (gitlab_url or GITLAB_URL).rstrip("/")
    if not GITLAB_TOKEN:
        raise RuntimeError("Укажите GITLAB_TOKEN")
    if not effective_project_id:
        raise RuntimeError("Укажите GITLAB_PROJECT_ID")

    client = GitLabClient(effective_gitlab_url, GITLAB_TOKEN)
    mr = client.get_merge_request(effective_project_id, mr_iid)
    changes = client.get_merge_request_changes(effective_project_id, mr_iid)

    title = mr.get("title", "")
    description = mr.get("description") or ""
    diffs = changes.get("changes", [])
    diff_text = ""
    for d in diffs:
        diff_text += f"\n--- {d.get('new_path') or d.get('old_path')} ---\n"
        diff_text += d.get("diff", "")

    # Важно: контекст берём из целевой ветки MR (обычно main).
    rag_ref = mr.get("target_branch") or "main"
    log.info("RAG ref branch: %s", rag_ref)
    try:
        tree = client.get_repository_tree(effective_project_id, rag_ref)
    except Exception as e:
        log.warning("Дерево репозитория недоступно: %s", e)
        tree = []

    file_contents = []
    for node in tree:
        path = node.get("path") or node.get("id")
        if node.get("type") != "blob":
            continue
        if not is_code_file(path) or skip_path(path):
            continue
        try:
            content = client.get_file_raw(effective_project_id, path, rag_ref)
            file_contents.append((path, content))
        except Exception:
            continue

    rag = RepoRAG()
    rag.index_files(file_contents)
    query = f"{title}\n{description}\n{diff_text}"[:8000]
    chunks = rag.retrieve(query, top_k=RAG_TOP_K)
    rag_context = rag.format_context(chunks)
    changed_paths = [d.get("new_path") or d.get("old_path") for d in diffs if d.get("new_path") or d.get("old_path")]
    changed_paths_str = "\n".join(f"- {p}" for p in changed_paths)

    system_prompt, user_prompt = build_prompt(changed_paths_str, rag_context, title, description, diff_text)
    max_completion_tokens = min(2000, max(256, LM_MAX_CTX // 2))
    max_prompt_chars = (LM_MAX_CTX - max_completion_tokens) * CHARS_PER_TOKEN
    max_user_chars = max(500, max_prompt_chars - len(system_prompt))
    if len(user_prompt) > max_user_chars:
        user_prompt = user_prompt[:max_user_chars]
        log.warning("Промпт обрезан до лимита модели")

    openai_client = OpenAI(base_url=LM_BASE_URL, api_key="lm-studio")
    resp = openai_client.chat.completions.create(
        model=LM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_completion_tokens,
        temperature=0.3,
    )
    review = (resp.choices[0].message.content or "").strip() or "*Пустой ответ модели.*"
    general_text, file_comments = parse_review_by_file(review)

    diff_refs = changes.get("diff_refs") or mr.get("diff_refs") or {}
    base_sha = diff_refs.get("base_sha")
    start_sha = diff_refs.get("start_sha")
    head_sha = diff_refs.get("head_sha")
    can_post_per_file = bool(base_sha and start_sha and head_sha)

    file_first_new_line: dict[str, int] = {}
    for d in diffs:
        path = d.get("new_path") or d.get("old_path")
        if not path:
            continue
        diff_body = d.get("diff") or ""
        line_no = first_changed_new_line_from_diff(diff_body)
        if line_no is None:
            line_no = first_new_line_from_diff(diff_body)
        file_first_new_line[path] = line_no if line_no is not None else 1

    if general_text:
        client.create_mr_discussion(effective_project_id, mr_iid, general_text)
    if not can_post_per_file and file_comments:
        files_block = "\n\n".join(f"## Файл: {path}\n{body}" for path, body in file_comments)
        client.create_mr_discussion(effective_project_id, mr_iid, files_block)
    elif can_post_per_file:
        changed_paths_set = {p for d in diffs for p in (d.get("new_path"), d.get("old_path")) if p}
        for path, body in file_comments:
            path_to_use = path.strip()
            if path_to_use not in changed_paths_set:
                for p in changed_paths_set:
                    if p and (path_to_use in p or p.endswith(path_to_use)):
                        path_to_use = p
                        break
            if path_to_use not in changed_paths_set:
                client.create_mr_discussion(effective_project_id, mr_iid, f"**Файл:** `{path_to_use}`\n\n{body}")
                continue
            new_line = file_first_new_line.get(path_to_use, 1)
            old_path_for_position = path_to_use
            for d in diffs:
                if (d.get("new_path") or d.get("old_path")) == path_to_use:
                    old_path_for_position = d.get("old_path") or path_to_use
                    break
            try:
                client.create_mr_discussion_with_position(
                    effective_project_id,
                    mr_iid,
                    body,
                    base_sha=base_sha,
                    start_sha=start_sha,
                    head_sha=head_sha,
                    new_path=path_to_use,
                    new_line=new_line,
                    old_path=old_path_for_position,
                    old_line=None,
                    line_code=None,
                )
            except Exception:
                created = client.create_mr_draft_note(
                    effective_project_id,
                    mr_iid,
                    body,
                    base_sha=base_sha,
                    start_sha=start_sha,
                    head_sha=head_sha,
                    new_path=path_to_use,
                    new_line=new_line,
                    old_path=old_path_for_position,
                )
                if not created:
                    client.create_mr_discussion(effective_project_id, mr_iid, f"**Файл:** `{path_to_use}`\n\n{body}")

    return {
        "mr_iid": mr_iid,
        "project_id": str(effective_project_id),
        "rag_ref": rag_ref,
        "changed_files": len(diffs),
        "retrieved_chunks": len(chunks),
        "inline_comments": len(file_comments),
    }
