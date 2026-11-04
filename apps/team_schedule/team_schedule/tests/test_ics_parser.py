import base64
import importlib.util
import unittest
from unittest.mock import patch

from team_schedule.ics import parser


def calendar(events, metadata="", bom=False):
    value = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic//EN\r\n" + metadata
    value += "".join("BEGIN:VEVENT\r\n" + event + "END:VEVENT\r\n" for event in events)
    return (("\ufeff" if bom else "") + value + "END:VCALENDAR\r\n").encode("utf-8")


def event(uid="CaseSensitive", sequence=0, extra="", summary="Synthetic"):
    return (f"UID:{uid}\r\nSEQUENCE:{sequence}\r\nSUMMARY:{summary}\r\n"
            "DTSTART:20261104T090700Z\r\nDTEND:20261104T094200Z\r\n" + extra)


def syntax_stub(*args, **kwargs):
    return object()


class ICSRuleTests(unittest.TestCase):
    def parse(self, *events, metadata=""):
        return parser._parse_file(calendar(events, metadata), syntax_stub)

    def test_text_folding_escaping_bom_and_equivalent_digest(self):
        first = event(extra="DESCRIPTION:line\\ncomma\\,semi\\;back\\\\slash\r\n")
        folded = first.replace("SUMMARY:Synthetic", "SUMMARY:Syn\r\n thetic")
        a = parser._parse_file(calendar([first], bom=True), syntax_stub)[0]
        b = parser._parse_file(calendar([folded]), syntax_stub)[0]
        self.assertEqual(a["digest"], b["digest"])
        self.assertEqual(a["payload"]["description"], "line\ncomma,semi;back\\slash")
        self.assertEqual(a["payload"]["start_utc"], "2026-11-04T09:07:00Z")
        self.assertEqual(a["payload"]["source_timezone"], "UTC")

    def test_uid_case_is_not_folded(self):
        items = self.parse(event("A"), event("a"))
        self.assertEqual([item["uid"] for item in items], ["A", "a"])
        self.assertNotEqual(items[0]["digest"], items[1]["digest"])

    def test_duplicate_uid_refuses_whole_file_even_bad_event(self):
        with self.assertRaises(parser.ICSError):
            self.parse(event("same"), "UID:same\r\nRRULE:FREQ=DAILY\r\n")

    def test_timestamp_prodid_and_sequence_do_not_break_content_digest(self):
        a = self.parse(event(extra="DTSTAMP:20261104T012345Z\r\n"))[0]
        b = self.parse(event(sequence=5, extra="LAST-MODIFIED:20260101T010101Z\r\n"))[0]
        self.assertEqual(a["digest"], b["digest"])

    def test_tzid_iana_and_language(self):
        source = event().replace("SUMMARY:", "SUMMARY;LANGUAGE=zh-CN:")
        source = source.replace("DTSTART:20261104T090700Z", 'DTSTART;TZID="Asia/Shanghai";VALUE=DATE-TIME:20261104T090700')
        source = source.replace("DTEND:20261104T094200Z", "DTEND;TZID=Asia/Shanghai:20261104T094200")
        item = self.parse(source)[0]
        self.assertEqual(item["payload"]["start_utc"], "2026-11-04T01:07:00Z")
        self.assertEqual(item["payload"]["source_timezone"], "Asia/Shanghai")

    def test_dst_ambiguous_and_nonexistent_rejected(self):
        for value in ("20261101T013000", "20260308T023000"):
            source = event().replace("DTSTART:20261104T090700Z", "DTSTART;TZID=America/New_York:" + value)
            self.assertEqual(self.parse(source)[0]["error"], "INVALID_TIME")

    def test_status_and_transparency(self):
        item = self.parse(event(extra="STATUS:TENTATIVE\r\nTRANSP:TRANSPARENT\r\n"))[0]
        self.assertEqual(item["payload"]["status"], "Active")
        self.assertEqual(item["payload"]["availability"], "Free")

    def test_minimal_cancel_and_required_sequence(self):
        item = self.parse("UID:unknown\r\nSEQUENCE:9\r\n", metadata="METHOD:CANCEL\r\n")[0]
        self.assertEqual(item["payload"], {"status": "Cancelled"})
        self.assertEqual(item["sequence"], 9)
        self.assertIn("error", self.parse("UID:unknown\r\nSTATUS:CANCELLED\r\n")[0])
        self.assertTrue(self.parse("UID:unknown\r\nSEQUENCE:0\r\nSTATUS:CANCELLED\r\n")[0]["cancelled"])

    def test_cancel_provided_time_still_validated(self):
        self.assertEqual(self.parse("UID:x\r\nSEQUENCE:1\r\nSTATUS:CANCELLED\r\nDTSTART:bad\r\n")[0]["error"], "INVALID_TIME")

    def test_activity_requires_real_nonblank_summary(self):
        for source in (event(summary=""), event(summary="  "), event().replace("SUMMARY:Synthetic\r\n", "")):
            self.assertEqual(self.parse(source)[0]["error"], "INVALID_INPUT")

    def test_property_and_component_refusal_matrix(self):
        rejected = [
            "DURATION:PT30M", "RRULE:FREQ=DAILY", "RDATE:20261104T090700Z",
            "EXDATE:20261104T090700Z", "RECURRENCE-ID:20261104T090700Z",
            "ATTACH:https://example.invalid/private", "URL:https://example.invalid/",
            "ATTENDEE:mailto:nobody@example.invalid", "ORGANIZER:mailto:nobody@example.invalid",
            "X-PRIVATE:secret", "BEGIN:VALARM\r\nACTION:DISPLAY\r\nEND:VALARM",
            "SUMMARY;ALTREP=https://example.invalid/:another",
        ]
        for line in rejected:
            with self.subTest(line=line):
                self.assertIn("error", self.parse(event(extra=line + "\r\n"))[0])
        for component in ("VTIMEZONE", "VTODO", "VJOURNAL", "VCALENDAR"):
            raw = calendar([]).replace(b"END:VCALENDAR", f"BEGIN:{component}\r\nEND:{component}\r\nEND:VCALENDAR".encode())
            with self.subTest(component=component), self.assertRaises(parser.ICSError):
                parser._parse_file(raw, syntax_stub)

    def test_parameter_time_and_duration_refusal_matrix(self):
        replacements = [
            "DTSTART;VALUE=DATE:20261104", "DTSTART:20261104T090700",
            "DTSTART:20261104T090700+0800", "DTSTART:20261104T090701Z",
            "DTSTART;TZID=Custom/Zone:20261104T090700", "DTSTART;TZID=UTC:20261104T090700Z",
            "DTSTART;X-UNKNOWN=value:20261104T090700Z", "DTSTART;TZID=UTC;TZID=UTC:20261104T090700",
            "DTSTART:20260230T090700Z",
        ]
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                source = event().replace("DTSTART:20261104T090700Z", replacement)
                self.assertIn("error", self.parse(source)[0])
        for ending in ("20261104T090700Z", "20261104T090600Z", "20261206T094200Z"):
            self.assertEqual(self.parse(event().replace("20261104T094200Z", ending))[0]["error"], "INVALID_TIME")

    def test_bad_event_isolated_and_missing_uid_safe(self):
        items = self.parse(event("good"), event("") + "UNKNOWN:private-canary\r\n", event("last"))
        self.assertEqual([item["index"] for item in items], [0, 1, 2])
        self.assertEqual(set(items[1]), {"index", "error"})
        self.assertEqual(items[2]["uid"], "last")

    def test_html_remains_inert_text_not_executed_or_fetched(self):
        item = self.parse(event(summary="<script>canary</script>", extra='DESCRIPTION:<img src="https://example.invalid/x">\r\n'))[0]
        self.assertEqual(item["payload"]["title"], "<script>canary</script>")
        self.assertIn("https://", item["payload"]["description"])

    def test_file_limits_encoding_structure_base64(self):
        for raw in (b"\xff", b"\x00", b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n", calendar([]) + calendar([]), calendar([]).replace(b"VERSION:2.0", b"VERSION:1.0")):
            with self.subTest(raw=raw[:40]), self.assertRaises(parser.ICSError):
                parser._parse_file(raw, syntax_stub)
        with self.assertRaises(parser.ICSError) as error:
            parser._parse_file(calendar([event(str(index)) for index in range(201)]), syntax_stub)
        self.assertEqual(error.exception.status, 413)
        for value in ("!", "data:text/plain;base64,AAAA", None):
            with self.assertRaises(parser.ICSError):
                parser.decode_file(value)
        self.assertEqual(parser.decode_file(base64.b64encode(b"abc").decode()), b"abc")
        with self.assertRaises(parser.ICSError) as error:
            parser.decode_file(base64.b64encode(b"a" * (parser.MAX_BYTES + 1)).decode())
        self.assertEqual(error.exception.status, 413)

    def test_large_malicious_parameter_and_folding_input_is_bounded(self):
        source = event(extra="DESCRIPTION" + ";X=x" * 20000 + ":canary\r\n")
        self.assertIn("error", self.parse(source)[0])
        folded = event(extra="DESCRIPTION:a\r\n" + " a\r\n" * 20000)
        self.assertEqual(self.parse(folded)[0]["error"], "INVALID_INPUT")

    def test_runtime_never_silently_substitutes_missing_vobject(self):
        with patch.object(parser.importlib, "import_module", side_effect=ImportError):
            with self.assertRaises(parser.ICSError) as error:
                parser.parse_file(calendar([event()]))
        self.assertEqual(error.exception.code, "DEPENDENCY_UNAVAILABLE")

    def test_library_rejection_is_local_and_safe(self):
        def reader(text, **kwargs):
            if "UID:" in text:
                raise ValueError("private parser path and canary")
            return object()
        result = parser._parse_file(calendar([event()]), reader)
        self.assertEqual(result, [{"index": 0, "error": "INVALID_INPUT"}])


@unittest.skipUnless(importlib.util.find_spec("vobject"), "Real vobject is not installed; rule tests use an explicit syntax stub")
class ICSRealVobjectTests(unittest.TestCase):
    def test_real_library_supported_text_and_fold(self):
        raw = calendar([event(extra="DESCRIPTION:one\\ntwo\r\n").replace("Synthetic", "Syn\r\n thetic")])
        item = parser.parse_file(raw)[0]
        self.assertNotIn("error", item)
        self.assertEqual(item["payload"]["description"], "one\ntwo")

    def test_real_library_mixed_good_bad_and_cancel(self):
        result = parser.parse_file(calendar([event("good"), event("bad", extra="RRULE:FREQ=DAILY\r\n"), "UID:cancel\r\nSEQUENCE:2\r\nSTATUS:CANCELLED\r\n"]))
        self.assertNotIn("error", result[0])
        self.assertEqual(result[1]["error"], "UNSUPPORTED_ICS")
        self.assertTrue(result[2]["cancelled"])
