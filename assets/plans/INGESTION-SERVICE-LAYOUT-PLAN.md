## Folder layout

```
newsfeed-ingestion/
├── app/
│   ├── config.py
│   ├── models.py
│   ├── db.py
│   ├── sources.py
│   │
│   ├── scraperkit/
│   │   ├── __init__.py
│   │   ├── loaders.py
│   │   ├── parsers.py
│   │   └── exceptions.py
│   │
│   ├── pipeline.py
│   ├── clean.py
│   ├── dedup.py
│   ├── validate.py
│   │
│   ├── scheduler.py
│   └── cli.py
│
├── sources/
│   ├── thehindu.yaml
│   ├── indianexpress.yaml
│   └── ndtv.yaml
│
├── migrations/
│   └── 001_initial.sql
│
├── tests/
│   └── test_pipeline.py
│
├── pyproject.toml
├── .env.example
└── README.md
```

## File-by-file roles and pseudocode

### `app/config.py`
**Role**: Single source of truth for env-based settings. Loaded once at startup.

```python
class Settings(BaseSettings):
    db_url: str
    log_level: str = "INFO"
    user_agent: str = "newsfeed-ingestion/0.1"
    fetch_timeout_s: int = 15
    max_concurrent_per_source: int = 2
    raw_html_dir: Path = Path("./raw_html")

settings = Settings()  # singleton
```

---

### `app/models.py`
**Role**: Pydantic contracts between stages. Every stage takes one model, returns another. No model is mutated in place.

```python
class FeedEntry(BaseModel):
    source: str
    url: str
    title: str | None
    published_at_raw: str | None

class ExtractedArticle(BaseModel):
    source: str
    url: str
    title: str
    body_raw: str
    published_at: datetime | None
    authors: list[str] = []
    language: str = "en"
    fetched_at: datetime
    html_path: str  # path to gzipped raw HTML

class CleanArticle(BaseModel):
    source: str
    url: str
    title: str
    body_clean: str
    body_hash: str
    word_count: int
    published_at: datetime
    metadata: dict = {}
    wire_source: str | None = None  # PTI/ANI/etc

class ValidationResult(BaseModel):
    accepted: bool
    reason: str | None = None
    flags: list[str] = []
```

---

### `app/db.py`
**Role**: Database connection + insert/query helpers. No business logic. Two tables: `raw_articles` and `raw_html_snapshots`.

```python
def get_conn():
    return psycopg.connect(settings.db_url)

def article_url_exists(url: str) -> bool:
    # SELECT 1 FROM raw_articles WHERE url = %s
    ...

def body_hash_exists(body_hash: str) -> bool:
    # SELECT 1 FROM raw_articles WHERE body_hash = %s
    ...

def insert_article(article: CleanArticle, status: str) -> UUID:
    # INSERT INTO raw_articles (...) VALUES (...) RETURNING id
    ...

def insert_html_snapshot(url: str, html: bytes, method: str) -> str:
    # gzip + write to disk, INSERT row, return path
    ...
```

---

### `app/sources.py`
**Role**: Load source configs from YAML files into `SourceConfig` objects. Map source name → parser class.

```python
class SourceConfig(BaseModel):
    name: str
    rss_url: str
    requires_js: bool = False
    poll_interval_minutes: int = 30
    min_request_interval_ms: int = 1000
    parser: str  # parser class name

def load_all_sources() -> list[SourceConfig]:
    # read sources/*.yaml, validate, return list
    ...

def get_parser(name: str) -> BaseParser:
    # registry lookup: "thehindu" -> TheHinduParser()
    ...
```

Example YAML (`sources/thehindu.yaml`):
```yaml
name: thehindu
rss_url: https://www.thehindu.com/news/feeder/default.rss
requires_js: false
poll_interval_minutes: 30
parser: thehindu
```

---

### `app/scraperkit/exceptions.py`
**Role**: Typed exceptions so failure semantics are granular, not "something broke."

```python
class ScraperKitError(Exception): ...
class FetchError(ScraperKitError): ...
class RateLimitError(FetchError): ...
class ExtractionError(ScraperKitError): ...
class SelectorMissingError(ExtractionError): ...
class TimestampParseError(ExtractionError): ...
```

---

### `app/scraperkit/loaders.py`
**Role**: Fetch HTML. Two strategies (http, playwright) behind one interface. Dispatcher picks based on source config.

```python
class BaseLoader(ABC):
    @abstractmethod
    def fetch(self, url: str) -> bytes: ...

class HttpLoader(BaseLoader):
    def fetch(self, url):
        # httpx.get with timeout + user agent
        # raise RateLimitError on 429
        # raise FetchError on non-2xx
        ...

class PlaywrightLoader(BaseLoader):
    def fetch(self, url):
        # launch headless, wait for selector, return html
        ...

def get_loader(requires_js: bool) -> BaseLoader:
    return PlaywrightLoader() if requires_js else HttpLoader()
```

---

### `app/scraperkit/parsers.py`
**Role**: Per-source HTML → `ExtractedArticle`. All source-specific selector logic lives here and nowhere else.

```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, html: bytes, url: str, source: str) -> ExtractedArticle: ...

class TheHinduParser(BaseParser):
    def parse(self, html, url, source):
        soup = BeautifulSoup(html, "lxml")
        title = self._title(soup)
        body = self._body(soup)
        ts = self._timestamp(soup)
        if not body:
            raise SelectorMissingError("body")
        return ExtractedArticle(
            source=source, url=url, title=title,
            body_raw=body, published_at=ts,
            fetched_at=now(), html_path=""  # filled by caller
        )

    def _title(self, soup): ...
    def _body(self, soup): ...
    def _timestamp(self, soup): ...

PARSER_REGISTRY = {"thehindu": TheHinduParser, ...}
```

---

### `app/clean.py`
**Role**: `ExtractedArticle` → `CleanArticle`. Layered, composable cleaning. Generic pipeline + optional per-source hooks.

```python
def clean(article: ExtractedArticle) -> CleanArticle:
    body = article.body_raw
    body = strip_html(body)
    body = remove_boilerplate(body)
    body = normalize_unicode(body)
    body = normalize_whitespace(body)
    body = remove_duplicate_paragraphs(body)
    
    # Per-source hook for known quirks
    if hook := SOURCE_HOOKS.get(article.source):
        body = hook(body)
    
    wire = detect_wire_source(body)
    body_hash = sha256(body.encode()).hexdigest()
    
    return CleanArticle(
        source=article.source, url=article.url,
        title=article.title.strip(), body_clean=body,
        body_hash=body_hash, word_count=len(body.split()),
        published_at=article.published_at, wire_source=wire,
    )

WIRE_PATTERNS = [r"^\(?(PTI|ANI|IANS|Reuters)\)?[:\s\-]", ...]
def detect_wire_source(body: str) -> str | None: ...

SOURCE_HOOKS = {}  # populate as quirks discovered
```

---

### `app/dedup.py`
**Role**: URL dedup and content-hash dedup. Near-dup detection deferred to v2.

```python
def is_url_duplicate(url: str) -> bool:
    return db.article_url_exists(url)

def is_content_duplicate(body_hash: str) -> bool:
    return db.body_hash_exists(body_hash)
```

---

### `app/validate.py`
**Role**: Decide if a cleaned article is fit for downstream use. Hard rejects vs soft flags.

```python
def validate(article: CleanArticle) -> ValidationResult:
    if article.word_count < 20:
        return ValidationResult(accepted=False, reason="too_short")
    if not article.title or len(article.title) < 10:
        return ValidationResult(accepted=False, reason="no_title")
    if is_paywall_stub(article.body_clean):
        return ValidationResult(accepted=False, reason="paywall_stub")
    
    flags = []
    if article.word_count < 80:
        flags.append("short_article")
    if not article.published_at:
        flags.append("missing_timestamp")
    
    return ValidationResult(accepted=True, flags=flags)

def is_paywall_stub(body: str) -> bool: ...
```

---

### `app/pipeline.py`
**Role**: Orchestrates one source end-to-end. The only file that knows the stage order. Everything else is a pure function.

```python
def run_source(source: SourceConfig) -> RunStats:
    stats = RunStats(source=source.name)
    entries = poll_rss(source.rss_url, source.name)
    
    sem = asyncio.Semaphore(settings.max_concurrent_per_source)
    
    for entry in entries:
        if is_url_duplicate(entry.url):
            stats.skipped_url_dup += 1
            continue
        
        try:
            with sem:
                html = get_loader(source.requires_js).fetch(entry.url)
                html_path = db.insert_html_snapshot(entry.url, html, "http")
                
                parser = get_parser(source.parser)
                extracted = parser.parse(html, entry.url, source.name)
                extracted.html_path = html_path
                
                cleaned = clean(extracted)
                
                if is_content_duplicate(cleaned.body_hash):
                    stats.skipped_content_dup += 1
                    continue
                
                result = validate(cleaned)
                if not result.accepted:
                    stats.rejected += 1
                    log_rejection(cleaned.url, result.reason)
                    continue
                
                db.insert_article(cleaned, status="pending")
                stats.accepted += 1
                
                time.sleep(source.min_request_interval_ms / 1000)
        
        except RateLimitError:
            stats.rate_limited += 1
            break  # stop this source, retry next cycle
        except (FetchError, ExtractionError) as e:
            stats.failed += 1
            log_failure(entry.url, type(e).__name__, str(e))
    
    return stats

def poll_rss(rss_url: str, source: str) -> list[FeedEntry]:
    # feedparser.parse, return normalized FeedEntry objects
    ...
```

---

### `app/scheduler.py`
**Role**: Schedule per-source runs with jitter. One job per source.

```python
def setup_scheduler():
    scheduler = BackgroundScheduler()
    for source in load_all_sources():
        jitter = random.randint(0, 300)  # 0-5 min
        scheduler.add_job(
            run_source, "interval",
            minutes=source.poll_interval_minutes,
            args=[source],
            jitter=jitter,
            id=f"source_{source.name}",
            max_instances=1,  # don't overlap runs of same source
        )
    scheduler.start()
```

---

### `app/cli.py`
**Role**: Entry points for running things manually. Critical for debugging.

```python
@app.command()
def run_once(source_name: str):
    """Run a single source one time. For debugging."""
    src = next(s for s in load_all_sources() if s.name == source_name)
    stats = run_source(src)
    print(stats.model_dump_json(indent=2))

@app.command()
def serve():
    """Start the scheduler and run forever."""
    setup_scheduler()
    while True:
        time.sleep(60)

@app.command()
def reprocess(article_id: str):
    """Re-clean an existing article from its stored raw HTML."""
    # Load raw HTML from snapshot, re-run clean+validate, update row
    ...
```

---

### `migrations/001_initial.sql`
**Role**: Schema. Run once before first start.

```sql
CREATE TABLE raw_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    body_clean TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    word_count INT NOT NULL,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    wire_source TEXT,
    metadata JSONB DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    flags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_status ON raw_articles(status);
CREATE INDEX idx_articles_body_hash ON raw_articles(body_hash);
CREATE INDEX idx_articles_published ON raw_articles(published_at DESC);

CREATE TABLE raw_html_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_url TEXT NOT NULL,
    source TEXT NOT NULL,
    html_path TEXT NOT NULL,  -- path to gzipped file on disk
    fetch_method TEXT NOT NULL,
    content_checksum TEXT NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_html_url ON raw_html_snapshots(article_url);
```

---

### `tests/test_pipeline.py`
**Role**: Tests for the pure functions. Don't try to test the full pipeline end-to-end yet — test clean, validate, dedup, parsers in isolation with fixture HTML.

```python
def test_clean_strips_html():
    raw = "<p>Hello <b>world</b></p>"
    extracted = make_extracted(body_raw=raw)
    result = clean(extracted)
    assert "world" in result.body_clean
    assert "<b>" not in result.body_clean

def test_validate_rejects_short():
    article = make_clean(word_count=10)
    assert not validate(article).accepted

def test_thehindu_parser_extracts_body():
    html = (FIXTURES / "thehindu_sample.html").read_bytes()
    parser = TheHinduParser()
    result = parser.parse(html, "http://...", "thehindu")
    assert len(result.body_raw) > 200
```

---

## How the contracts flow

```
RSS              → FeedEntry
Loader           → bytes (raw HTML)
Parser           → ExtractedArticle  
Cleaner          → CleanArticle
Validator        → ValidationResult
DB               → row in raw_articles
```

Each arrow is a pure function. The pipeline is the only place those arrows get chained. That's what makes any individual stage testable in isolation and the whole thing debuggable when something goes wrong.

## What to build in what order

**Day 1-2**: `models.py`, `db.py`, `migrations`, `config.py`. Get the foundation set up so you can insert and query articles.

**Day 3-4**: `scraperkit/` — `loaders.py`, `parsers.py` for one source, `exceptions.py`. Make sure you can fetch and parse one site reliably.

**Day 5-6**: `clean.py`, `dedup.py`, `validate.py`. The post-extraction stages.

**Day 7**: `pipeline.py` wiring everything together, `cli.py` for manual runs. Run end-to-end on one source. Inspect 50 articles by hand.

**Day 8-9**: Add second and third source parsers. This is where you discover what your parser abstraction got wrong and refactor.

**Day 10**: `scheduler.py`, deploy somewhere it can run continuously.