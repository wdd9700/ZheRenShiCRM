import unittest
from datetime import datetime, timedelta, timezone

from team_schedule.availability import core, intervals, scanner

UTC = timezone.utc
DAY = datetime(2026, 11, 4, tzinfo=UTC)


def at(hour, minute=0, day=0):
    return DAY + timedelta(days=day, hours=hour, minutes=minute)


def window(start_hour=9, end_hour=14, day=0):
    return at(start_hour, day=day), at(end_hour, day=day)


def row(user, start, end):
    return {"user": user, "start_utc": start, "end_utc": end}


class AcceptanceExample(unittest.TestCase):
    """D010300 §7.3: window 09:00-14:00, min_minutes 20."""

    def setUp(self):
        self.window = window()
        self.rows = [
            row("a", at(9, 7), at(9, 42)),
            row("a", at(13, 3), at(13, 18)),
            row("b", at(9, 30), at(10, 5)),
            row("b", at(13, 18), at(13, 31)),
        ]
        self.busy = core.busy_by_user(["a", "b"], self.rows, *self.window)
        self.free = core.common_free([pieces for _, pieces in self.busy], *self.window, 20)

    def test_busy_is_per_person_and_sorted(self):
        self.assertEqual(self.busy, [
            ("a", [(at(9, 7), at(9, 42)), (at(13, 3), at(13, 18))]),
            ("b", [(at(9, 30), at(10, 5)), (at(13, 18), at(13, 31))]),
        ])

    def test_common_free_with_min_20(self):
        self.assertEqual(self.free, [(at(10, 5), at(13, 3)), (at(13, 31), at(14))])

    def test_adjacent_busy_between_people_creates_no_free_slot(self):
        union = intervals.union(*[pieces for _, pieces in self.busy])
        self.assertEqual(union, [(at(9, 7), at(10, 5)), (at(13, 3), at(13, 31))])

    def test_shorter_gaps_appear_without_the_minimum(self):
        self.assertEqual(core.common_free([pieces for _, pieces in self.busy], *self.window, 1), [
            (at(9), at(9, 7)),
            (at(10, 5), at(13, 3)),
            (at(13, 31), at(14)),
        ])


class Clipping(unittest.TestCase):
    def test_pieces_crossing_the_window_edges_are_cut(self):
        start, end = window()
        self.assertEqual(intervals.clip((at(8), at(9, 30)), start, end), (start, at(9, 30)))
        self.assertEqual(intervals.clip((at(13, 30), at(15)), start, end), (at(13, 30), end))

    def test_pieces_outside_or_touching_the_window_are_empty(self):
        start, end = window()
        self.assertIsNone(intervals.clip((at(7), at(9)), start, end))
        self.assertIsNone(intervals.clip((at(14), at(15)), start, end))
        self.assertIsNone(intervals.clip((at(12), at(12)), start, end))

    def test_cross_day_window_keeps_the_midnight_span(self):
        start, end = at(23), at(2, day=1)
        busy = [(at(23, 57), at(0, 11, day=1))]
        self.assertEqual(intervals.merge([intervals.clip(busy[0], start, end)]), busy)
        self.assertEqual(intervals.complement(start, end, busy), [(start, at(23, 57)), (at(0, 11, day=1), end)])


class Merging(unittest.TestCase):
    def test_adjacent_pieces_merge(self):
        self.assertEqual(intervals.merge([(at(9), at(10)), (at(10), at(11))]), [(at(9), at(11))])

    def test_overlapping_pieces_merge(self):
        self.assertEqual(intervals.merge([(at(9), at(10, 30)), (at(10), at(11))]), [(at(9), at(11))])

    def test_contained_piece_is_absorbed(self):
        self.assertEqual(intervals.merge([(at(9), at(12)), (at(10), at(11))]), [(at(9), at(12))])

    def test_duplicates_collapse(self):
        self.assertEqual(intervals.merge([(at(9), at(10)), (at(9), at(10))]), [(at(9), at(10))])

    def test_unsorted_input_is_normalized(self):
        self.assertEqual(intervals.merge([(at(12), at(13)), (at(9), at(10))]), [(at(9), at(10)), (at(12), at(13))])

    def test_empty_and_reversed_pieces_are_dropped(self):
        self.assertEqual(intervals.merge([(at(9), at(9)), (at(10), at(9)), (at(11), at(12))]), [(at(11), at(12))])

    def test_naive_datetimes_are_rejected(self):
        with self.assertRaises(ValueError):
            intervals.merge([(datetime(2026, 11, 4, 9), datetime(2026, 11, 4, 10))])


class Complement(unittest.TestCase):
    def test_all_busy_leaves_nothing_free(self):
        start, end = window()
        self.assertEqual(intervals.complement(start, end, [(at(8), at(15))]), [])

    def test_all_free_returns_the_whole_window(self):
        start, end = window()
        self.assertEqual(intervals.complement(start, end, []), [(start, end)])

    def test_busy_outside_the_window_is_ignored(self):
        start, end = window()
        self.assertEqual(intervals.complement(start, end, [(at(7), at(9)), (at(14), at(16))]), [(start, end)])


class MinuteLength(unittest.TestCase):
    def test_exact_minutes(self):
        self.assertEqual(intervals.minutes((at(9), at(9, 20))), 20)

    def test_sub_minute_and_empty_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            intervals.minutes((at(9), at(9) + timedelta(seconds=30)))
        with self.assertRaises(ValueError):
            intervals.minutes((at(9), at(9)))

    def test_minimum_is_inclusive(self):
        kept = intervals.filter_minutes([(at(9), at(9, 20)), (at(10), at(10, 19))], 20)
        self.assertEqual(kept, [(at(9), at(9, 20))])

    def test_non_integer_minimum_is_rejected(self):
        for bad in (0, -1, True, 20.0, "20"):
            with self.assertRaises(ValueError):
                intervals.filter_minutes([], bad)

    def test_window_shorter_than_the_minimum_has_no_free_time(self):
        self.assertEqual(core.common_free([], at(9), at(9, 10), 20), [])


class Composition(unittest.TestCase):
    def test_users_without_rows_are_reported_as_free(self):
        busy = core.busy_by_user(["a", "b"], [row("a", at(9), at(10))], *window())
        self.assertEqual(busy, [("a", [(at(9), at(10))]), ("b", [])])

    def test_requested_order_is_preserved(self):
        busy = core.busy_by_user(["b", "a"], [], *window())
        self.assertEqual([user for user, _ in busy], ["b", "a"])

    def test_rows_for_unrequested_users_are_ignored(self):
        busy = core.busy_by_user(["a"], [row("z", at(9), at(10))], *window())
        self.assertEqual(busy, [("a", [])])

    def test_duplicate_and_adjacent_rows_for_one_person_merge(self):
        rows = [row("a", at(9), at(10)), row("a", at(9), at(10)), row("a", at(10), at(11))]
        self.assertEqual(core.busy_by_user(["a"], rows, *window()), [("a", [(at(9), at(11))])])

    def test_scan_guard_rejects_incomplete_reads(self):
        self.assertEqual(len(core.guard_scan([{}] * core.SCAN_LIMIT)), core.SCAN_LIMIT)
        with self.assertRaises(core.ScanLimitExceeded):
            core.guard_scan([{}] * (core.SCAN_LIMIT + 1))


class ScannerStatement(unittest.TestCase):
    def test_one_branch_per_person_and_a_capped_result(self):
        statement = scanner.statement(["a", "b"])
        self.assertTrue(statement.startswith("SELECT * FROM ("))
        self.assertEqual(statement.count(" UNION ALL "), 1)
        self.assertTrue(statement.endswith("LIMIT %d" % (core.SCAN_LIMIT + 1)))

    def test_only_interval_columns_are_projected(self):
        statement = scanner.statement(["a", "b", "c"])
        self.assertEqual(statement.count("AS `user`, t.start_utc AS start_utc, t.end_utc AS end_utc"), 3)
        for leaked in ("title", "description", "source", "uid", "revision", "members"):
            self.assertNotIn(leaked, statement.lower())

    def test_occupancy_requires_active_busy_and_owner_or_accepted_member(self):
        statement = scanner.statement(["a"])
        self.assertIn("t.status='Active'", statement)
        self.assertIn("t.availability='Busy'", statement)
        self.assertIn("t.owner=%s", statement)
        self.assertIn("m.occupies=1", statement)

    def test_parameters_are_user_bound_in_order(self):
        self.assertEqual(
            scanner.parameters(["a", "b"], "2026-11-04T09:00:00Z", "2026-11-04T14:00:00Z"),
            ("a", "2026-11-04T14:00:00Z", "2026-11-04T09:00:00Z", "a", "a",
             "b", "2026-11-04T14:00:00Z", "2026-11-04T09:00:00Z", "b", "b"),
        )

    def test_out_of_range_people_are_rejected(self):
        for bad in ([], ["a"] * (core.MAX_PEOPLE + 1), "a", None):
            with self.assertRaises(ValueError):
                scanner.statement(bad)


if __name__ == "__main__":
    unittest.main()
