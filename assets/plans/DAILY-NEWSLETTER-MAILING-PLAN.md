# Daily Newsletter and Mailing Plan

## Goal

Create the first user-facing Headlyn workflow: a one-shot daily pipeline that
consumes normalized story clusters, generates grounded newsletter copy with the
local Gemma model, renders HTML and plain text, and optionally sends the shared
edition through generic SMTP.

## Flow

```text
RSS ingestion
  → story normalization
  → Gemma headline/summary/section rewrite
  → deterministic balanced selection
  → HTML/plain-text rendering
  → preview or explicit SMTP delivery
```

The first delivery version is for an internal/test recipient list. Website
delivery, personalization, provider-specific APIs, and production subscriber
management are later phases.

## Newsletter behavior

- Consume all stories in `story_normalization/<run_id>/newsletter_stories.json`,
  including singleton stories.
- Give Gemma every contributing RSS title, description, and publisher.
- Require strict JSON containing a headline, 30–70 word factual summary, and
  one section from the controlled section list.
- Use representative RSS content if rewriting fails and record the fallback.
- Target ten selected stories, require at least five to send, cap a
  representative source at three, and prefer four publishers when available.
- Give every available section one selection opportunity before filling the
  remaining slots by freshness, source count, article count, and confidence.
- Show one representative source link in the email; retain all source details
  in upstream debug artifacts.

## Artifacts

```text
artifacts/stages/daily_newsletter/<edition_date>/
  rewrites.jsonl
  selection.json
  newsletter.json
  newsletter.html
  newsletter.txt
  delivery.json
  summary.json
```

Edition state is keyed by date. A sent edition cannot be sent again without
`--force-resend`; `--force-rebuild` explicitly regenerates its content.

## Configuration

Gemma uses the existing Ollama endpoint and model by default. SMTP uses:

- `HEADLYN_SMTP_HOST`
- `HEADLYN_SMTP_PORT`
- `HEADLYN_SMTP_USERNAME`
- `HEADLYN_SMTP_PASSWORD`
- `HEADLYN_SMTP_FROM`
- `HEADLYN_SMTP_REPLY_TO`
- `HEADLYN_RECIPIENTS`
- `HEADLYN_UNSUBSCRIBE_INSTRUCTIONS`

No recipient address is written to an artifact or normal diagnostic log.

## Commands

Generate a preview from an existing story run:

```bash
python -m headlyn.newsletter.pipeline \
  --story-run-id <story-run-id> \
  --edition-date YYYY-MM-DD
```

Run the complete daily flow:

```bash
python -m headlyn.pipeline --edition-date YYYY-MM-DD
```

Send only after configuring SMTP:

```bash
python -m headlyn.pipeline --edition-date YYYY-MM-DD --send
```

External scheduling is intentionally delegated to cron, launchd, or another
job runner.
