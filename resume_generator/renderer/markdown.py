"""
renderer/markdown.py
Renders the normalized resume dict to a clean Markdown string.
"""


def render_markdown(data: dict) -> str:
    lines = []

    # Header
    lines.append(f"# {data['name']}")
    if data["title"]:
        lines.append(f"*{data['title']}*")
    lines.append("")

    if data["purpose"]:
        lines.append(data["purpose"])
        lines.append("")

    # Contact block
    contact_parts = []
    if data["email"]:    contact_parts.append(f"**Email:** {data['email']}")
    if data["phone"]:    contact_parts.append(f"**Phone:** {data['phone']}")
    if data["location"]: contact_parts.append(f"**Location:** {data['location']}")
    for lnk in data["links"]:
        contact_parts.append(f"**{lnk['title']}:** {lnk['url']}")

    if contact_parts:
        lines.append("---")
        lines.extend(contact_parts)
        lines.append("---")
        lines.append("")

    # ARI sections
    def ari_section(entries, heading):
        if not entries:
            return
        lines.append(f"## {heading}")
        lines.append("")
        for e in entries:
            lines.append(f"### {e['title']}")
            if e["action"]:
                lines.append(f"- **Action:** {e['action']}")
            if e["result"]:
                lines.append(f"- **Result:** {e['result']}")
            if e["impact"]:
                lines.append(f"- **Impact:** {e['impact']}")
            lines.append("")

    ari_section(data["experience"],   "Experience")
    ari_section(data["volunteer"],    "Volunteer Work")
    ari_section(data["certificates"], "Certificates")
    ari_section(data["awards"],       "Awards")

    if data["hobbies"]:
        lines.append("## Hobbies & Interests")
        lines.append("")
        lines.append(" · ".join(data["hobbies"]))
        lines.append("")

    return "\n".join(lines)

