<p align="center">
  <img src="./assets/images/HEADLYN-BLUE-LOGO.png" alt="Headlyn Logo" width="280" />
</p>

# Headlyn

Headlyn is a news intelligence project that turns fragmented article streams into a structured, story-first feed. The product goal is to group related articles about the same event into one evolving story while preserving source attribution.

> [!WARNING]
> This project is under active development. The current repository contains a static India news dataset and the scripts used to create it.

## Current Status

The repository currently includes a static dataset for India news sources:

- RSS snapshots captured on `2026-05-28` under `assets/rss-feeds/raw/2026-05-28/`.
- Source-specific collection and extraction scripts under `scripts/`.
- A helper runner in `main.py` for running the source scripts together.
- Normalized article datasets under `assets/datasets/articles/`.
- Rendered HTML captures under `assets/datasets/raw-html/` where article pages were captured.

The latest checked-in article dataset contains `120` JSONL records, with `20` articles per supported source.

## Supported Sources

| Source ID | Publisher | RSS items in snapshot | Article records |
| --- | --- | ---: | ---: |
| `firstpost` | Firstpost | 200 | 20 |
| `hindustan-times` | Hindustan Times | 100 | 20 |
| `ndtv` | NDTV | 20 | 20 |
| `news18` | News18 | 200 | 20 |
| `pib` | Press Information Bureau | 20 | 20 |
| `the-hindu` | The Hindu | 60 | 20 |

## Project Layout

```text
.
|-- main.py
|-- scripts/
|   |-- scrape_article_utils.py
|   |-- scrape_firstpost_articles.py
|   |-- scrape_hindustan_times_articles.py
|   |-- scrape_ndtv_articles.py
|   |-- scrape_news18_articles.py
|   |-- scrape_pib_articles.py
|   `-- scrape_the_hindu_articles.py
|-- assets/
|   |-- datasets/
|   |   |-- articles/
|   |   `-- raw-html/
|   |-- images/
|   |-- plans/
|   `-- rss-feeds/
`-- README.md
```

## Dataset Format

Each article output file is newline-delimited JSON. Current article records use this shape:

```json
{
  "source": "ndtv",
  "url": "https://example.com/article",
  "title": "Article headline",
  "description": "Short summary from metadata or RSS",
  "published_at": "2026-05-28T07:18:04+00:00",
  "tags": ["India"],
  "paragraphs": ["Article paragraph text"],
  "rss_published_at": "2026-05-28T07:18:04+00:00",
  "fetched_at": "2026-05-28T12:16:22.039971+00:00"
}
```

## Setup

This project does not yet have a pinned dependency file. Create a virtual environment and install the runtime dependencies directly:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install beautifulsoup4 lxml playwright
python -m playwright install chromium
```

## Recreating The Dataset

Run all supported source scripts together:

```bash
python main.py
```

Run one source script directly:

```bash
python scripts/scrape_ndtv_articles.py
```

The current scripts read RSS snapshots from `assets/rss-feeds/raw/2026-05-28/` and write normalized article records to `assets/datasets/articles/`. Browser profile state is written under `.browser-profiles/`, which is ignored by git.

## Target Product Features

- **One story, many sources**: group related articles into a single story so users do not see the same event repeated across publishers.
- **Cleaner news feed**: focus the feed on distinct stories instead of scattered article duplicates.
- **Evolving story updates**: update stories as new information becomes available.
- **Personalized ranking**: learn from user behavior to show more relevant stories first.
- **Better discovery**: keep the feed fresh and diverse beyond a user's usual interests.

## Roadmap

- Add pinned project dependencies and environment setup files.
- Move source configuration out of individual dataset scripts.
- Add validation, deduplication, and quality checks for extracted article text.
- Persist articles into an application database.
- Build story clustering and ranking on top of the static article dataset.
