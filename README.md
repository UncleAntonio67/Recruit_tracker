# Recruit Tracker (Local-first)

Internal job aggregation + application/interview tracking.

## Start (SQLite)

This project defaults to a local SQLite DB file at `./recruit_tracker.db`.

Quick start:

```powershell
Set-Location D:\Project\recruit_tracker
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_local.ps1 -HostAddress 127.0.0.1 -Port 8000 -AdminUser admin -AdminPass change-me
```

Open:
- `http://127.0.0.1:8000/login`

## Crawling (Near 180 Days)

This app is designed to be compliant and maintainable.

- Primary: official company career sites / public feeds / public JSON APIs.
- “Near 180 days” is enforced when a source provides publish/update time. If a source doesn’t provide dates, the job is kept but `published_at` may be empty.

### Proxy / Network

If crawling fails with errors like `WinError 10013` (socket access denied), you usually need to use your corporate proxy.

Options:

- Set environment variables before running crawl:
  - `HTTP_PROXY=http://127.0.0.1:7890`
  - `HTTPS_PROXY=http://127.0.0.1:7890`
- Or pass `-Proxy` to `scripts\run_crawl.ps1`.
- Or set per-source `proxy` in the source config JSON.

### Add Crawl Sources

Use the admin UI:
- `/admin/sources` -> New

Or CLI:

```powershell
# Tencent (China)
.\.venv\Scripts\python.exe -m app.crawl add-source --kind tencent --name Tencent --config-json "{'company_name':'腾讯','api_keywords':['架构','项目管理','新能源','电池'],'proxy':'http://127.0.0.1:7890'}"

# Kuaishou (China)
.\.venv\Scripts\python.exe -m app.crawl add-source --kind kuaishou --name Kuaishou --config-json "{'company_name':'快手','page_size':50,'max_pages':60,'proxy':'http://127.0.0.1:7890'}"

# RSS
.\.venv\Scripts\python.exe -m app.crawl add-source --kind rss --name ExampleFeed --config-json "{'feed_url':'https://example.com/jobs.rss','company_name':'Example'}"

# Any source may include a proxy:
# { ..., "proxy": "http://127.0.0.1:7890" }
```

### Run Crawl Manually

```powershell
.\.venv\Scripts\python.exe -m app.crawl run --since-days 180
# or
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_crawl.ps1 -SinceDays 180 -Proxy http://127.0.0.1:7890
```

### Run Crawl Every 2 Days (Windows Task Scheduler)

Example (run as current user):

```powershell
$taskName = "RecruitTrackerCrawl"
$cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File D:\\Project\\recruit_tracker\\scripts\\run_crawl.ps1 -SinceDays 180"

schtasks /Create /F /SC DAILY /MO 2 /TN $taskName /TR $cmd /ST 03:30
schtasks /Run /TN $taskName
```

## Create additional users

Login as admin then open `/admin/users`, or use CLI:

```powershell
.\.venv\Scripts\python.exe -m app.manage create-user --username user2 --password change-me
```

## Cloud Run + Neon (later)

Set env vars:
- `DATABASE_URL` to Neon Postgres connection string
- `ENV=prod`

Run migrations against Neon:

```powershell
$env:DATABASE_URL="postgresql+psycopg://..."
alembic upgrade head
```
