import pytest

from barkueue.util.exchange import match_topic


class TestStar:
    def test_matches_one_segment(self):
        assert match_topic("order.*", "order.created") is True

    def test_rejects_multiple_segments(self):
        assert match_topic("order.*", "order.created.log") is False

    def test_rejects_zero_segments(self):
        assert match_topic("order.*", "order") is False

    def test_matches_any_segment_value(self):
        assert match_topic("*.log", "order.log") is True
        assert match_topic("*.log", "payment.log") is True


class TestHash:
    def test_matches_zero_segments(self):
        assert match_topic("order.#", "order") is True

    def test_matches_multiple_segments(self):
        assert match_topic("order.#", "order.created.log") is True

    def test_catch_all(self):
        assert match_topic("#", "anything.here") is True
        assert match_topic("#", "x") is True
        assert match_topic("#", "") is True

    def test_in_middle(self):
        assert match_topic("order.#.log", "order.log") is True
        assert match_topic("order.#.log", "order.a.b.log") is True

    def test_in_middle_rejects_wrong_ending(self):
        assert match_topic("order.#.log", "order.log.extra") is False

    def test_at_beginning(self):
        assert match_topic("#.log", "a.log") is True
        assert match_topic("#.log", "a.b.log") is True
        assert match_topic("#.log", "log") is True


class TestExact:
    def test_exact_match(self):
        assert match_topic("order.created", "order.created") is True

    def test_exact_mismatch(self):
        assert match_topic("order.created", "order.updated") is False

    def test_exact_mismatch_suffix(self):
        assert match_topic("order", "order.created") is False


class TestEdgeCases:
    @pytest.mark.parametrize(
        "pattern,topic,expected",
        [
            ("order.*.#", "order.created", True),
            ("order.*.#", "order.created.log.error", True),
            ("order.*.#", "order", False),
            ("*.*.log", "a.b.log", True),
            ("*.*.log", "a.log", False),
            ("", "", True),
        ],
    )
    def test_combinations(self, pattern, topic, expected):
        assert match_topic(pattern, topic) is expected
