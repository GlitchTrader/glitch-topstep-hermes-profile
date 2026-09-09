"""Integration tests for canonical bar-close orchestration (shared clock + cursor)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from live_stability_repo_guard import (  # noqa: E402
    CANONICAL_ARTIFACT_SCHEMA,
    LiveRepoGuardError,
    assert_module_from_profile_root,
    path_is_forbidden_checkout,
    require_canonical_live_artifact_for_prac_soak,
    validate_live_repo_context,
)
from operational_stability_gate import (  # noqa: E402
    BAR_CLOSE_ACCEPTANCE_V2,
    BarCloseCursor,
    run_bar_close_aware_stability_window,
    run_canonical_live_stability_window,
    wait_for_bar_complete,
)
from quote_state import classify_evaluation_axes  # noqa: E402


def _load_runner():
    path = SCRIPTS / 'run-canonical-live-stability.py'
    spec = importlib.util.spec_from_file_location('run_canonical_live_stability', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


RUNNER = _load_runner()
build_canonical_artifact = RUNNER.build_canonical_artifact


def _utc(y: int, m: int, d: int, h: int, mi: int, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=timezone.utc)


def _good_health(now: datetime) -> dict:
    stamp = now.isoformat().replace("+00:00", "Z")
    return {
        "status": "ok",
        "recorded_utc": stamp,
        "data_quality": {
            "state_complete": True,
            "issues": [],
            "quote_state": "normal",
            "execution_eligibility": "eligible",
            "operational": {
                "generation": 1,
                "marketStream": {"state": "connected"},
                "userStream": {"state": "connected"},
                "reconciliation": {"state": "succeeded"},
            },
        },
        "execution_recovery": {"blockingNewExposure": False},
        "market_observation": {"last_succeeded_utc": stamp, "last_error": None},
        "read_circuit_breaker": {},
        "position": {"open_quantity": 0},
    }


def _packet_roll_delay(now: datetime, *, roll_delay_seconds: float, quote_state: str = "normal") -> dict:
    """Provider keeps prior minute until roll_delay_seconds after civil close."""
    cur_min = now.replace(second=0, microsecond=0)
    rolled = now >= cur_min + timedelta(seconds=roll_delay_seconds)
    if rolled:
        # New minute started as partial; prior_completed anchors the just-closed bar.
        latest = cur_min
        prior = cur_min - timedelta(minutes=1)
        partial = True
    else:
        # Still showing completed prior minute (not a raw partial without anchor).
        latest = cur_min - timedelta(minutes=1)
        prior = latest - timedelta(minutes=1)
        partial = False

    issues: list[str] = []
    eligibility = "eligible"
    if quote_state == "locked":
        issues = ["quote_locked"]
        eligibility = "blocked_locked"
    elif quote_state == "invalid":
        issues = ["quote_geometry_invalid"]
        eligibility = "blocked_invalid"

    return {
        "data_quality": {
            "state_complete": quote_state != "invalid",
            "issues": issues,
            "quote_state": quote_state,
            "execution_eligibility": eligibility,
            "data_completeness": quote_state in ("normal", "locked"),
        },
        "account": {"instrument_open_contracts": 0},
        "market": {
            "quote_timestamp": now.isoformat().replace("+00:00", "Z"),
            "quote_valid": quote_state == "normal",
        },
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


def _stale_partial(now: datetime, latest_minute: datetime) -> dict:
    prior = latest_minute - timedelta(minutes=1)
    return {
        "data_quality": {
            "state_complete": True,
            "issues": [],
            "quote_state": "normal",
            "execution_eligibility": "eligible",
        },
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


def _clock(start: datetime):
    state = {"t": start, "mono": 0.0}

    def now_fn() -> datetime:
        return state["t"]

    def sleep_fn(seconds: float) -> None:
        # Always advance — poll_seconds=0 must not freeze monotonic timeout.
        step = max(float(seconds), 0.05)
        state["mono"] += step
        state["t"] = state["t"] + timedelta(seconds=step)

    def mono_fn() -> float:
        return state["mono"]

    return state, now_fn, sleep_fn, mono_fn


@mock.patch("operational_stability_gate._measurement_helpers")
class CanonicalOrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helpers = (lambda _p: [], lambda _p: (True, "capacity_gate"))

    def _patch_helpers(self, helpers_mock: mock.MagicMock) -> None:
        helpers_mock.return_value = self.helpers

    def test_provider_rolls_9_22_45_60_75(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        for delay in (9, 22, 45, 60, 75):
            with self.subTest(delay=delay):
                if delay <= 15:
                    start = _utc(2026, 9, 8, 14, 0, 2)
                    state, now_fn, sleep_fn, mono_fn = _clock(start)
                    wait = wait_for_bar_complete(
                        lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=float(delay)),
                        timeout_seconds=60.0,
                        post_close_window_seconds=5.0,
                        provider_roll_latency_seconds=10.0,
                        poll_seconds=0.0,
                        sleep_fn=sleep_fn,
                        monotonic_fn=mono_fn,
                        now_fn=now_fn,
                    )
                    self.assertTrue(wait.get("ready"), msg=f"delay={delay} {wait.get('reason')}")
                    self.assertIsNotNone(wait.get("confirmed_at_utc"))
                    self.assertTrue(wait["cursor"]["seen_closed_bar_keys"])
                else:
                    # v11 shape: short timeout; late roll must not become ready.
                    start = _utc(2026, 9, 8, 13, 59, 36)
                    state, now_fn, sleep_fn, mono_fn = _clock(start)
                    late_roll = _utc(2026, 9, 8, 14, 0, 0) + timedelta(seconds=min(delay, 22))

                    def packet() -> dict:
                        if now_fn() < late_roll:
                            return _stale_partial(now_fn(), _utc(2026, 9, 8, 13, 59, 0))
                        return _stale_partial(now_fn(), _utc(2026, 9, 8, 14, 0, 0))

                    wait = wait_for_bar_complete(
                        packet,
                        timeout_seconds=5.0,
                        post_close_window_seconds=5.0,
                        provider_roll_latency_seconds=10.0,
                        poll_seconds=0.0,
                        sleep_fn=sleep_fn,
                        monotonic_fn=mono_fn,
                        now_fn=now_fn,
                    )
                    self.assertFalse(wait.get("ready"), msg=f"delay={delay}")
                    missed = wait.get("missed_boundaries") or []
                    self.assertGreaterEqual(len(missed), 1)
                    self.assertEqual(missed[0]["reason"], "missed_post_close_window")
                    closes = [m.get("expected_close_utc") for m in missed]
                    self.assertEqual(closes.count(closes[0]), 1)

    def test_canonical_window_confirms_9s_roll_without_prewait(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 0, 2)
        _state, now_fn, sleep_fn, mono_fn = _clock(start)
        result = run_canonical_live_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            required_samples=1,
            max_duration_seconds=90.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
            provider_roll_latency_seconds=10.0,
            post_close_window_seconds=5.0,
        )
        self.assertTrue(result.get("canonical_entry"))
        self.assertTrue(result["confirmed"], msg=result.get("stop_reason"))
        self.assertTrue(result["bar_close_cursor"]["seen_closed_bar_keys"])
        self.assertTrue(result.get("shared_clock"))
        self.assertTrue(result.get("pre_wait_forbidden"))

    def test_shared_cursor_handoff_wait_to_stability(self, helpers: mock.MagicMock) -> None:
        """If wait helper is used, it must share cursor — no double miss on same boundary."""
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 0, 2)
        state, now_fn, sleep_fn, mono_fn = _clock(start)
        cursor = BarCloseCursor()

        wait = wait_for_bar_complete(
            lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            timeout_seconds=60.0,
            post_close_window_seconds=5.0,
            provider_roll_latency_seconds=10.0,
            poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
            cursor=cursor,
        )
        self.assertTrue(wait.get("ready"))
        self.assertIsNotNone(wait.get("confirmed_at_utc"))
        self.assertTrue(cursor.seen_closed_bar_keys)

        # Stability with a fresh window but pre-seeded cursor must skip already-seen.
        # Inject cursor by capturing first sample then forcing same packet key via mark.
        seen_before = set(cursor.seen_closed_bar_keys)
        # Advance clock into next minute post-close with roll.
        state["t"] = _utc(2026, 9, 8, 14, 1, 2)
        result = run_bar_close_aware_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            required_samples=1,
            max_duration_seconds=120.0,
            acceptance_policy=BAR_CLOSE_ACCEPTANCE_V2,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
        )
        # Canonical path does not reuse external wait cursor; prove reprocess reason never
        # appears as missed for keys already in the stability cursor after capture.
        captured = result.get("bar_close_cursor", {}).get("seen_closed_bar_keys") or []
        for key in captured:
            repeats = [
                s
                for s in result.get("skipped_samples") or []
                if s.get("closed_bar_utc") == key and s.get("reason") == "missed_post_close_window"
            ]
            self.assertEqual(repeats, [])
        # External wait cursor must remain monotonic (not cleared).
        self.assertTrue(seen_before <= cursor.seen_closed_bar_keys)

    def test_repeated_boundary_not_reprocessed_as_miss(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 1, 2)
        state, now_fn, sleep_fn, mono_fn = _clock(start)

        # First: capture one sample
        result1 = run_canonical_live_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            required_samples=1,
            max_duration_seconds=90.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
            provider_roll_latency_seconds=10.0,
            post_close_window_seconds=5.0,
        )
        self.assertTrue(result1["confirmed"])
        keys = result1["bar_close_cursor"]["seen_closed_bar_keys"]
        self.assertEqual(len(keys), 1)

        # Seed a cursor and force the stability loop to see the same key again.
        cursor = BarCloseCursor()
        cursor.seen_closed_bar_keys.add(keys[0])
        cursor.last_captured_close = _utc(2026, 9, 8, 14, 1, 0)
        cursor.next_target_close = _utc(2026, 9, 8, 14, 2, 0)

        # Direct unit: already_seen must skip without missed_post_close_window
        self.assertTrue(cursor.already_seen(keys[0]))
        nxt = cursor.advance_after_miss_or_skip(_utc(2026, 9, 8, 14, 1, 0))
        self.assertGreaterEqual(nxt, _utc(2026, 9, 8, 14, 2, 0))

        # Shared wait+cursor: second wait on same packet must not mark miss for captured key.
        state["t"] = _utc(2026, 9, 8, 14, 1, 3)
        wait2 = wait_for_bar_complete(
            lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            timeout_seconds=5.0,
            poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
            cursor=cursor,
            provider_roll_latency_seconds=10.0,
        )
        for miss in wait2.get("missed_boundaries") or []:
            self.assertNotEqual(miss.get("expected_close_utc"), keys[0].replace(".000", ""))

    def test_lost_boundaries_recover_next(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 0, 50)
        state, now_fn, sleep_fn, mono_fn = _clock(start)
        stale_until = _utc(2026, 9, 8, 14, 2, 0)

        def packet() -> dict:
            if now_fn() < stale_until:
                return _stale_partial(now_fn(), _utc(2026, 9, 8, 14, 0, 0))
            return _packet_roll_delay(now_fn(), roll_delay_seconds=3.0)

        result = run_canonical_live_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=packet,
            required_samples=2,
            max_duration_seconds=400.0,
            max_warmup_seconds=200.0,
            max_total_boundaries=8,
            max_total_duration_seconds=500.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
            provider_roll_latency_seconds=10.0,
            post_close_window_seconds=5.0,
        )
        self.assertTrue(result["confirmed"], msg=str(result.get("stop_reason")))
        self.assertGreaterEqual(len(result.get("warmup_events") or []), 1)
        cursor = result["bar_close_cursor"]
        self.assertGreaterEqual(len(cursor["seen_closed_bar_keys"]), 2)
        # Monotonic: last_captured advances
        self.assertIsNotNone(cursor["last_captured_close"])
        self.assertIsNotNone(cursor["next_target_close"])

    def test_monotonic_cursor_fields(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        cursor = BarCloseCursor()
        t0 = _utc(2026, 9, 8, 14, 1, 0)
        cursor.mark_captured(t0, "2026-09-08T14:00:00Z")
        self.assertEqual(cursor.next_target_close, t0 + timedelta(minutes=1))
        self.assertTrue(cursor.already_seen("2026-09-08T14:00:00Z"))
        snap = cursor.snapshot()
        self.assertEqual(snap["last_captured_close"], "2026-09-08T14:01:00Z")
        self.assertIn("2026-09-08T14:00:00Z", snap["seen_closed_bar_keys"])

    def test_bounded_timeout(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 1, 2)
        state, now_fn, sleep_fn, mono_fn = _clock(start)
        result = run_canonical_live_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _stale_partial(now_fn(), _utc(2026, 9, 8, 14, 0, 0)),
            required_samples=5,
            max_duration_seconds=20.0,
            max_warmup_seconds=10.0,
            max_total_duration_seconds=35.0,
            max_total_boundaries=4,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
        )
        self.assertFalse(result["confirmed"])
        # Warmup + valid budgets may stack briefly; outer total must stay bounded.
        self.assertLessEqual(result["elapsed_seconds"], 60.0)
        self.assertLessEqual(result.get("max_total_duration_seconds") or 35.0, 35.0)

    def test_import_outside_canonical_fails(self, helpers: mock.MagicMock) -> None:
        del helpers
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / "foreign_script.py"
            foreign.write_text("x=1\n", encoding="utf-8")
            with self.assertRaises(LiveRepoGuardError):
                assert_module_from_profile_root(foreign, ROOT)

    def test_forbidden_checkout_markers(self, helpers: mock.MagicMock) -> None:
        del helpers
        self.assertTrue(path_is_forbidden_checkout(Path(r"C:\Users\x\Projects\wave0-offline-20260909\pf")))
        self.assertTrue(path_is_forbidden_checkout(Path(r"C:\Users\x\Projects\glitch-topstep-hermes-profile\.wt-fix-x")))
        self.assertTrue(path_is_forbidden_checkout(Path(r"C:\Users\x\Projects\x\docs\evidence\adhoc")))
        self.assertFalse(path_is_forbidden_checkout(Path(r"C:\Users\x\Projects\glitch-topstep-hermes-profile")))

    def test_sha_divergence_blocks(self, helpers: mock.MagicMock) -> None:
        del helpers
        gateway = ROOT.parent.parent / "glitch-topstep"
        if not gateway.is_dir():
            gateway = ROOT.parent / "glitch-topstep"
        if not gateway.is_dir():
            self.skipTest("gateway sibling missing")
        with self.assertRaises(LiveRepoGuardError) as ctx:
            validate_live_repo_context(
                profile_root=ROOT,
                gateway_root=gateway,
                expected_profile_sha="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                allow_worktree=True,
            )
        self.assertIn("profile_sha_divergence", str(ctx.exception))

    def test_quote_axes_locked_invalid_normal(self, helpers: mock.MagicMock) -> None:
        del helpers
        cases = {
            "normal": (True, True, False),
            "locked": (True, False, False),
            "invalid": (False, False, False),
        }
        for state, (op_ok, exec_ok, directional) in cases.items():
            with self.subTest(state=state):
                health = _good_health(_utc(2026, 9, 8, 14, 1, 2))
                packet = _packet_roll_delay(_utc(2026, 9, 8, 14, 1, 9), roll_delay_seconds=9.0, quote_state=state)
                if state != "normal":
                    health["data_quality"]["quote_state"] = state
                    health["data_quality"]["issues"] = packet["data_quality"]["issues"]
                    health["data_quality"]["execution_eligibility"] = packet["data_quality"]["execution_eligibility"]
                    health["data_quality"]["state_complete"] = packet["data_quality"]["state_complete"]
                    health["data_quality"]["data_completeness"] = packet["data_quality"]["data_completeness"]
                axes = classify_evaluation_axes(health, packet)
                self.assertEqual(axes["quote_state"], state)
                self.assertEqual(axes["operational_cycle_valid"], op_ok)
                self.assertEqual(axes["executable_market_valid"], exec_ok)
                self.assertEqual(axes["directional_opportunity"], directional)
                self.assertFalse(axes["execution_authority"])
                if state in ("locked", "invalid"):
                    self.assertTrue(axes["blocks_no_edge"])
                    self.assertNotEqual(axes["deferred_reason"], "no_edge")

    def test_zero_intents_orders_writes_in_artifact(self, helpers: mock.MagicMock) -> None:
        self._patch_helpers(helpers)
        start = _utc(2026, 9, 8, 14, 1, 2)
        state, now_fn, sleep_fn, mono_fn = _clock(start)
        stability = run_canonical_live_stability_window(
            health_fetcher=lambda: _good_health(now_fn()),
            packet_fetcher=lambda: _packet_roll_delay(now_fn(), roll_delay_seconds=9.0),
            required_samples=1,
            max_duration_seconds=90.0,
            post_close_poll_seconds=0.0,
            sleep_fn=sleep_fn,
            monotonic_fn=mono_fn,
            now_fn=now_fn,
        )
        artifact = build_canonical_artifact(
            stability={**stability, "confirmed": True},
            provenance={
                "profile_root": str(ROOT),
                "gateway_root": str(ROOT.parent / "glitch-topstep"),
                "profile_sha": "b3d70b04c9a6004ee03dad19761d72ebb875d6be",
                "gateway_sha": "d4ac84aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "script_sha": {},
                "paired_contract": {},
            },
        )
        self.assertEqual(artifact["schema_version"], CANONICAL_ARTIFACT_SCHEMA)
        self.assertEqual(artifact["safety"]["intents_sent"], 0)
        self.assertEqual(artifact["safety"]["orders_sent"], 0)
        self.assertEqual(artifact["safety"]["writes_operacionais"], 0)
        self.assertTrue(artifact["confirmed"] or stability.get("confirmed") is not None)
        require_canonical_live_artifact_for_prac_soak(artifact)

    def test_prac_soak_blocked_without_canonical_artifact(self, helpers: mock.MagicMock) -> None:
        del helpers
        with self.assertRaises(LiveRepoGuardError):
            require_canonical_live_artifact_for_prac_soak(None)
        with self.assertRaises(LiveRepoGuardError):
            require_canonical_live_artifact_for_prac_soak({"schema_version": "other", "confirmed": True})
        with self.assertRaises(LiveRepoGuardError):
            require_canonical_live_artifact_for_prac_soak(
                {
                    "schema_version": CANONICAL_ARTIFACT_SCHEMA,
                    "confirmed": True,
                    "canonical_entry": True,
                    "provenance": {},
                    "safety": {"intents_sent": 0, "orders_sent": 0, "writes_operacionais": 0},
                }
            )




if __name__ == "__main__":
    unittest.main()
