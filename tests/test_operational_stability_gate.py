"""Tests for bar-close-aware operational stability gate."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = Path = __import__("pathlib").Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from operational_stability_gate import (  # noqa: E402
    BLOCKED_BAR_CLOSE_WINDOW,
    BLOCKED_CLASSIFICATION,
    BarCloseContext,
    _civil_minute_close_after,
    _next_post_close_sample_target,
    evaluate_operational_stability_sample,
    extract_bar_close_context,
    is_post_close_sample,
    is_target_post_close_sample,
    resolve_post_close_window_seconds,
    resolve_provider_roll_latency_seconds,
    run_bar_close_aware_stability_window,
    run_operational_stability_window,
    wait_for_bar_complete,
)


def _utc(y: int, m: int, d: int, h: int, mi: int, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=timezone.utc)


def _good_health(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    return {
        "status": "ok",
        "recorded_utc": stamp,
        "data_quality": {"state_complete": True, "issues": []},
        "execution_recovery": {"blockingNewExposure": False},
        "market_observation": {
            "last_succeeded_utc": stamp,
            "last_error": None,
        },
        "read_circuit_breaker": {"bars": {"open": False}},
        "position": {"open_quantity": 0},
    }


def _packet_at(now: datetime) -> dict:
    """Simulate provider roll: first 5s after minute = prior bar closed."""
    cur_min = now.replace(second=0, microsecond=0)
    if now.second < 5:
        latest = cur_min - timedelta(minutes=1)
        partial = False
    else:
        latest = cur_min
        partial = int(latest.timestamp() * 1000) + 60_000 > int(now.timestamp() * 1000)
    prior = latest - timedelta(minutes=1)
    return {
        "data_quality": {"state_complete": True, "issues": []},
        "account": {"instrument_open_contracts": 0},
        "market": {"quote_timestamp": now.isoformat().replace("+00:00", "Z")},
        "market_observation": {
            "observation": {
                "source": "projectx_bars",
                "timeframes": [
                    {
                        "timeframe_minutes": 1,
                        "latest_bar_utc": latest.isoformat().replace("+00:00", "Z"),
                        "latest_bar_partial": partial,
                        "prior_completed_bar": {
                            "timestamp": prior.isoformat().replace("+00:00", "Z"),
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "volume": 10,
                        },
                        "bars_accepted": 500,
                    }
                ],
            }
        },
    }


def _stale_partial_packet(now: datetime, latest_minute: datetime) -> dict:
    """Packet stuck on partial bar after its close — v11 warmup_sync_timeout reproduction."""
    prior = latest_minute - timedelta(minutes=1)
    return {
        "data_quality": {"state_complete": True, "issues": []},
        "account": {"instrument_open_contracts": 0},
        "market": {"quote_timestamp": now.isoformat().replace("+00:00", "Z")},
        "market_observation": {
            "observation": {
                "source": "projectx_bars",
                "timeframes": [
                    {
                        "timeframe_minutes": 1,
                        "latest_bar_utc": latest_minute.isoformat().replace("+00:00", "Z"),
                        "latest_bar_partial": True,
                        "prior_completed_bar": {
                            "timestamp": prior.isoformat().replace("+00:00", "Z"),
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "volume": 10,
                        },
                        "bars_accepted": 500,
                    }
                ],
            }
        },
    }


def _partial_packet(now: datetime) -> dict:
    cur_min = now.replace(second=0, microsecond=0)
    return {
        "data_quality": {"state_complete": True, "issues": []},
        "account": {"instrument_open_contracts": 0},
        "market": {"quote_timestamp": now.isoformat().replace("+00:00", "Z")},
        "market_observation": {
            "observation": {
                "source": "projectx_bars",
                "timeframes": [
                    {
                        "timeframe_minutes": 1,
                        "latest_bar_utc": cur_min.isoformat().replace("+00:00", "Z"),
                        "latest_bar_partial": True,
                        "prior_completed_bar": {
                            "timestamp": (cur_min - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                            "open": 1,
                            "high": 2,
                            "low": 1,
                            "close": 2,
                            "volume": 10,
                        },
                        "bars_accepted": 500,
                    }
                ],
            }
        },
    }


class BarCloseContextTests(unittest.TestCase):
    def test_extract_expected_close(self) -> None:
        now = _utc(2026, 9, 8, 14, 0, 30)
        packet = _partial_packet(now)
        ctx = extract_bar_close_context(packet, now=now)
        self.assertIsNotNone(ctx)
        self.assertIn(ctx.latest_bar_utc[:16], "2026-09-08T14:00")
        self.assertEqual(ctx.expected_close_utc, "2026-09-08T14:01:00Z")

    def test_post_close_window_timezone(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        packet = _packet_at(now)
        ctx = extract_bar_close_context(packet, now=now)
        assert ctx is not None
        inside = _utc(2026, 9, 8, 14, 1, 3)
        outside = _utc(2026, 9, 8, 14, 1, 6)
        self.assertTrue(is_post_close_sample(inside, ctx, post_close_window_seconds=5.0))
        self.assertFalse(is_post_close_sample(outside, ctx, post_close_window_seconds=5.0))

    def test_roll_anchored_sample_after_provider_latency(self) -> None:
        """v10 evidence: provider roll ~9s after clock close with prior_completed_bar."""
        now = _utc(2026, 9, 8, 20, 11, 9)
        packet = {
            "data_quality": {"state_complete": True, "issues": []},
            "account": {"instrument_open_contracts": 0},
            "market_observation": {
                "observation": {
                    "source": "projectx_bars",
                    "timeframes": [
                        {
                            "timeframe_minutes": 1,
                            "latest_bar_utc": "2026-09-08T20:11:00.000Z",
                            "latest_bar_partial": True,
                            "prior_completed_bar": {
                                "timestamp": "2026-09-08T20:10:00.000Z",
                                "open": 1,
                                "high": 2,
                                "low": 1,
                                "close": 2,
                                "volume": 10,
                            },
                        }
                    ],
                }
            },
        }
        ctx = extract_bar_close_context(packet, now=now)
        assert ctx is not None
        self.assertFalse(is_post_close_sample(now, ctx, post_close_window_seconds=5.0, provider_roll_latency_seconds=0.0))
        self.assertTrue(
            is_post_close_sample(now, ctx, post_close_window_seconds=5.0, provider_roll_latency_seconds=10.0)
        )

    def test_resolve_window_config_from_env(self) -> None:
        with mock.patch.dict("os.environ", {"GLITCH_OPERATIONAL_POST_CLOSE_WINDOW_SECONDS": "7"}):
            self.assertEqual(resolve_post_close_window_seconds(), 7.0)
        with mock.patch.dict("os.environ", {"GLITCH_PROVIDER_ROLL_LATENCY_SECONDS": "12"}):
            self.assertEqual(resolve_provider_roll_latency_seconds(), 12.0)


class WaitForBarCompleteTests(unittest.TestCase):
    def test_succeeds_post_close_with_always_partial_feed(self) -> None:
        """Provider keeps latest_bar_partial=true after roll — clock alignment must still pass."""
        post_close = _utc(2026, 9, 8, 14, 1, 1)
        times = [_utc(2026, 9, 8, 14, 0, 45), post_close, post_close, post_close]

        def now_fn() -> datetime:
            if len(times) > 1:
                return times.pop(0)
            return times[0]

        result = wait_for_bar_complete(
            lambda: _partial_packet(post_close),
            timeout_seconds=30.0,
            poll_seconds=0.0,
            sleep_fn=lambda _s: None,
            monotonic_fn=lambda: 0.0,
            now_fn=now_fn,
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["expected_close_utc"], "2026-09-08T14:01:00Z")
        self.assertTrue(result["latest_bar_partial"])

    def test_succeeds_on_provider_roll_after_close(self) -> None:
        """Provider rolls latest_bar ~8s late — bar_roll_confirmed must pass."""
        start = _utc(2026, 9, 8, 14, 0, 45)
        post_close = _utc(2026, 9, 8, 14, 1, 8)
        times = [start, _utc(2026, 9, 8, 14, 1, 0), post_close, post_close]
        fetches = {"n": 0}

        def now_fn() -> datetime:
            if len(times) > 1:
                return times.pop(0)
            return times[0]

        def packet_fetcher() -> dict:
            fetches["n"] += 1
            if fetches["n"] <= 2:
                return _partial_packet(start)
            cur = post_close.replace(second=0, microsecond=0)
            pkt = _partial_packet(post_close)
            tf = pkt["market_observation"]["observation"]["timeframes"][0]
            tf["latest_bar_utc"] = cur.isoformat().replace("+00:00", "Z")
            tf["prior_completed_bar"]["timestamp"] = (cur - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
            return pkt

        result = wait_for_bar_complete(
            packet_fetcher,
            timeout_seconds=30.0,
            poll_seconds=0.0,
            sleep_fn=lambda _s: None,
            monotonic_fn=lambda: 0.0,
            now_fn=now_fn,
        )
        self.assertTrue(result["ready"])
        self.assertTrue(result.get("bar_roll_confirmed") or result.get("expected_close_utc"))

    def test_fails_when_window_missed_before_timeout(self) -> None:
        # 16s past close exceeds strict 5s + default 10s provider roll grace
        t0 = _utc(2026, 9, 8, 14, 1, 16)
        mono = {"v": 0.0}

        def monotonic_fn() -> float:
            mono["v"] += 1.0
            return mono["v"]

        result = wait_for_bar_complete(
            lambda: _partial_packet(t0),
            timeout_seconds=5.0,
            poll_seconds=0.0,
            sleep_fn=lambda _s: None,
            monotonic_fn=monotonic_fn,
            now_fn=lambda: t0,
        )
        self.assertFalse(result["ready"])
        self.assertIn(result["reason"], {"bar_still_partial", "bar_close_alignment_timeout"})

    def test_late_bar_roll_after_22s_abandons_boundary(self) -> None:
        """v11 evidence: bar_roll_confirmed ~22s late must not count as ready."""
        start = _utc(2026, 9, 8, 22, 16, 36)
        late_roll = _utc(2026, 9, 8, 22, 17, 22)
        clock = {"t": start}
        fetches = {"n": 0}
        mono = {"v": 0.0}

        def now_fn() -> datetime:
            return clock["t"]

        def packet_fetcher() -> dict:
            fetches["n"] += 1
            if clock["t"] < late_roll:
                return _stale_partial_packet(clock["t"], _utc(2026, 9, 8, 22, 16, 0))
            return _stale_partial_packet(late_roll, _utc(2026, 9, 8, 22, 17, 0))

        def sleep_fn(seconds: float) -> None:
            step = max(seconds, 0.1)
            mono["v"] += step
            clock["t"] = clock["t"] + timedelta(seconds=step)

        result = wait_for_bar_complete(
            packet_fetcher,
            timeout_seconds=5.0,
            poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=now_fn,
        )
        self.assertFalse(result["ready"])
        missed = result.get("missed_boundaries") or []
        self.assertGreaterEqual(len(missed), 1)
        self.assertEqual(missed[0]["reason"], "missed_post_close_window")

    def test_civil_minute_close_after_aligns_with_scheduler(self) -> None:
        self.assertEqual(
            _civil_minute_close_after(_utc(2026, 9, 8, 22, 17, 28)),
            _utc(2026, 9, 8, 22, 18, 0),
        )
        self.assertEqual(
            _civil_minute_close_after(_utc(2026, 9, 8, 22, 18, 1)),
            _utc(2026, 9, 8, 22, 19, 0),
        )

    def test_v11_five_boundary_partial_roll_never_ready(self) -> None:
        """v11 partial-roll scenario: civil realignment missed 15s window; packet-close target recovers."""
        clock = {"t": _utc(2026, 9, 8, 22, 52, 26)}
        mono = {"v": 0.0}
        fetches = {"n": 0}

        def _v11_packet(now: datetime) -> dict:
            latest = now.replace(second=0, microsecond=0)
            prior = latest - timedelta(minutes=1)
            return {
                "data_quality": {"state_complete": True, "issues": []},
                "account": {"instrument_open_contracts": 0},
                "market": {"quote_timestamp": now.isoformat().replace("+00:00", "Z")},
                "market_observation": {
                    "observation": {
                        "source": "projectx_bars",
                        "timeframes": [
                            {
                                "timeframe_minutes": 1,
                                "latest_bar_utc": latest.isoformat().replace("+00:00", "Z"),
                                "latest_bar_partial": True,
                                "prior_completed_bar": {
                                    "timestamp": prior.isoformat().replace("+00:00", "Z"),
                                    "open": 1,
                                    "high": 2,
                                    "low": 1,
                                    "close": 2,
                                    "volume": 10,
                                },
                                "bars_accepted": 500,
                            }
                        ],
                    }
                },
            }

        def now_fn() -> datetime:
            return clock["t"]

        def sleep_fn(seconds: float) -> None:
            step = max(seconds, 0.01)
            mono["v"] += step
            clock["t"] = clock["t"] + timedelta(seconds=step)

        def packet_fetcher() -> dict:
            fetches["n"] += 1
            if fetches["n"] == 1:
                raise TimeoutError("gateway_timeout")
            return _v11_packet(clock["t"])

        result = wait_for_bar_complete(
            packet_fetcher,
            timeout_seconds=120.0,
            poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=now_fn,
        )
        self.assertTrue(result["ready"])
        self.assertTrue(result.get("latest_bar_partial"))
        self.assertLess(result["waited_seconds"], 120.0)
        missed = result.get("missed_boundaries") or []
        self.assertLessEqual(len(missed), 1)

    def test_next_post_close_sample_target_partial_bar(self) -> None:
        ctx = extract_bar_close_context(
            _stale_partial_packet(_utc(2026, 9, 8, 22, 52, 26), _utc(2026, 9, 8, 22, 52, 0)),
            now=_utc(2026, 9, 8, 22, 52, 26),
        )
        assert ctx is not None
        target = _next_post_close_sample_target(ctx, _utc(2026, 9, 8, 22, 52, 26))
        self.assertEqual(target, _utc(2026, 9, 8, 22, 53, 0))
        late = _utc(2026, 9, 8, 22, 53, 16)
        self.assertEqual(_next_post_close_sample_target(ctx, late), _utc(2026, 9, 8, 22, 54, 0))
        self.assertEqual(_civil_minute_close_after(late), _utc(2026, 9, 8, 22, 54, 0))

    def test_target_post_close_rejects_late_roll_without_prior_alignment(self) -> None:
        now = _utc(2026, 9, 8, 22, 17, 22)
        ctx = extract_bar_close_context(
            _stale_partial_packet(now, _utc(2026, 9, 8, 22, 17, 0)),
            now=now,
        )
        assert ctx is not None
        target = _utc(2026, 9, 8, 22, 17, 0)
        self.assertFalse(
            is_target_post_close_sample(
                now,
                target,
                ctx,
                post_close_window_seconds=5.0,
                provider_roll_latency_seconds=10.0,
            )
        )


@mock.patch("operational_stability_gate._measurement_helpers")
class MissedBoundaryRealignTests(unittest.TestCase):
    def test_v11_stale_packet_advances_to_next_civil_close(self, helpers: mock.MagicMock) -> None:
        """Warmup must not loop on expired 22:17 boundary when packet is stale."""
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 22, 17, 28)}
        mono = {"v": 0.0}
        stale_minute = _utc(2026, 9, 8, 22, 17, 0)

        def now_fn() -> datetime:
            return clock["t"]

        def sleep_fn(seconds: float) -> None:
            mono["v"] += seconds
            clock["t"] = clock["t"] + timedelta(seconds=seconds)

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _stale_partial_packet(now_fn(), stale_minute),
            required_samples=5,
            max_duration_seconds=600.0,
            max_warmup_seconds=90.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=now_fn,
        )
        closes = [e["expected_close_utc"] for e in result.get("warmup_events") or []]
        self.assertIn("2026-09-08T22:17:00Z", closes)
        self.assertEqual(closes.count("2026-09-08T22:17:00Z"), 1)
        self.assertGreater(clock["t"], _utc(2026, 9, 8, 22, 17, 28))

    def test_multiple_missed_boundaries_then_success(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 14, 0, 50)}
        mono = {"v": 0.0}
        phase = {"stale_until": _utc(2026, 9, 8, 14, 2, 0)}

        def now_fn() -> datetime:
            return clock["t"]

        def sleep_fn(seconds: float) -> None:
            mono["v"] += seconds
            clock["t"] = clock["t"] + timedelta(seconds=seconds)

        def packet_fetcher() -> dict:
            if clock["t"] < phase["stale_until"]:
                return _stale_partial_packet(clock["t"], _utc(2026, 9, 8, 14, 0, 0))
            return _packet_at(clock["t"])

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=packet_fetcher,
            required_samples=3,
            max_duration_seconds=600.0,
            max_warmup_seconds=180.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=now_fn,
        )
        self.assertTrue(result["confirmed"])
        self.assertGreaterEqual(len(result["samples"]), 3)
        missed = [e["expected_close_utc"] for e in result.get("warmup_events") or []]
        self.assertGreaterEqual(len(set(missed)), 1)

    def test_bounded_valid_window_timeout(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 14, 1, 2)}
        mono = {"v": 0.0}

        def sleep_fn(seconds: float) -> None:
            mono["v"] += max(seconds, 0.05)

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(clock["t"]),
            packet_fetcher=lambda: _packet_at(clock["t"]),
            required_samples=5,
            max_duration_seconds=10.0,
            max_warmup_seconds=5.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=lambda: clock["t"],
        )
        self.assertFalse(result["confirmed"])
        self.assertLessEqual(result.get("valid_window_elapsed_seconds") or 0, 10.5)

    def test_packet_timeout_recorded(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        calls = {"n": 0}

        def packet_fetcher() -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("packet timeout")
            return _packet_at(_utc(2026, 9, 8, 14, 1, 2))

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(_utc(2026, 9, 8, 14, 1, 2)),
            packet_fetcher=packet_fetcher,
            required_samples=1,
            max_duration_seconds=60.0,
            post_close_poll_seconds=0.0,
            sleep_fn=lambda _s: None,
            monotonic_fn=lambda: 0.0,
            now_fn=lambda: _utc(2026, 9, 8, 14, 1, 2),
        )
        self.assertGreaterEqual(len(result.get("gateway_timeouts") or []), 1)

    def test_no_infinite_retry_on_same_boundary(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 22, 17, 28)}
        mono = {"v": 0.0}
        iterations = {"n": 0}

        def packet_fetcher() -> dict:
            iterations["n"] += 1
            return _stale_partial_packet(clock["t"], _utc(2026, 9, 8, 22, 17, 0))

        def sleep_fn(seconds: float) -> None:
            mono["v"] += seconds
            clock["t"] = clock["t"] + timedelta(seconds=seconds)

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(clock["t"]),
            packet_fetcher=packet_fetcher,
            required_samples=5,
            max_duration_seconds=600.0,
            max_warmup_seconds=30.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=lambda: clock["t"],
        )
        self.assertFalse(result["confirmed"])
        self.assertLess(iterations["n"], 50)
        closes = [e["expected_close_utc"] for e in result.get("warmup_events") or []]
        if len(closes) >= 2:
            self.assertNotEqual(closes[0], closes[-1])


@mock.patch("operational_stability_gate._measurement_helpers")
class MissingPriorBarTests(unittest.TestCase):
    def test_partial_without_prior_completed_bar_fails(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: ["bar_1m_partial"], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 3)
        cur_min = now.replace(second=0, microsecond=0)
        packet = {
            "data_quality": {"state_complete": True, "issues": []},
            "account": {"instrument_open_contracts": 0},
            "market_observation": {
                "observation": {
                    "source": "projectx_bars",
                    "timeframes": [
                        {
                            "timeframe_minutes": 1,
                            "latest_bar_utc": cur_min.isoformat().replace("+00:00", "Z"),
                            "latest_bar_partial": True,
                            "bars_accepted": 500,
                        }
                    ],
                }
            },
        }
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertIn("bar_1m_partial", verdict.reasons)


@mock.patch("operational_stability_gate._measurement_helpers")
class EvaluateSampleTests(unittest.TestCase):
    def test_pre_close_sample_rejected(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 0, 45)
        packet = _partial_packet(now)
        ctx = extract_bar_close_context(packet, now=now)
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
            bar_close_context=ctx,
        )
        self.assertFalse(verdict.ok)
        self.assertTrue(
            "sample_before_bar_close_window" in verdict.reasons or "bar_1m_partial" in verdict.reasons
        )

    def test_post_close_with_new_partial_bar_counts(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: ["bar_1m_partial"], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 3)
        cur_min = now.replace(second=0, microsecond=0)
        prior = cur_min - timedelta(minutes=1)
        packet = {
            "data_quality": {"state_complete": True, "issues": []},
            "account": {"instrument_open_contracts": 0},
            "market": {"quote_timestamp": now.isoformat().replace("+00:00", "Z")},
            "market_observation": {
                "observation": {
                    "source": "projectx_bars",
                    "timeframes": [
                        {
                            "timeframe_minutes": 1,
                            "latest_bar_utc": cur_min.isoformat().replace("+00:00", "Z"),
                            "latest_bar_partial": True,
                            "prior_completed_bar": {
                                "timestamp": prior.isoformat().replace("+00:00", "Z"),
                                "open": 1,
                                "high": 2,
                                "low": 1,
                                "close": 2,
                                "volume": 10,
                            },
                            "bars_accepted": 500,
                        }
                    ],
                }
            },
        }
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertTrue(verdict.ok)

    def test_partial_bar_fails(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: ["bar_1m_partial"], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 0, 45)
        packet = _partial_packet(now)
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertTrue(
            "bar_1m_partial" in verdict.reasons or "sample_before_bar_close_window" in verdict.reasons
        )

    def test_health_packet_divergence_fails(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        packet = _packet_at(now)
        health = _good_health(now)
        health["data_quality"] = {"state_complete": False, "issues": ["account_state_stale"]}
        verdict = evaluate_operational_stability_sample(
            health=health,
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertIn("health_state_complete_false", verdict.reasons)
        self.assertIn("account_state_stale", verdict.reasons)
        self.assertIn("health_packet_state_complete_divergence", verdict.reasons)

    def test_degraded_refresh_timeout_blocks_valid_sample(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        packet = _packet_at(now)
        packet["data_quality"] = {
            "state_complete": True,
            "issues": [],
            "optional_issues": ["market_observation_refresh_timeout"],
        }
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertIn("packet_optional_market_observation_refresh_timeout", verdict.reasons)

    def test_stale_observation_blocks_valid_sample(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        packet = _packet_at(now)
        packet["data_quality"] = {
            "state_complete": False,
            "issues": ["market_observation_stale"],
            "optional_issues": ["market_observation_refresh_timeout"],
        }
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertIn("packet_market_observation_stale", verdict.reasons)
        self.assertIn("packet_state_complete_false", verdict.reasons)
        self.assertIn("health_packet_state_complete_divergence", verdict.reasons)

    def test_crossed_bbo_blocks_valid_sample(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        packet = _packet_at(now)
        packet["data_quality"] = {
            "state_complete": False,
            "issues": ["quote_geometry_invalid"],
            "optional_issues": [],
        }
        verdict = evaluate_operational_stability_sample(
            health=_good_health(now),
            packet=packet,
            fetched_utc=now.isoformat().replace("+00:00", "Z"),
            now=now,
            require_closed_bar=True,
        )
        self.assertFalse(verdict.ok)
        self.assertIn("packet_quote_geometry_invalid", verdict.reasons)
        self.assertIn("packet_state_complete_false", verdict.reasons)

    def test_circuit_breaker_open_fails(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        health = _good_health(now)
        health["read_circuit_breaker"] = {"bars": {"open": True}}
        verdict = evaluate_operational_stability_sample(health=health, packet=_packet_at(now), now=now)
        self.assertFalse(verdict.ok)
        self.assertTrue(any(r.startswith("circuit_breaker_") for r in verdict.reasons))

    def test_recovery_blocked_fails(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        now = _utc(2026, 9, 8, 14, 1, 2)
        health = _good_health(now)
        health["execution_recovery"] = {"blockingNewExposure": True}
        verdict = evaluate_operational_stability_sample(health=health, packet=_packet_at(now), now=now)
        self.assertFalse(verdict.ok)
        self.assertIn("recovery_blocked", verdict.reasons)


@mock.patch("operational_stability_gate._measurement_helpers")
class BarCloseAwareWindowTests(unittest.TestCase):
    def test_five_closes_pass(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 14, 0, 10)}

        def now_fn() -> datetime:
            return clock["t"]

        def advance(seconds: float) -> None:
            clock["t"] = clock["t"] + timedelta(seconds=seconds)

        def sleep_fn(seconds: float) -> None:
            advance(seconds)

        def health_fetcher() -> dict:
            return _good_health(now_fn())

        def packet_fetcher() -> dict:
            return _packet_at(now_fn())

        result = run_bar_close_aware_stability_window(
            health_fetcher=health_fetcher,
            packet_fetcher=packet_fetcher,
            required_samples=5,
            max_duration_seconds=600.0,
            post_close_window_seconds=5.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: 0.0,
            now_fn=now_fn,
        )
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["sampling_mode"], "bar_close_aware")
        self.assertEqual(len(result["samples"]), 5)
        closed = [row["closed_bar_utc"] for row in result["samples"]]
        self.assertEqual(len(set(closed)), 5)

    def test_timeout_blocked_bar_close_window(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        stuck = _utc(2026, 9, 8, 14, 0, 50)
        mono = {"v": 0.0}

        def sleep_fn(seconds: float) -> None:
            mono["v"] += seconds

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(stuck),
            packet_fetcher=lambda: _partial_packet(stuck),
            required_samples=5,
            max_duration_seconds=30.0,
            max_warmup_seconds=30.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=lambda: stuck,
        )
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["classification"], BLOCKED_BAR_CLOSE_WINDOW)
        self.assertEqual(result["stop_reason"], "warmup_sync_timeout")

    def test_warmup_missed_close_does_not_start_valid_window(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        clock = {"t": _utc(2026, 9, 8, 14, 0, 50)}
        mono = {"v": 0.0}

        def now_fn() -> datetime:
            return clock["t"]

        def sleep_fn(seconds: float) -> None:
            mono["v"] += seconds
            clock["t"] = clock["t"] + timedelta(seconds=seconds)

        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _partial_packet(now_fn()),
            required_samples=5,
            max_duration_seconds=10.0,
            max_warmup_seconds=5.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: mono["v"],
            now_fn=now_fn,
        )
        self.assertFalse(result["confirmed"])
        self.assertGreaterEqual(len(result.get("warmup_events") or []), 1)
        self.assertIn("warmup_events", result)

    def test_lease_occupied_blocks(self, helpers: mock.MagicMock) -> None:
        helpers.return_value = (lambda _p: [], lambda _p: (True, "capacity_gate"))
        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(),
            packet_fetcher=lambda: _packet_at(_utc(2026, 9, 8, 14, 1, 2)),
            required_samples=5,
            max_duration_seconds=10.0,
            sleep_fn=lambda _s: None,
            monotonic_fn=lambda: 0.0,
            now_fn=lambda: _utc(2026, 9, 8, 14, 1, 2),
            lease_checker=lambda: (False, "lease_occupied"),
        )
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["stop_reason"], "lease_occupied")


class PostCloseOfflineScenarioTests(unittest.TestCase):
    """Offline reproduction of post-close health/packet coherence scenarios."""

    def _evaluate(self, health: dict, packet: dict, now: datetime) -> object:
        with mock.patch(
            "operational_stability_gate._measurement_helpers",
            return_value=(lambda _p: [], lambda _p: (True, "capacity_gate")),
        ):
            return evaluate_operational_stability_sample(
                health=health,
                packet=packet,
                fetched_utc=now.isoformat().replace("+00:00", "Z"),
                now=now,
                require_closed_bar=True,
            )

    def test_fresh_account_at_bar_close_passes(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        verdict = self._evaluate(_good_health(now), _packet_at(now), now)
        self.assertTrue(verdict.ok)

    def test_stale_account_at_bar_close_fails(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        health = _good_health(now)
        health["data_quality"] = {
            "state_complete": False,
            "issues": ["account_state_stale"],
        }
        packet = _packet_at(now)
        packet["data_quality"] = {
            "state_complete": False,
            "issues": ["account_state_stale"],
        }
        verdict = self._evaluate(health, packet, now)
        self.assertFalse(verdict.ok)
        self.assertIn("account_state_stale", verdict.reasons)

    def test_health_stale_packet_fresh_fails_divergence(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        health = _good_health(now)
        health["data_quality"] = {"state_complete": False, "issues": ["account_state_stale"]}
        packet = _packet_at(now)
        verdict = self._evaluate(health, packet, now)
        self.assertFalse(verdict.ok)
        self.assertIn("health_packet_state_complete_divergence", verdict.reasons)

    def test_health_and_packet_same_cycle_pass(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        verdict = self._evaluate(_good_health(now), _packet_at(now), now)
        self.assertFalse(verdict.detail.get("state_complete_divergence"))

    def test_recovery_blocked_fails_at_bar_close(self) -> None:
        now = _utc(2026, 9, 8, 14, 1, 3)
        health = _good_health(now)
        health["execution_recovery"] = {"blockingNewExposure": True}
        verdict = self._evaluate(health, _packet_at(now), now)
        self.assertIn("recovery_blocked", verdict.reasons)


class LegacyPollTests(unittest.TestCase):
    def test_degraded_sample_fails(self) -> None:
        health = _good_health()
        health["status"] = "degraded"
        verdict = evaluate_operational_stability_sample(health=health, fetched_utc=health["recorded_utc"])
        self.assertFalse(verdict.ok)
        self.assertIn("status_degraded", verdict.reasons)

    def test_window_stops_on_degraded(self) -> None:
        seq = [_good_health(), {**_good_health(), "status": "degraded"}]
        idx = {"n": 0}

        def fetcher() -> dict:
            row = seq[min(idx["n"], len(seq) - 1)]
            idx["n"] += 1
            return row

        result = run_operational_stability_window(
            health_fetcher=fetcher,
            required_samples=5,
            max_duration_seconds=10,
            poll_interval_seconds=0,
            sleep_fn=lambda _s: None,
            bar_close_aware=False,
        )
        self.assertFalse(result["confirmed"])
        self.assertEqual(result["classification"], BLOCKED_CLASSIFICATION)
        self.assertEqual(result["stop_reason"], "degraded_during_window")

    def test_window_confirms_five_consecutive_legacy(self) -> None:
        result = run_operational_stability_window(
            health_fetcher=_good_health,
            required_samples=5,
            max_duration_seconds=10,
            poll_interval_seconds=0,
            sleep_fn=lambda _s: None,
            bar_close_aware=False,
        )
        self.assertTrue(result["confirmed"])
        self.assertEqual(len(result["samples"]), 5)


if __name__ == "__main__":
    unittest.main()
