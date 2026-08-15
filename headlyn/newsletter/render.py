from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import SECTION_ORDER


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_LOGO_PATH = ROOT_DIR / "assets" / "images" / "HEADLYN-BLUE-LOGO.png"
BRAND_BLUE = "#173fe6"
INK = "#172033"
MUTED = "#647083"
PAPER = "#fffefa"


def render_html(edition: dict[str, object], *, logo_src: str | None = None) -> str:
    date = html.escape(str(edition.get("edition_date", "")))
    display_date = html.escape(format_edition_date(str(edition.get("edition_date", ""))))
    stories = edition.get("stories", [])
    sections: list[str] = []
    if isinstance(stories, list):
        for section in SECTION_ORDER:
            section_stories = [
                story
                for story in stories
                if isinstance(story, dict) and story.get("section") == section
            ]
            if not section_stories:
                continue
            cards = "\n".join(
                render_html_story(story, featured=index == 0)
                for index, story in enumerate(section_stories)
            )
            sections.append(render_html_section(section, len(section_stories), cards))

    body = "\n".join(sections) or (
        '<tr><td class="content-pad" style="padding:28px 34px;color:#647083">'
        "No stories were selected for this edition."
        "</td></tr>"
    )
    story_count = len(
        [story for story in stories if isinstance(story, dict)]
    ) if isinstance(stories, list) else 0
    publisher_count = len(
        {
            str(story.get("source_id", ""))
            for story in stories
            if isinstance(story, dict) and story.get("source_id")
        }
    ) if isinstance(stories, list) else 0
    edition_meta = (
        f"{story_count} stories&nbsp;&nbsp;·&nbsp;&nbsp;{publisher_count} publishers"
        if story_count
        else "A focused daily edition"
    )
    source_list = render_html_sources(stories if isinstance(stories, list) else [])
    unsubscribe = html.escape(
        str(edition.get("unsubscribe_instructions", "Reply to this email to unsubscribe."))
    )
    logo = logo_src if logo_src is not None else default_logo_data_uri()
    logo_markup = (
        f'<img src="{html.escape(logo, quote=True)}" width="42" height="42" '
        'alt="Headlyn" style="display:block;width:42px;height:42px;border:0;border-radius:11px">'
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
      .outer-pad {{ padding:10px 0 18px !important; }}
      .masthead-pad {{ padding:0 18px 14px !important; }}
      .content-pad {{ padding-left:18px !important; padding-right:18px !important; }}
      .hero-pad {{ padding:20px 18px 18px !important; }}
      .hero-title {{ font-size:30px !important; line-height:1.06 !important; }}
      .story-headline {{ font-size:21px !important; line-height:27px !important; }}
      .story-body {{ font-size:14px !important; line-height:22px !important; }}
      .footer-pad {{ padding-left:18px !important; padding-right:18px !important; }}
      .date-cell {{ display:block !important; padding-top:10px !important; text-align:left !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f2ed;color:{INK};font-family:'Avenir Next','Helvetica Neue',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;-webkit-font-smoothing:antialiased">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0">A concise, source-linked briefing from Headlyn.</div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f2ed">
    <tr><td align="center" class="outer-pad" style="padding:18px 10px 28px">
      <table role="presentation" class="shell" width="660" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:660px;background:#ffffff;border:1px solid #e8e6e1">
        <tr><td class="masthead-pad" style="padding:0 26px 15px;border-bottom:1px solid #d9dce3;background:#ffffff">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr>
              <td valign="middle" style="width:54px;padding-top:15px">{logo_markup}</td>
              <td valign="middle" style="padding:15px 10px 0">
                <div style="font-family:'Avenir Next','Helvetica Neue',Arial,sans-serif;font-size:26px;line-height:28px;font-weight:600;letter-spacing:-.065em;color:{INK}">Headlyn</div>
                <div style="font-size:10px;line-height:14px;font-weight:700;letter-spacing:.18em;color:{BRAND_BLUE};text-transform:uppercase">The Newsletter</div>
              </td>
              <td class="date-cell" align="right" valign="middle" style="padding-top:15px;font-size:12px;line-height:18px;color:{MUTED}">{display_date}</td>
            </tr>
          </table>
        </td></tr>
        <tr><td class="hero-pad" style="padding:24px 30px 22px;background:#f7f9ff;border-left:4px solid {BRAND_BLUE};border-bottom:1px solid #dce4fb">
          <table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>
            <td style="width:28px;padding-right:9px"><div style="height:2px;background:{BRAND_BLUE};font-size:0;line-height:0">&nbsp;</div></td>
            <td style="font-size:10px;line-height:15px;font-weight:700;letter-spacing:.16em;color:{BRAND_BLUE};text-transform:uppercase">THE DAILY BRIEFING</td>
          </tr></table>
          <h1 class="hero-title" style="margin:10px 0 7px;font-family:'Iowan Old Style','Palatino Linotype','Book Antiqua',Georgia,'Times New Roman',serif;font-size:38px;line-height:1.05;font-weight:500;letter-spacing:-.04em;color:{INK}">The stories worth knowing.</h1>
          <p style="margin:0;max-width:500px;font-size:14px;line-height:21px;color:#536174">A concise, source-linked briefing for this morning.</p>
          <p style="margin:12px 0 0;padding-top:8px;border-top:1px solid #dce4fb;font-size:9px;line-height:14px;font-weight:700;letter-spacing:.12em;color:#7f8ba0;text-transform:uppercase">{edition_meta}</p>
        </td></tr>
        <tr><td class="content-pad" style="padding:17px 34px 0;background:{PAPER}">
          <p style="margin:0;font-size:14px;line-height:22px;color:{MUTED}">Today’s briefing, grouped by topic.</p>
        </td></tr>
        {body}
        <tr><td class="footer-pad" style="padding:24px 34px 23px;background:{PAPER}">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr><td style="border-top:1px solid #d9dce3;padding-top:17px;font-family:'Iowan Old Style','Palatino Linotype','Book Antiqua',Georgia,'Times New Roman',serif;font-size:16px;line-height:22px;color:{INK}">Headlyn - The Newsletter</td></tr>
            <tr><td style="padding-top:4px;font-size:12px;line-height:19px;color:{MUTED}">A shared daily briefing.</td></tr>
            <tr><td style="padding-top:12px;font-size:12px;line-height:19px;color:{MUTED}">Created by Vishnu Chityala while building a targeted news platform.</td></tr>
            <tr><td style="padding-top:3px;font-size:12px;line-height:19px;color:{MUTED}"><a href="mailto:vishnurchityala@gmail.com" style="color:{BRAND_BLUE};text-decoration:none">vishnurchityala@gmail.com</a><span style="padding:0 6px;color:#a4acb8">•</span><a href="tel:+919537234000" style="color:{BRAND_BLUE};text-decoration:none">+91-9537234000</a></td></tr>
            {source_list}
            <tr><td style="padding-top:13px;font-size:12px;line-height:19px;color:{MUTED}">{unsubscribe}</td></tr>
            <tr><td style="padding-top:5px;font-size:11px;line-height:17px;color:#8b95a4">Source links open the original articles.</td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def render_html_sources(stories: list[object]) -> str:
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for story in stories:
        if not isinstance(story, dict):
            continue
        label = str(story.get("source_name") or story.get("source_id") or "").strip()
        url = str(story.get("url", "")).strip()
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        sources.append((label, url))
    if not sources:
        return ""
    items: list[str] = []
    for label, url in sources:
        safe_label = html.escape(label)
        if url:
            safe_url = html.escape(url, quote=True)
            content = f'<a href="{safe_url}" style="color:{BRAND_BLUE};text-decoration:none">{safe_label}</a>'
        else:
            content = safe_label
        items.append(
            f'<li style="padding:2px 0;font-size:12px;line-height:19px;color:{MUTED}">{content}</li>'
        )
    return f"""<tr><td style="padding-top:16px;font-size:12px;line-height:19px;font-weight:700;color:{INK}">Sources in this edition</td></tr>
            <tr><td style="padding-top:2px"><ul style="margin:0;padding:0 0 0 18px">{"".join(items)}</ul></td></tr>"""


def render_html_section(section: str, count: int, cards: str) -> str:
    label = html.escape(section.upper())
    count_label = f"{count} STORY" if count == 1 else f"{count} STORIES"
    return f"""<tr><td class="content-pad" style="padding:26px 34px 0;background:{PAPER}">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-top:2px solid {INK}">
    <tr>
      <td style="padding-top:9px;font-size:11px;line-height:16px;font-weight:800;letter-spacing:.14em;color:{BRAND_BLUE}">{label}</td>
      <td align="right" style="padding-top:9px;font-size:10px;line-height:16px;font-weight:700;letter-spacing:.08em;color:#8b95a4">{count_label}</td>
    </tr>
  </table>
</td></tr>
<tr><td class="content-pad" style="padding:10px 34px 0;background:{PAPER}">{cards}</td></tr>"""


def render_html_story(story: dict[str, object], *, featured: bool = False) -> str:
    headline = html.escape(str(story.get("headline", "")))
    summary = html.escape(str(story.get("summary", "")))
    source = html.escape(str(story.get("source_name", "")))
    published = html.escape(format_published_at(str(story.get("published_at", ""))))
    url = html.escape(str(story.get("url", "")), quote=True)
    article_count = int(story.get("article_count", 1) or 1)
    report_label = f"{article_count} reports" if article_count > 1 else "1 report"
    headline_class = "story-headline" if featured else ""
    headline_size = "25px" if featured else "20px"
    headline_line = "31px" if featured else "27px"
    story_spacing = (
        "padding:0 0 20px"
        if featured
        else "padding:17px 0 19px;border-top:1px solid #e1e4e9"
    )
    return f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="{story_spacing}">
  <tr><td>
    <h3 class="{headline_class}" style="margin:0 0 8px;font-family:'Iowan Old Style','Palatino Linotype','Book Antiqua',Georgia,'Times New Roman',serif;font-size:{headline_size};line-height:{headline_line};font-weight:600;letter-spacing:-.018em;color:{INK}"><a href="{url}" aria-label="Read: {headline}" style="color:{INK};text-decoration:none">{headline}</a></h3>
    <p class="story-body" style="margin:0 0 9px;font-size:15px;line-height:23px;color:#4f5b6d">{summary}</p>
    <p style="margin:0;font-size:12px;line-height:19px;color:{MUTED}"><span style="font-weight:700;color:{BRAND_BLUE}">{source}</span><span style="padding:0 6px;color:#a4acb8">•</span><span>{published}</span><span style="padding-left:6px">•&nbsp;{report_label}</span></p>
    <p style="margin:7px 0 0"><a href="{url}" style="display:inline-block;padding:6px 0;font-size:12px;line-height:18px;font-weight:700;color:{BRAND_BLUE};text-decoration:none">Read original&nbsp; ↗</a></p>
  </td></tr>
</table>"""


def render_text(edition: dict[str, object]) -> str:
    lines = [
        "HEADLYN - THE NEWSLETTER",
        format_edition_date(str(edition.get("edition_date", ""))),
        "",
        "A concise, source-linked briefing grouped by topic.",
        "",
    ]
    stories = edition.get("stories", [])
    if isinstance(stories, list):
        for section in SECTION_ORDER:
            section_stories = [
                story
                for story in stories
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
    lines.extend(
        [
            "Headlyn - The Newsletter · A shared daily briefing.",
            str(edition.get("unsubscribe_instructions", "Reply to this email to unsubscribe.")),
            "Source links open the original articles.",
            "",
        ]
    )
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
