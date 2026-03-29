from __future__ import annotations

import html
import re


HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str, *, remove_comments: bool = False) -> str:
    text = html.unescape(value)
    if remove_comments:
        text = HTML_COMMENT_RE.sub("", text)
    text = HTML_TAG_RE.sub("", text)
    return " ".join(text.split()).strip()


def find_card_bounds(
    html_text: str,
    heading: str,
    *,
    end_at_next_card: bool,
) -> tuple[int, int]:
    heading_index = html_text.find(heading)
    if heading_index == -1:
        raise ValueError(f"Could not locate heading in docs.html: {heading}")

    start_index = html_text.rfind('<section class="card ref-card">', 0, heading_index)
    if start_index == -1:
        raise ValueError(f"Could not locate start of card for heading: {heading}")

    if not end_at_next_card:
        return start_index, len(html_text)

    next_card_index = html_text.find('\n  <section class="card ref-card">', heading_index)
    end_index = len(html_text) if next_card_index == -1 else next_card_index
    return start_index, end_index


def extract_card_body(
    html_text: str,
    heading: str,
    *,
    end_at_next_card: bool,
) -> str:
    try:
        start_index, end_index = find_card_bounds(html_text, heading, end_at_next_card=end_at_next_card)
    except ValueError:
        return ""
    return html_text[start_index:end_index]
