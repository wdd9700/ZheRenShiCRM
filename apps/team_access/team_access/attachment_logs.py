from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

import frappe

from team_access.permissions import MAX_ROWS, deny

TYPES = ("Attachment", "Attachment Removed")


class AttachmentLink(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.events = []

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, tuple(sorted(attrs))))
        if tag == "a":
            self.links.append([value for key, value in attrs if key == "href"])

    def handle_endtag(self, tag):
        self.events.append(("end", tag))

    def handle_data(self, data):
        self.events.append(("text", data))

    def handle_comment(self, data):
        self.events.append(("comment", data))

    def handle_decl(self, decl):
        self.events.append(("declaration", decl))

    def handle_pi(self, data):
        self.events.append(("instruction", data))

    def unknown_decl(self, data):
        self.events.append(("unknown", data))


def sources(doc):
    if doc.doctype != "Comment" or doc.get("comment_type") not in TYPES:
        return ()
    if doc.get("comment_type") != "Attachment":
        return None
    parser = AttachmentLink()
    try:
        parser.feed(doc.get("content") or "")
        if len(parser.links) != 1 or len(parser.links[0]) != 1:
            return None
        value = parser.links[0][0]
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            return None
        url = unquote(parsed.path)
        if not url.startswith(("/files/", "/private/files/")):
            return None
    except (TypeError, ValueError):
        return None
    from html import escape
    from urllib.parse import quote

    rows = frappe.get_all("File", filters={"file_url": url}, fields=["name", "file_name", "file_url", "is_private"], limit_page_length=MAX_ROWS + 1)
    if len(rows) > MAX_ROWS:
        deny()
    for row in rows:
        icon = ' <i class="fa fa-lock text-warning"></i>' if row.is_private else ""
        expected = f"<a href='{quote(row.file_url, safe='/:')}' target='_blank'>{escape(row.file_name or row.file_url)}</a>{icon}"
        canonical = AttachmentLink()
        canonical.feed(expected)
        if parser.events == canonical.events:
            return tuple(("File", str(alias.name)) for alias in rows)
    return None


def permitted(doc, user, seen):
    from team_access.permissions import can_reference

    targets = sources(doc)
    return targets is not None and all(can_reference(dt, name, user, seen) for dt, name in targets)
