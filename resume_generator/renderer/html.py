"""
renderer/html.py
Renders a polished, print-ready HTML resume.
Self-contained: all CSS is inlined. No external dependencies.
"""

from html import escape as esc


def render_html(data: dict) -> str:

    def ari_section(entries, heading):
        if not entries:
            return ""
        html = f'<section class="section"><h2 class="section-heading">{esc(heading)}</h2>'
        for e in entries:
            html += f'<div class="entry"><h3 class="entry-title">{esc(e["title"])}</h3><ul class="ari-list">'
            if e["action"]:
                html += f'<li><span class="badge badge-a">Action</span><span>{esc(e["action"])}</span></li>'
            if e["result"]:
                html += f'<li><span class="badge badge-r">Result</span><span>{esc(e["result"])}</span></li>'
            if e["impact"]:
                html += f'<li><span class="badge badge-i">Impact</span><span>{esc(e["impact"])}</span></li>'
            html += "</ul></div>"
        html += "</section>"
        return html

    contact_items = []
    if data["email"]:
        contact_items.append(f'<a href="mailto:{esc(data["email"])}">{esc(data["email"])}</a>')
    if data["phone"]:
        contact_items.append(esc(data["phone"]))
    if data["location"]:
        contact_items.append(esc(data["location"]))
    for lnk in data["links"]:
        contact_items.append(f'<a href="{esc(lnk["url"])}" target="_blank">{esc(lnk["title"])}</a>')

    contact_html = " &nbsp;·&nbsp; ".join(contact_items)

    hobbies_html = ""
    if data["hobbies"]:
        items = " &nbsp;·&nbsp; ".join(esc(h) for h in data["hobbies"])
        hobbies_html = f'<section class="section"><h2 class="section-heading">Hobbies &amp; Interests</h2><p class="hobbies">{items}</p></section>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(data['name'])} — Resume</title>
  <style>
    /* ── Reset ── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    /* ── Page ── */
    body {{
      font-family: Georgia, 'Times New Roman', serif;
      background: #f5f4f0;
      color: #1a1a1a;
      font-size: 15px;
      line-height: 1.65;
    }}
    .page {{
      max-width: 780px;
      margin: 2.5rem auto;
      background: #ffffff;
      padding: 3rem 3.5rem;
      border-radius: 4px;
    }}

    /* ── Header ── */
    header {{
      border-bottom: 2px solid #1a1a1a;
      padding-bottom: 1.25rem;
      margin-bottom: 1.75rem;
    }}
    h1 {{
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.5px;
      line-height: 1.1;
    }}
    .role {{
      font-size: 14px;
      color: #555;
      font-style: italic;
      margin: 0.25rem 0 0.75rem;
    }}
    .purpose {{
      font-size: 15px;
      color: #333;
      max-width: 600px;
      margin-bottom: 0.85rem;
    }}
    .contact {{
      font-size: 13px;
      color: #555;
    }}
    .contact a {{
      color: #185FA5;
      text-decoration: none;
    }}
    .contact a:hover {{ text-decoration: underline; }}

    /* ── Sections ── */
    .section {{ margin: 1.75rem 0; }}
    .section-heading {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #888;
      border-bottom: 0.5px solid #ddd;
      padding-bottom: 5px;
      margin-bottom: 1rem;
    }}

    /* ── Entries ── */
    .entry {{ margin-bottom: 1.1rem; }}
    .entry-title {{
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 0.3rem;
    }}
    .ari-list {{ list-style: none; }}
    .ari-list li {{
      display: flex;
      align-items: baseline;
      gap: 9px;
      font-size: 14px;
      color: #333;
      padding: 2px 0;
    }}

    /* ── ARI Badges ── */
    .badge {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 9.5px;
      font-weight: 700;
      letter-spacing: 0.07em;
      text-transform: uppercase;
      padding: 2px 7px;
      border-radius: 3px;
      flex-shrink: 0;
      margin-top: 2px;
    }}
    .badge-a {{ background: #dbeafe; color: #1e3a8a; }}
    .badge-r {{ background: #dcfce7; color: #14532d; }}
    .badge-i {{ background: #ede9fe; color: #3b0764; }}

    /* ── Hobbies ── */
    .hobbies {{ font-size: 14px; color: #555; }}

    /* ── Print ── */
    @media print {{
      body {{ background: #fff; font-size: 13px; }}
      .page {{ margin: 0; padding: 1.5rem 2rem; border-radius: 0; }}
      .badge-a {{ background: #dbeafe !important; color: #1e3a8a !important; -webkit-print-color-adjust: exact; }}
      .badge-r {{ background: #dcfce7 !important; color: #14532d !important; -webkit-print-color-adjust: exact; }}
      .badge-i {{ background: #ede9fe !important; color: #3b0764 !important; -webkit-print-color-adjust: exact; }}
    }}
  </style>
</head>
<body>
<div class="page">

  <header>
    <h1>{esc(data['name'])}</h1>
    {f'<p class="role">{esc(data["title"])}</p>' if data["title"] else ""}
    {f'<p class="purpose">{esc(data["purpose"])}</p>' if data["purpose"] else ""}
    {f'<div class="contact">{contact_html}</div>' if contact_html else ""}
  </header>

  {ari_section(data["experience"],   "Experience")}
  {ari_section(data["volunteer"],    "Volunteer Work")}
  {ari_section(data["certificates"], "Certificates")}
  {ari_section(data["awards"],       "Awards")}
  {hobbies_html}

</div>
</body>
</html>"""

