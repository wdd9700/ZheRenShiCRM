import unittest
from datetime import datetime, timezone

from team_schedule.timeutils import ScheduleError, encode_utc, parse_utc, resolve_local, validate_window


class TestModelTime(unittest.TestCase):
    def test_strict_utc(self):
        for value in (None, "2026-11-04", "2026-11-04T17:37:01Z", "2026-11-04T17:37:00+00:00", "2026-02-30T09:00:00Z", "2026-11-04T17:37Z"):
            with self.subTest(value=value), self.assertRaises(ScheduleError):
                parse_utc(value)
        self.assertEqual(encode_utc(parse_utc("2026-11-04T17:37:00Z")), "2026-11-04T17:37:00Z")
        with self.assertRaises(ScheduleError):
            encode_utc(datetime(2026, 11, 4, 17, 37))
        self.assertEqual(encode_utc(datetime(2026, 11, 4, 17, 37, tzinfo=timezone.utc)), "2026-11-04T17:37:00Z")

    def test_minute_windows(self):
        validate_window("2026-11-04T09:07:00Z", "2026-11-04T09:42:00Z")
        validate_window("2026-11-04T23:57:00Z", "2026-11-05T00:11:00Z")
        validate_window("2026-11-01T00:00:00Z", "2026-12-02T00:00:00Z")
        for end in ("2026-11-04T09:07:00Z", "2026-11-04T09:06:00Z", "2026-12-05T09:08:00Z"):
            with self.subTest(end=end), self.assertRaises(ScheduleError):
                validate_window("2026-11-04T09:07:00Z", end)

    def test_cross_date_zones(self):
        self.assertEqual(resolve_local("2026-11-05T01:37", "Asia/Shanghai")["utc"], "2026-11-04T17:37:00Z")
        self.assertEqual(resolve_local("2026-11-04T23:07", "Asia/Kolkata")["utc"], "2026-11-04T17:37:00Z")
        for zone in ("not/a-zone", "UTC+08:00", None):
            with self.subTest(zone=zone), self.assertRaises(ScheduleError):
                resolve_local("2026-11-04T09:07", zone)

    def test_dst_is_explicit(self):
        with self.assertRaises(ScheduleError):
            resolve_local("2026-03-08T02:30", "America/New_York")
        with self.assertRaises(ScheduleError) as error:
            resolve_local("2026-11-01T01:30", "America/New_York")
        self.assertEqual(error.exception.code, "AMBIGUOUS_LOCAL_TIME")
        self.assertEqual(error.exception.details, {"offset_minutes": [-300, -240]})
        self.assertEqual(resolve_local("2026-11-01T01:30", "America/New_York", -240)["utc"], "2026-11-01T05:30:00Z")
        self.assertEqual(resolve_local("2026-11-01T01:30", "America/New_York", -300)["utc"], "2026-11-01T06:30:00Z")
        for offset in (0, True, "-240"):
            with self.subTest(offset=offset), self.assertRaises(ScheduleError):
                resolve_local("2026-11-01T01:30", "America/New_York", offset)


if __name__ == "__main__":
    unittest.main()
