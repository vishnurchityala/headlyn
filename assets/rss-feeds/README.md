# RSS Feed Snapshots

Raw RSS responses are stored as date-stamped snapshots for deterministic feed
replay and ingestion tests.

## Layout

```text
assets/rss-feeds/
  raw/
    <snapshot_date>/
      manifest.json
      <source-id>/
        feed.xml
        headers.txt
```

- `feed.xml` is the exact RSS response body fetched from the publisher.
- `headers.txt` is the HTTP response header dump from the same fetch.
- `manifest.json` records the exact UTC capture time, source URL, relative file paths, byte size, HTTP status, content type, and item count for each feed in the snapshot.

Replay command:

```text
python -m headlyn.ingestion.pipeline \
  --source firstpost \
  --source ndtv \
  --source hindustan-times \
  --mode snapshot \
  --snapshot-date 2026-05-28
```

Snapshot replay uses only the checked-in RSS XML. No article pages are fetched.
