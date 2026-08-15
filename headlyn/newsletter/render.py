from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import SECTION_ORDER


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOGO_PATH = ROOT_DIR / "assets" / "images" / "HEADLYN-BLUE-LOGO.png"


def render_html(edition: dict[str, object], *, logo_src: str | None = None) -> str:
    date = html.escape(str(edition.get("edition_date", "")))
    display_date = html.escape(format_edition_date(str(edition.get("edition_date", ""))))
    stories = edition.get("stories", [])
    sections: list[str] = []
    if isinstance(stories, list):
        for section in SECTION_ORDER:
            section_stories = [
                story for story in stories
                if isinstance(story, dict) and story.get("section") == section
            ]
            if not section_stories:
                continue
            cards = "\n".join(render_html_story(story) for story in section_stories)
            sections.append(render_html_section(section, len(section_stories), cards))
    body = "\n".join(sections) or (
        '<tr><td style="padding:28px 24px;color:#536174">'
        "No stories were selected for this edition."
        "</td></tr>"
    )
    unsubscribe = html.escape(
        str(edition.get("unsubscribe_instructions", "Reply to this email to unsubscribe."))
    )
    logo = logo_src if logo_src is not None else default_logo_data_uri()
    logo_markup = (
        f'<img src="{html.escape(logo, quote=True)}" width="44" height="44" '
        'alt="Headlyn" style="display:block;width:44px;height:44px;border:0;border-radius:12px">'
        if logo
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Headlyn - The Newsletter — {date}</title>
  <style>
    @media only screen and (max-width: 600px) {{
      .shell {{ width:100% !important; }}
      .gutter {{ padding-left:16px !important; padding-right:16px !important; }}
      .hero-title {{ font-size:28px !important; line-height:1.1 !important; }}
      .story-card {{ padding:16px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;color:#172033;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;-webkit-font-smoothing:antialiased">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">A concise, source-linked briefing from Headlyn.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f3f6fb">
    <tr><td align="center" class="gutter" style="padding:18px 10px 28px">
      <table role="presentation" class="shell" width="680" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:680px">
        <tr><td style="padding:0 4px 12px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr>
              <td valign="middle" style="width:56px">{logo_markup}</td>
              <td valign="middle" style="padding-left:10px">
                <div style="font-family:Georgia,'Times New Roman',serif;font-size:27px;line-height:31px;font-weight:600;letter-spacing:-.03em;color:#172033">Headlyn</div>
                <div style="font-size:11px;line-height:16px;font-weight:800;letter-spacing:.18em;color:#1542d8;text-transform:uppercase">The Newsletter</div>
              </td>
              <td align="right" valign="middle" style="font-size:12px;color:#68758a">{display_date}</td>
            </tr>
          </table>
        </td></tr>
        <tr><td class="gutter" style="padding:22px 30px 24px;background:#1542d8;border-radius:20px 20px 0 0">
          <div style="font-size:11px;line-height:17px;font-weight:800;letter-spacing:.16em;color:#b9c9ff;text-transform:uppercase">The daily briefing</div>
          <h1 class="hero-title" style="margin:8px 0 6px;font-family:Georgia,'Times New Roman',serif;font-size:32px;line-height:1.08;font-weight:500;letter-spacing:-.02em;color:#ffffff">The stories worth knowing.</h1>
          <p style="margin:0;max-width:520px;font-size:14px;line-height:21px;color:#e2e9ff">A concise, source-linked briefing.</p>
        </td></tr>
        <tr><td class="gutter" style="padding:16px 30px 4px;background:#ffffff">
          <p style="margin:0;font-size:14px;line-height:21px;color:#536174">Today’s briefing, grouped by topic.</p>
        </td></tr>
        {body}
        <tr><td style="padding:16px 30px 22px;background:#ffffff;border-radius:0 0 20px 20px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr><td style="border-top:1px solid #e7ebf2;padding-top:18px;font-size:12px;line-height:19px;color:#7b8798">{unsubscribe}</td></tr>
            <tr><td style="padding-top:8px;font-size:11px;line-height:17px;color:#a0a9b7">Headlyn · A shared daily briefing · Source links open the original articles</td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def render_html_section(section: str, count: int, cards: str) -> str:
    return f"""<tr><td class="gutter" style="padding:16px 30px 0;background:#ffffff">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr>
      <td><span style="display:inline-block;padding:5px 10px;border-radius:999px;background:#eaf0ff;color:#1542d8;font-size:11px;line-height:15px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">{html.escape(section)}</span></td>
      <td align="right" style="font-size:12px;color:#9aa5b4">{count} {'story' if count == 1 else 'stories'}</td>
    </tr>
  </table>
</td></tr>
<tr><td class="gutter" style="padding:8px 30px 0;background:#ffffff">{cards}</td></tr>"""


def render_html_story(story: dict[str, object]) -> str:
    headline = html.escape(str(story.get("headline", "")))
    summary = html.escape(str(story.get("summary", "")))
    source = html.escape(str(story.get("source_name", "")))
    published = html.escape(format_published_at(str(story.get("published_at", ""))))
    url = html.escape(str(story.get("url", "")), quote=True)
    article_count = int(story.get("article_count", 1) or 1)
    report_label = f"{article_count} reports" if article_count > 1 else "1 report"
    return f"""<table role="presentation" class="story-card" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 10px;background:#ffffff;border:1px solid #e5eaf2;border-radius:12px">
  <tr><td class="story-card" style="padding:16px 18px 15px">
    <h3 style="margin:0 0 7px;font-family:Georgia,'Times New Roman',serif;font-size:19px;line-height:25px;font-weight:600;letter-spacing:-.01em;color:#172033"><a href="{url}" style="color:#172033;text-decoration:none">{headline}</a></h3>
    <p style="margin:0 0 11px;font-size:14px;line-height:21px;color:#536174">{summary}</p>
    <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
      <td style="padding-right:9px;font-size:12px;line-height:18px;font-weight:700;color:#1542d8">{source}</td>
      <td style="padding-right:10px;font-size:12px;line-height:18px;color:#a2adbb">·</td>
      <td style="padding-right:10px;font-size:12px;line-height:18px;color:#7b8798">{published}</td>
      <td style="font-size:12px;line-height:18px;color:#7b8798">{report_label}</td>
    </tr></table>
    <p style="margin:11px 0 0"><a href="{url}" style="display:inline-block;padding:7px 11px;border-radius:7px;background:#1542d8;color:#ffffff;font-size:11px;line-height:15px;font-weight:800;text-decoration:none">Read original&nbsp; →</a></p>
  </td></tr>
</table>"""


def render_text(edition: dict[str, object]) -> str:
    lines = [
        "HEADLYN DAILY BRIEFING",
        format_edition_date(str(edition.get("edition_date", ""))),
        "",
        "A concise, source-linked briefing grouped by topic.",
        "",
    ]
    stories = edition.get("stories", [])
    if isinstance(stories, list):
        for section in SECTION_ORDER:
            section_stories = [
                story for story in stories
                if isinstance(story, dict) and story.get("section") == section
            ]
            if not section_stories:
                continue
            lines.extend([section.upper(), "=" * len(section)])
            for story in section_stories:
                lines.extend(
                    [
                        str(story.get("headline", "")),
                        str(story.get("summary", "")),
                        f"{story.get('source_name', '')} · {format_published_at(str(story.get('published_at', '')))}",
                        str(story.get("url", "")),
                        "",
                    ]
                )
    lines.extend([
        str(edition.get("unsubscribe_instructions", "Reply to this email to unsubscribe.")),
        "",
    ])
    return "\n".join(lines)


def default_logo_data_uri() -> str:
    try:
        encoded = base64.b64encode(DEFAULT_LOGO_PATH.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{encoded}"


def format_edition_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")
    except ValueError:
        return value


def format_published_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %H:%M IST")
    except ValueError:
        return value
