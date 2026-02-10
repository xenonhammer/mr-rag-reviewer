# mr-rag-reviewer

Отдельный Docker-сервис для ревью Merge Request через RAG + LM Studio.

## Запуск

1. Скопируй `.env.example` в `.env` и заполни переменные.
2. Подними сервис:

```bash
docker compose up -d --build
```

3. Проверка:

```bash
curl http://localhost:8081/health
```

## Вызов из CI

```bash
curl -X POST "$REVIEWER_URL/review" \
  -H "Content-Type: application/json" \
  -H "X-Reviewer-Token: $REVIEWER_API_TOKEN" \
  -d '{"action":"review_mr","project_id":"1","mr_iid":2,"gitlab_url":"http://gitlab.local"}'
```
