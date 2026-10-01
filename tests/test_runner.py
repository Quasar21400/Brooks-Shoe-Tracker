import unittest
from datetime import datetime, timedelta, timezone

from shoe_tracker.models import Offer, SourceResult
from shoe_tracker.runner import handle_health, handle_stock

from .fakes import TARGET


class RecordingNotifier:
    def __init__(self, deliver=True):
        self.deliver = deliver
        self.sent: list[tuple[str, int]] = []
        self.opened: list[str] = []
        self.closed: list[str] = []

    def channels(self):
        return ["ntfy"]

    def send(self, title, message, url="", priority=3, tags=()):
        self.sent.append((title, priority))
        return self.deliver

    def open_issue(self, issues, key, title, body):
        self.opened.append(key)
        issues.setdefault(key, 7)
        return self.deliver

    def close_issue(self, issues, key, comment):
        issues.pop(key, None)
        self.closed.append(key)


def result(name, *keys, error=None):
    return SourceResult(name, "status", [Offer(k, name, "online", f"https://x/{k}") for k in keys], error)


class StockTests(unittest.TestCase):
    def test_alerts_once_per_new_offer(self):
        state, n = {}, RecordingNotifier()
        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        self.assertEqual(len(n.sent), 1)
        self.assertEqual(n.sent[0][1], 5)
        self.assertIn("brooks:1", state["offers"])

        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        self.assertEqual(len(n.sent), 1)  # nothing new, no repeat alert

        handle_stock([result("Brooks Running", "brooks:1"), result("Shop", "shop:9")], state, n, TARGET)
        self.assertEqual(len(n.sent), 2)

    def test_sold_out_again_closes_issue(self):
        state, n = {}, RecordingNotifier()
        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        handle_stock([result("Brooks Running")], state, n, TARGET)
        self.assertEqual(state["offers"], {})
        self.assertTrue(n.sent[-1][0].startswith("Sold out again"))
        self.assertEqual(n.closed, ["stock"])

    def test_failed_source_keeps_its_offers(self):
        state, n = {}, RecordingNotifier()
        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        handle_stock([result("Brooks Running", error="HTTP 403")], state, n, TARGET)
        self.assertIn("brooks:1", state["offers"])
        self.assertEqual(len(n.sent), 1)

    def test_undelivered_alert_is_retried(self):
        state, n = {}, RecordingNotifier(deliver=False)
        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        self.assertNotIn("brooks:1", state["offers"])
        n.deliver = True
        handle_stock([result("Brooks Running", "brooks:1")], state, n, TARGET)
        self.assertIn("brooks:1", state["offers"])
        self.assertEqual(len(n.sent), 2)


class HealthTests(unittest.TestCase):
    def test_alerts_after_threshold_then_recovers(self):
        state, n = {}, RecordingNotifier()
        t0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        bad = [result("Brooks Running", error="HTTP 403")]
        handle_health(bad, state, n, t0, 6)
        handle_health(bad, state, n, t0 + timedelta(hours=5), 6)
        self.assertEqual(n.sent, [])
        handle_health(bad, state, n, t0 + timedelta(hours=6), 6)
        handle_health(bad, state, n, t0 + timedelta(hours=7), 6)
        self.assertEqual(len(n.sent), 1)
        self.assertEqual(n.opened, ["health:Brooks Running"])

        handle_health([result("Brooks Running")], state, n, t0 + timedelta(hours=8), 6)
        self.assertEqual(state["health"], {})
        self.assertTrue(n.sent[-1][0].startswith("Tracker recovered"))
        self.assertEqual(n.closed, ["health:Brooks Running"])

    def test_short_outage_is_silent(self):
        state, n = {}, RecordingNotifier()
        t0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
        handle_health([result("Shop", error="timeout")], state, n, t0, 6)
        handle_health([result("Shop")], state, n, t0 + timedelta(hours=1), 6)
        self.assertEqual(n.sent, [])
        self.assertEqual(state["health"], {})


if __name__ == "__main__":
    unittest.main()
