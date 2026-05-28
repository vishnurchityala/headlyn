<p align="center">
  <img src="./assets/images/HEADLYN-BLUE-LOGO.png" alt="Headlyn Logo" width="280" />
</p>

# Headlyn

Headlyn is a news intelligence project that turns fragmented article streams into a structured, story-first feed. The product goal is to group related articles about the same event into one evolving story while preserving source attribution.

## Dataset Snapshot

This repository contains a static India news dataset captured on `2026-05-28`.

- `6` publishers are represented.
- `120` normalized article records are included.
- Each publisher has `20` article records.
- Article files are stored as JSON arrays under `assets/datasets/articles/`.
- Raw RSS snapshots are stored under `assets/rss-feeds/raw/2026-05-28/`.
- Rendered article HTML captures are stored under `assets/datasets/raw-html/`.

## Article Files

| Source ID | Publisher | RSS items in snapshot | Article records | JSON file |
| --- | --- | ---: | ---: | --- |
| `firstpost` | Firstpost | 200 | 20 | `assets/datasets/articles/firstpost-2026-05-28.json` |
| `hindustan-times` | Hindustan Times | 100 | 20 | `assets/datasets/articles/hindustan-times-2026-05-28.json` |
| `ndtv` | NDTV | 20 | 20 | `assets/datasets/articles/ndtv-2026-05-28.json` |
| `news18` | News18 | 200 | 20 | `assets/datasets/articles/news18-2026-05-28.json` |
| `pib` | Press Information Bureau | 20 | 20 | `assets/datasets/articles/pib-2026-05-28.json` |
| `the-hindu` | The Hindu | 60 | 20 | `assets/datasets/articles/the-hindu-2026-05-28.json` |

## Dataset Format

Each article file is a JSON array of article objects. Current article records use this shape:

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

## Target Product Features

- **One story, many sources**: group related articles into a single story so users do not see the same event repeated across publishers.
- **Cleaner news feed**: focus the feed on distinct stories instead of scattered article duplicates.
- **Evolving story updates**: update stories as new information becomes available.
- **Personalized ranking**: learn from user behavior to show more relevant stories first.
- **Better discovery**: keep the feed fresh and diverse beyond a user's usual interests.
