# Obituary Content API and WordPress Auto Publisher

Production-ready starter system for collecting respectful, USA-focused obituary content, storing structured records in MongoDB Atlas, serving them through FastAPI, and auto-publishing to WordPress.

## Architecture

- `scraper/`: independent collector run by GitHub Actions. It fetches trend keywords, scrapes lightweight HTML pages with `requests` and BeautifulSoup, extracts structured fields, rewrites content respectfully, deduplicates by hash, and writes to MongoDB.
- `api/`: FastAPI app that only reads MongoDB and returns clean JSON responses. No scraping runs inside the API.
- `wordpress-plugin/`: WordPress plugin that fetches `/api/obituaries` and publishes new posts when called by a secure external trigger.
- `.github/workflows/cron.yml`: runs the collector every 15 minutes.
- `.github/workflows/wordpress-publish.yml`: optional external scheduler that triggers the WordPress publisher every 15 minutes.

## MongoDB Schema

Collection: `obituaries`

```json
{
  "_id": "ObjectId",
  "name": "Jane Doe",
  "title": "Jane Doe Obituary - Ohio - 2026",
  "slug": "jane-doe-obituary-ohio-2026",
  "content": "Unique rewritten article...",
  "meta_description": "Read the obituary for Jane Doe...",
  "date_of_death": "2026-05-01",
  "location": "Columbus, OH",
  "source_url": "https://source.example/...",
  "created_at": "2026-05-03T12:00:00Z",
  "hash": "sha256..."
}
```

Indexes are created automatically by the scraper:

- `slug`, unique
- `hash`, unique
- `created_at`, descending
- text index on `name`, `title`, and `content`

## Local Setup

1. Create a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `MONGODB_URI`.

3. Run the collector:

```bash
python scraper/scraper.py
```

4. Start the API:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

5. Test:

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/api/obituaries?page=1&limit=10"
```

## API Endpoints

- `GET /api/obituaries?page=1&limit=10`
- `GET /api/obituaries/{id_or_slug}`
- `GET /api/search?q=keyword&page=1&limit=10`
- `GET /api/trending?limit=10`
- `GET /health`

## MongoDB Atlas Free Tier

1. Create a free MongoDB Atlas account.
2. Create an M0 free cluster.
3. Create a database user with read/write access.
4. Add network access. For free hosting and GitHub Actions, use `0.0.0.0/0` if your provider does not offer static outbound IPs.
5. Copy the connection string and set it as `MONGODB_URI`.
6. Use `obituary_api` as `MONGODB_DB`, or set your preferred name consistently in API hosting and GitHub Actions.

## Deploy FastAPI on Free Hosting

Render, Railway, Fly.io, and similar providers can run this app on free or low-cost tiers when available. The simplest setup is:

1. Push this repository to GitHub.
2. Create a new web service from the repository.
3. Set the build command:

```bash
pip install -r requirements.txt
```

4. Set the start command:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

5. Render reads `.python-version` and deploys with Python 3.11.15. If you prefer to set it in the dashboard instead, add:

```text
PYTHON_VERSION=3.11.15
```

6. Add environment variables:

```text
MONGODB_URI=your Atlas connection string
MONGODB_DB=obituary_api
CORS_ORIGINS=*
```

7. Open `/health` on the deployed URL to confirm MongoDB connectivity.

## GitHub Actions Automation

1. In GitHub, open repository settings.
2. Add these repository secrets:

```text
MONGODB_URI
MONGODB_DB
OPENAI_API_KEY
```

`OPENAI_API_KEY` is optional. Without it, the scraper uses a conservative local rewrite that avoids invented facts.

3. The workflow in `.github/workflows/cron.yml` runs every 15 minutes and can also be triggered manually from the Actions tab.

## WordPress Plugin Installation

1. Zip the `wordpress-plugin` folder or upload `obituary-auto-poster.php` into `wp-content/plugins/obituary-auto-poster/`.
2. Activate **Obituary Auto Poster** in WordPress Admin.
3. Open **Settings > Obituary Auto Poster**.
4. Enter your API URL:

```text
https://your-api-host.example.com/api/obituaries
```

5. Save settings.
6. Copy the **External trigger URL** and **Trigger token** from the settings page.

The plugin does not use WordPress cron. This is better for shared hosts such as Namecheap where WP-Cron can be delayed by low traffic.

## External WordPress Publishing Cron

To trigger publishing from GitHub Actions, add these repository secrets:

```text
WORDPRESS_TRIGGER_URL=https://your-wordpress-site.com/wp-json/obituary-auto-poster/v1/run
WORDPRESS_TRIGGER_TOKEN=the token shown in WordPress plugin settings
```

Then run **WordPress Publisher** from GitHub Actions, or wait for its 15-minute schedule.

You can also test the trigger with:

```bash
curl -X POST \
  -H "X-OAP-Token: your-token" \
  "https://your-wordpress-site.com/wp-json/obituary-auto-poster/v1/run"
```

## Content and Compliance Notes

- The scraper uses public web pages and lightweight requests. Review source site terms before scaling traffic.
- The rewrite step is instructed not to invent relatives, causes of death, service times, or private details.
- Each post links back to the source URL in metadata and keeps a source id for deduplication.
- Keep `MAX_KEYWORDS_PER_RUN` between 5 and 10 to avoid excessive scraping.

## Production Tips

- Use MongoDB Atlas indexes generated by `scraper/db.py`.
- Keep the API read-only and horizontally scalable.
- Use provider-level caching or a CDN for `/api/obituaries` if traffic grows.
- Restrict `CORS_ORIGINS` to your WordPress domain once deployed.
- Monitor GitHub Actions logs for blocked search pages or source pages.
