"""Compact GitHub release notes for Home Assistant MQTT Update entities.

Home Assistant exposes release_summary in the update dialog (max. 255 chars).
The complete changelog remains available through release_url.
"""
import re


def summarize_release(markdown, limit=255):
    if not isinstance(markdown, str) or not markdown.strip() or limit < 16:
        return ""

    category = ""
    entries = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            # GitHub releases contain the entire repository changelog. Only
            # summarize the current release, not previous versions or commits.
            if heading.startswith(("previous ", "changes since ", "source")):
                break
        if line.startswith("### "):
            category = line[4:].strip().rstrip(":")
            continue
        if not line.startswith(("- ", "* ")):
            continue
        message = line[2:].strip()
        message = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", message)
        message = re.sub(r"[\x60*_~]", "", message)
        message = re.sub(r"\s+", " ", message).rstrip(".").strip()
        if not message:
            continue
        label = (category + ": ") if category else ""
        entries.append((category, label + message))

    if not entries:
        return ""

    # Prioritize one item per category, so 'Added' does not disappear behind
    # a long list of fixes. Then fill remaining space in source order.
    chosen = []
    categories = set()
    for item in entries:
        if item[0] not in categories:
            chosen.append(item)
            categories.add(item[0])
    for item in entries:
        if item not in chosen:
            chosen.append(item)

    parts = []
    for _, text in chosen:
        item = text[:119].rstrip() + ("…" if len(text) > 119 else "")
        extra = len(item) + (1 if parts else 0)
        if sum(map(len, parts)) + (len(parts) if parts else 0) + extra > limit:
            continue
        parts.append(item)
        if len(parts) >= 3:
            break

    # A release with a single very long bullet still gets a useful summary.
    if not parts:
        text = chosen[0][1]
        return text[:limit-1].rstrip() + "…" if len(text) > limit else text
    return "\n".join(parts)[:limit]
