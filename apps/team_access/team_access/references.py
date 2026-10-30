from team_access.permissions import MAX_ROWS, PRIVATE_TYPES, deny, get_record

GRAPH_TYPES = ("Comment", "Communication", "ToDo", "Version", "CRM Notification", "Notification Log")


def references(doc):
    if doc.doctype == "ToDo":
        result = [(doc.get("reference_type"), doc.get("reference_name"))]
    elif doc.doctype == "Version":
        result = [(doc.get("ref_doctype"), doc.get("docname"))]
    elif doc.doctype == "CRM Call Log":
        result = [(doc.get("reference_doctype"), doc.get("reference_docname"))]
    elif doc.doctype in ("CRM Notification", "Notification Log"):
        result = [(doc.get("notification_type_doctype") or doc.get("document_type") or doc.get("reference_doctype"), doc.get("notification_type_doc") or doc.get("document_name") or doc.get("reference_name"))]
    else:
        result = [(doc.get("reference_doctype"), doc.get("reference_name"))]
    if doc.doctype in ("Communication", "CRM Call Log"):
        links = doc.get("timeline_links" if doc.doctype == "Communication" else "links") or []
        if len(links) > MAX_ROWS:
            deny()
        result.extend((link.get("link_doctype"), link.get("link_name")) for link in links)
    if doc.doctype == "CRM Call Log" and doc.get("note"):
        result.append(("FCRM Note", doc.get("note")))
    if doc.doctype == "Notification Log":
        result.append((doc.get("source_doctype"), doc.get("source_name")))
    if doc.doctype == "CRM Notification" and doc.get("comment"):
        result.append(("Comment", doc.get("comment")))
    return [(dt, str(name) if name is not None else None) for dt, name in result if dt or name]


def private_roots(doctype=None, name=None, doc=None):
    roots, visited = set(), set()

    def visit(dt, identifier, path):
        if not dt and not identifier:
            return
        if not dt or not identifier:
            deny()
        key = (dt, str(identifier))
        if key in path or len(path) >= 12:
            deny()
        if key in visited:
            return
        if len(visited) >= MAX_ROWS:
            deny()
        visited.add(key)
        if dt in PRIVATE_TYPES:
            if not get_record(dt, identifier):
                deny()
            roots.add(key)
        elif dt in (*GRAPH_TYPES, "CRM Call Log"):
            record = get_record(dt, identifier)
            if not record:
                deny()
            for target_dt, target_name in references(record):
                visit(target_dt, target_name, (*path, key))

    if doc is not None:
        for target_dt, target_name in references(doc):
            visit(target_dt, target_name, ())
    else:
        visit(doctype, name, ())
    return roots


def history_permitted(doc, user, seen=()):
    from team_access.permissions import can_contribute

    return all(can_contribute(dt, name, user, seen) for dt, name in private_roots(doc=doc))
