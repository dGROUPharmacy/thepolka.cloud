"""
normalize.py
Converts any raw input dict into the canonical resume schema.
Every renderer reads from this shape — nothing else.
"""


def normalize(data: dict) -> dict:
    """
    Accepts raw form data and returns a clean, predictable schema.

    ARI entries (experience, volunteer, certificates, awards) are lists of:
        { title, action, result, impact }

    Simple list fields (hobbies) are lists of strings.
    """

    def clean_ari(entries):
        """Normalize a list of action/result/impact entries."""
        if not isinstance(entries, list):
            return []
        out = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            entry = {
                "title":  str(e.get("title",  "") or "").strip(),
                "action": str(e.get("action", "") or "").strip(),
                "result": str(e.get("result", "") or "").strip(),
                "impact": str(e.get("impact", "") or "").strip(),
            }
            if entry["title"] or entry["action"]:
                out.append(entry)
        return out

    def clean_list(items):
        """Normalize a simple list of strings."""
        if not isinstance(items, list):
            return []
        return [str(i).strip() for i in items if str(i).strip()]

    def clean_links(raw):
        """
        Accept either:
          - a string with one 'Label https://url' per line
          - a list of { title, url } dicts
        Returns list of { title, url } dicts.
        """
        if isinstance(raw, list):
            return [
                {"title": str(l.get("title", "")).strip(),
                 "url":   str(l.get("url",   "")).strip()}
                for l in raw
                if isinstance(l, dict) and l.get("url")
            ]
        if isinstance(raw, str):
            links = []
            for line in raw.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    links.append({"title": parts[0], "url": parts[1]})
                elif len(parts) == 1:
                    links.append({"title": parts[0], "url": parts[0]})
            return links
        return []

    return {
        "name":         str(data.get("name",     "") or "").strip(),
        "title":        str(data.get("title",    "") or "").strip(),
        "purpose":      str(data.get("purpose",  "") or "").strip(),
        "email":        str(data.get("email",    "") or "").strip(),
        "phone":        str(data.get("phone",    "") or "").strip(),
        "location":     str(data.get("location", "") or "").strip(),
        "links":        clean_links(data.get("links", [])),
        "experience":   clean_ari(data.get("experience",   [])),
        "volunteer":    clean_ari(data.get("volunteer",    [])),
        "certificates": clean_ari(data.get("certificates", [])),
        "awards":       clean_ari(data.get("awards",       [])),
        "hobbies":      clean_list(data.get("hobbies",     [])),
    }

