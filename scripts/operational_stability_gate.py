"""Bounded operational stability window — bar-close-aware sampling, read-only."""

from __future__ import annotations

import json
import importlib.util
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from common import parse_utc, utc_now

GATE_SCHEMA = "glitch.topstep.operational_stability_gate.v1"
BLOCKED_CLASSIFICATION = "blocked_operational_instability"
BLOCKED_BAR_CLOSE_WINDOW = "blocked_bar_close_window"

DEFAULT_REQUIRED_SAMPLES = 5
DEFAULT_MAX_DURATION_SECONDS = 600.0  # 10 minutes bounded (valid-sample window only)
DEFAULT_POLL_INTERVAL_SECONDS = 30.0  # legacy poll mode only
DEFAULT_MAX_WARMUP_SECONDS = 120.0
DEFAULT_POST_CLOSE_WINDOW_SECONDS = 5.0
DEFAULT_PROVIDER_ROLL_LATENCY_SECONDS = 10.0
DEFAULT_HEALTH_FRESHNESS_SECONDS = 90.0
DEFAULT_MARKET_OBS_FRESHNESS_SECONDS = 120.0
MINUTE_MS = 60_000

# Operational stability treats these optional packet issues as blocking — degraded
# cache fallback must not count as a valid sample.
PACKET_OPERATIONAL_BLOCKING_OPTIONAL_ISSUES = frozenset({
    "market_observation_refresh_timeout",
})

_SCRIPTS = Path(__file__).resolve().parent


def resolve_post_close_window_seconds() -> float:
    """Explicit operator config — default remains 5s; never silently widened in code."""
    raw = os.environ.get("GLITCH_OPERATIONAL_POST_CLOSE_WINDOW_SECONDS", "").strip()
    if not raw:
        return DEFAULT_POST_CLOSE_WINDOW_SECONDS
    return float(raw)


def resolve_provider_roll_latency_seconds() -> float:
    """Grace after clock close while provider roll lands; anchors on prior_completed_bar."""
    raw = os.environ.get("GLITCH_PROVIDER_ROLL_LATENCY_SECONDS", "").strip()
    if not raw:
        return DEFAULT_PROVIDER_ROLL_LATENCY_SECONDS
    return float(raw)


def _measurement_helpers() -> tuple[Any, Any]:
    spec = importlib.util.spec_from_file_location(
        "evaluation_measurement_ready", _SCRIPTS / "evaluation-measurement-ready.py"
    )
    if not spec or not spec.loader:
        raise ImportError("evaluation-measurement-ready.py unavailable")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._bar_issues, mod._capacity_ok


@dataclass
class StabilitySampleVerdict:
    ok: bool
    reasons: list[str]
    detail: dict[str, Any]


@dataclass
class BarCloseContext:
    latest_bar_utc: str
    expected_close_utc: str
    latest_bar_partial: bool
    prior_completed_bar_utc: str | None
    bar_age_ms: int | None
    source: str | None


def _age_seconds(now: datetime, ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        return max(0.0, (now - parse_utc(str(ts))).total_seconds())
    except (TypeError, ValueError):
        return None


def _tf1(packet: dict[str, Any] | None) -> dict[str, Any] | None:
    if not packet:
        return None
    mo = packet.get("market_observation") if isinstance(packet.get("market_observation"), dict) else {}
    obs = mo.get("observation") if isinstance(mo.get("observation"), dict) else {}
    for tf in obs.get("timeframes") or []:
        if isinstance(tf, dict) and tf.get("timeframe_minutes") == 1:
            return tf
    return None


def extract_bar_close_context(packet: dict[str, Any] | None, *, now: datetime | None = None) -> BarCloseContext | None:
    """Derive expected bar close from packet — does not fabricate bars."""
    tf1 = _tf1(packet)
    if not tf1 or not tf1.get("latest_bar_utc"):
        return None
    now_dt = now or datetime.now(timezone.utc)
    latest = str(tf1["latest_bar_utc"])
    bar_open = parse_utc(latest.replace("+00:00", "Z"))
    expected_close = bar_open + timedelta(minutes=1)
    bar_age_ms = int(max(0.0, (now_dt - bar_open).total_seconds()) * 1000)
    prior = tf1.get("prior_completed_bar")
    prior_utc = prior.get("timestamp") if isinstance(prior, dict) else None
    mo = packet.get("market_observation") if isinstance(packet.get("market_observation"), dict) else {}
    obs = mo.get("observation") if isinstance(mo.get("observation"), dict) else {}
    return BarCloseContext(
        latest_bar_utc=latest,
        expected_close_utc=expected_close.isoformat().replace("+00:00", "Z"),
        latest_bar_partial=bool(tf1.get("latest_bar_partial")),
        prior_completed_bar_utc=prior_utc,
        bar_age_ms=bar_age_ms,
        source=str(obs.get("source") or mo.get("source") or "") or None,
    )


def _close_reference_utc(ctx: BarCloseContext) -> str:
    """Bar whose close we wait for — prior bar when latest already rolled partial."""
    if ctx.latest_bar_partial and ctx.prior_completed_bar_utc:
        return ctx.prior_completed_bar_utc
    return ctx.latest_bar_utc


def expected_close_for_context(ctx: BarCloseContext) -> datetime:
    ref = parse_utc(_close_reference_utc(ctx).replace("+00:00", "Z"))
    assert ref is not None
    return ref + timedelta(minutes=1)


def is_post_close_sample(
    sample_utc: datetime,
    ctx: BarCloseContext,
    *,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
    provider_roll_latency_seconds: float | None = None,
) -> bool:
    close_dt = expected_close_for_context(ctx)
    strict_end = close_dt + timedelta(seconds=post_close_window_seconds)
    if close_dt <= sample_utc <= strict_end:
        return True
    roll_latency = (
        provider_roll_latency_seconds
        if provider_roll_latency_seconds is not None
        else resolve_provider_roll_latency_seconds()
    )
    # ponytail: provider roll often lands after clock close — anchor on prior_completed_bar
    if (
        roll_latency > 0
        and ctx.latest_bar_partial
        and ctx.prior_completed_bar_utc
        and sample_utc > strict_end
    ):
        roll_end = close_dt + timedelta(seconds=post_close_window_seconds + roll_latency)
        return sample_utc <= roll_end
    return False


def _circuit_breaker_closed(health: dict[str, Any]) -> tuple[bool, str]:
    cb = health.get("read_circuit_breaker")
    if not isinstance(cb, dict):
        return True, "absent"
    for key in ("bars", "quotes", "orders"):
        section = cb.get(key)
        if isinstance(section, dict) and section.get("open") is True:
            return False, f"{key}_open"
    if cb.get("open") is True:
        return False, "aggregate_open"
    return True, "closed"


def _market_observation_fresh(health: dict[str, Any], *, max_age_s: float, now: datetime) -> tuple[bool, str]:
    mo = health.get("market_observation")
    if not isinstance(mo, dict):
        return False, "market_observation_missing"
    if mo.get("last_error"):
        return False, f"last_error:{mo.get('last_error')}"
    age = _age_seconds(now, mo.get("last_succeeded_utc"))
    if age is None:
        return False, "last_succeeded_utc_missing"
    if age > max_age_s:
        return False, f"stale_{int(age)}s"
    return True, "fresh"


def _account_flat(health: dict[str, Any], packet: dict[str, Any] | None) -> tuple[bool, int | None]:
    if packet:
        account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
        open_qty = account.get("instrument_open_contracts")
        if open_qty is not None:
            try:
                qty = int(open_qty)
                return qty == 0, qty
            except (TypeError, ValueError):
                pass
    pos = health.get("position") if isinstance(health.get("position"), dict) else {}
    open_qty = pos.get("open_quantity") or pos.get("instrument_open_contracts")
    if open_qty is not None:
        try:
            qty = int(open_qty)
            return qty == 0, qty
        except (TypeError, ValueError):
            pass
    inv = health.get("invariant_metrics") if isinstance(health.get("invariant_metrics"), dict) else {}
    open_qty = inv.get("open_quantity")
    if open_qty is not None:
        try:
            qty = int(open_qty)
            return qty == 0, qty
        except (TypeError, ValueError):
            pass
    return True, None


def evaluate_operational_stability_sample(
    *,
    health: dict[str, Any],
    packet: dict[str, Any] | None = None,
    fetched_utc: str | None = None,
    health_freshness_seconds: float = DEFAULT_HEALTH_FRESHNESS_SECONDS,
    market_obs_freshness_seconds: float = DEFAULT_MARKET_OBS_FRESHNESS_SECONDS,
    now: datetime | None = None,
    require_closed_bar: bool = False,
    bar_close_context: BarCloseContext | None = None,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
    provider_roll_latency_seconds: float | None = None,
) -> StabilitySampleVerdict:
    """Single-sample gate — records health/packet separately; never masks health incompleteness."""
    reasons: list[str] = []
    now_dt = now or datetime.now(timezone.utc)
    sample_utc = fetched_utc or utc_now()
    try:
        sample_dt = parse_utc(sample_utc.replace("+00:00", "Z"))
    except (TypeError, ValueError):
        sample_dt = now_dt

    health_dq = health.get("data_quality") if isinstance(health.get("data_quality"), dict) else {}
    health_sc = health_dq.get("state_complete")
    health_issues = sorted(health_dq.get("issues") or [])
    packet_dq = (packet or {}).get("data_quality") if isinstance((packet or {}).get("data_quality"), dict) else {}
    packet_sc = packet_dq.get("state_complete") if packet else None
    packet_issues = sorted(packet_dq.get("issues") or []) if packet else []
    packet_optional_issues = sorted(packet_dq.get("optional_issues") or []) if packet else []

    detail: dict[str, Any] = {
        "status": health.get("status"),
        "health_state_complete": health_sc,
        "packet_state_complete": packet_sc,
        "state_complete_divergence": (
            packet is not None and health_sc is not packet_sc
        ),
        "health_issues": health_issues,
        "packet_issues": packet_issues,
        "packet_optional_issues": packet_optional_issues,
        "account_state_stale": (
            "account_state_stale" in health_issues or "account_state_stale" in packet_issues
        ),
        "fetched_utc": sample_utc,
    }

    recorded = health.get("recorded_utc")
    health_age = _age_seconds(now_dt, str(recorded) if recorded else sample_utc)
    detail["health_age_seconds"] = health_age
    if health_age is None or health_age > health_freshness_seconds:
        reasons.append("health_stale")

    if str(health.get("status") or "") != "ok":
        reasons.append(f"status_{health.get('status') or 'unknown'}")

    if health_sc is not True:
        reasons.append("health_state_complete_false")
    if packet is not None and packet_sc is not True:
        reasons.append("packet_state_complete_false")
    if packet is not None and health_sc is not packet_sc:
        reasons.append("health_packet_state_complete_divergence")
    if "market_observation_stale" in packet_issues:
        reasons.append("packet_market_observation_stale")
    for issue in PACKET_OPERATIONAL_BLOCKING_OPTIONAL_ISSUES:
        if issue in packet_optional_issues:
            reasons.append(f"packet_optional_{issue}")
    if "quote_geometry_invalid" in packet_issues:
        reasons.append("packet_quote_geometry_invalid")
    if "account_state_stale" in health_issues:
        reasons.append("account_state_stale")

    cb_ok, cb_reason = _circuit_breaker_closed(health)
    detail["circuit_breaker"] = cb_reason
    if not cb_ok:
        reasons.append(f"circuit_breaker_{cb_reason}")

    mo_ok, mo_reason = _market_observation_fresh(
        health, max_age_s=market_obs_freshness_seconds, now=now_dt
    )
    detail["market_observation"] = mo_reason
    if not mo_ok:
        reasons.append(f"market_observation_{mo_reason}")

    recovery = health.get("execution_recovery") if isinstance(health.get("execution_recovery"), dict) else {}
    if recovery.get("blockingNewExposure") is True:
        reasons.append("recovery_blocked")
    legacy_recovery = health.get("recovery") if isinstance(health.get("recovery"), dict) else {}
    if legacy_recovery.get("active") is True:
        reasons.append("recovery_active")

    flat_ok, open_qty = _account_flat(health, packet)
    detail["account_open_contracts"] = open_qty
    if not flat_ok:
        reasons.append("account_not_flat")

    ctx = bar_close_context or (extract_bar_close_context(packet, now=sample_dt) if packet else None)
    if ctx is not None:
        detail["bar_close"] = {
            "sample_utc": sample_utc,
            "latest_bar_utc": ctx.latest_bar_utc,
            "expected_close_utc": ctx.expected_close_utc,
            "bar_age_ms": ctx.bar_age_ms,
            "partial_flag": ctx.latest_bar_partial,
            "prior_completed_bar_utc": ctx.prior_completed_bar_utc,
            "source": ctx.source,
        }

    if packet is not None:
        bar_issues_fn, capacity_ok_fn = _measurement_helpers()
        bar_issues = bar_issues_fn(packet)
        if "bar_1m_partial" in bar_issues:
            reasons.append("bar_1m_partial")
        if "bar_1m_lag" in bar_issues:
            reasons.append("bar_1m_lag")
        cap_ok, cap_reason = capacity_ok_fn(packet)
        detail["capacity"] = cap_reason
        if not cap_ok:
            reasons.append(f"capacity_{cap_reason}")

    if require_closed_bar:
        if ctx is None:
            reasons.append("bar_close_context_missing")
        else:
            close_ref = _close_reference_utc(ctx)
            detail["bar_close"]["close_reference_utc"] = close_ref
            detail["bar_close"]["expected_close_utc"] = (
                expected_close_for_context(ctx).isoformat().replace("+00:00", "Z")
            )
            if not is_post_close_sample(
                sample_dt,
                ctx,
                post_close_window_seconds=post_close_window_seconds,
                provider_roll_latency_seconds=provider_roll_latency_seconds,
            ):
                reasons.append("sample_before_bar_close_window")
            elif not ctx.latest_bar_partial:
                pass  # completed latest bar
            elif not ctx.prior_completed_bar_utc:
                reasons.append("bar_1m_partial")

    degraded_signal = str(health.get("status") or "") == "degraded" or "degraded" in str(
        health.get("gateway_mode") or ""
    ).lower()
    if degraded_signal:
        reasons.append("degraded")

    if (
        require_closed_bar
        and ctx
        and is_post_close_sample(
            sample_dt,
            ctx,
            post_close_window_seconds=post_close_window_seconds,
            provider_roll_latency_seconds=provider_roll_latency_seconds,
        )
        and ctx.latest_bar_partial
        and ctx.prior_completed_bar_utc
    ):
        reasons = [r for r in reasons if r != "bar_1m_partial"]

    return StabilitySampleVerdict(ok=not reasons, reasons=sorted(set(reasons)), detail=detail)


def _sleep_until(
    target: datetime,
    *,
    sleep_fn: Callable[[float], None],
    now_fn: Callable[[], datetime],
    monotonic_fn: Callable[[], float],
    monotonic_deadline: float | None = None,
) -> bool:
    """Sleep until target UTC. Returns False if monotonic_deadline exceeded."""
    while True:
        if monotonic_deadline is not None and monotonic_fn() >= monotonic_deadline:
            return False
        remaining = (target - now_fn()).total_seconds()
        if remaining <= 0:
            return True
        step = min(1.0, remaining)
        sleep_fn(step)
        # ponytail: frozen now_fn (unit tests) must not spin forever
        if (target - now_fn()).total_seconds() >= remaining:
            return True


def _record_fetch_failure(
    bucket: list[dict[str, Any]],
    *,
    phase: str,
    endpoint: str,
    exc: Exception,
    expected_close_utc: str | None = None,
) -> None:
    row: dict[str, Any] = {
        "reason": "gateway_timeout" if "timeout" in str(exc).lower() else "gateway_fetch_error",
        "phase": phase,
        "endpoint": endpoint,
        "error": str(exc),
        "fetched_utc": utc_now(),
    }
    if expected_close_utc:
        row["expected_close_utc"] = expected_close_utc
    detail = getattr(exc, "detail", None)
    if detail:
        row["detail"] = detail
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict) and isinstance(parsed.get("attempts"), list):
                row["attempts"] = parsed["attempts"]
        except (TypeError, json.JSONDecodeError):
            pass
    bucket.append(row)


def _bar_roll_confirmed(initial: BarCloseContext, current: BarCloseContext) -> bool:
    """True when provider rolled bars after expected close (prior or latest advanced)."""
    if (
        current.prior_completed_bar_utc
        and current.prior_completed_bar_utc != initial.prior_completed_bar_utc
        and current.prior_completed_bar_utc >= _close_reference_utc(initial)
    ):
        return True
    if current.latest_bar_utc != initial.latest_bar_utc:
        try:
            rolled = parse_utc(current.latest_bar_utc.replace("+00:00", "Z"))
            ref_close = expected_close_for_context(initial)
            return rolled is not None and rolled >= ref_close - timedelta(minutes=1)
        except (TypeError, ValueError):
            return True
    return False


def _bar_wait_ready(
    ctx: BarCloseContext,
    now: datetime,
    *,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
) -> bool:
    """True when sample is in post-close window with closed-bar evidence — never raw partial alone."""
    if not is_post_close_sample(now, ctx, post_close_window_seconds=post_close_window_seconds):
        return False
    if not ctx.latest_bar_partial:
        return True
    return bool(ctx.prior_completed_bar_utc)


def wait_for_bar_complete(
    packet_fetcher: Callable[[], dict[str, Any]],
    *,
    timeout_seconds: float = 300.0,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
    poll_seconds: float = 0.25,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Wait until clock-aligned post-close window — does not poll for partial=false."""
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    started = monotonic_fn()
    deadline = started + timeout_seconds
    polls: list[dict[str, Any]] = []
    initial_ctx: BarCloseContext | None = None

    while monotonic_fn() < deadline:
        now = now_fn()
        try:
            packet = packet_fetcher()
        except Exception as exc:
            polls.append(
                {
                    "fetched_utc": now.isoformat().replace("+00:00", "Z"),
                    "error": str(exc),
                }
            )
            sleep_fn(poll_seconds)
            continue

        ctx = extract_bar_close_context(packet, now=now)
        poll_row: dict[str, Any] = {
            "fetched_utc": now.isoformat().replace("+00:00", "Z"),
            "latest_bar_utc": ctx.latest_bar_utc if ctx else None,
            "prior_completed_bar_utc": ctx.prior_completed_bar_utc if ctx else None,
            "latest_bar_partial": ctx.latest_bar_partial if ctx else None,
            "expected_close_utc": (
                expected_close_for_context(ctx).isoformat().replace("+00:00", "Z") if ctx else None
            ),
        }
        polls.append(poll_row)

        if ctx is None:
            sleep_fn(poll_seconds)
            continue

        if initial_ctx is None:
            initial_ctx = ctx

        expected_close = expected_close_for_context(ctx)
        window_end = expected_close + timedelta(seconds=post_close_window_seconds)

        if now < expected_close:
            if not _sleep_until(
                expected_close,
                sleep_fn=sleep_fn,
                now_fn=now_fn,
                monotonic_fn=monotonic_fn,
                monotonic_deadline=deadline,
            ):
                break
            now = now_fn()
            try:
                packet = packet_fetcher()
            except Exception as exc:
                polls.append(
                    {
                        "fetched_utc": now.isoformat().replace("+00:00", "Z"),
                        "error": str(exc),
                        "phase": "post_sleep",
                    }
                )
                sleep_fn(poll_seconds)
                continue
            ctx = extract_bar_close_context(packet, now=now)
            if ctx is None:
                sleep_fn(poll_seconds)
                continue
            expected_close = expected_close_for_context(ctx)
            window_end = expected_close + timedelta(seconds=post_close_window_seconds)
            poll_row = {
                "fetched_utc": now.isoformat().replace("+00:00", "Z"),
                "latest_bar_utc": ctx.latest_bar_utc,
                "prior_completed_bar_utc": ctx.prior_completed_bar_utc,
                "latest_bar_partial": ctx.latest_bar_partial,
                "expected_close_utc": expected_close.isoformat().replace("+00:00", "Z"),
                "phase": "post_sleep",
            }
            polls.append(poll_row)

        if _bar_wait_ready(ctx, now, post_close_window_seconds=post_close_window_seconds):
            return {
                "ready": True,
                "waited_seconds": round(monotonic_fn() - started, 2),
                "expected_close_utc": expected_close.isoformat().replace("+00:00", "Z"),
                "latest_bar_utc": ctx.latest_bar_utc,
                "prior_completed_bar_utc": ctx.prior_completed_bar_utc,
                "latest_bar_partial": ctx.latest_bar_partial,
                "close_reference_utc": _close_reference_utc(ctx),
                "polls": polls,
            }

        if initial_ctx and _bar_roll_confirmed(initial_ctx, ctx):
            return {
                "ready": True,
                "waited_seconds": round(monotonic_fn() - started, 2),
                "expected_close_utc": expected_close.isoformat().replace("+00:00", "Z"),
                "latest_bar_utc": ctx.latest_bar_utc,
                "prior_completed_bar_utc": ctx.prior_completed_bar_utc,
                "latest_bar_partial": ctx.latest_bar_partial,
                "close_reference_utc": _close_reference_utc(ctx),
                "bar_roll_confirmed": True,
                "polls": polls,
            }

        sleep_fn(poll_seconds)

    last = polls[-1] if polls else {}
    return {
        "ready": False,
        "reason": "bar_still_partial" if last.get("latest_bar_partial") else "bar_close_alignment_timeout",
        "waited_seconds": round(monotonic_fn() - started, 2),
        "expected_close_utc": last.get("expected_close_utc"),
        "latest_bar_utc": last.get("latest_bar_utc"),
        "prior_completed_bar_utc": last.get("prior_completed_bar_utc"),
        "latest_bar_partial": last.get("latest_bar_partial"),
        "polls": polls,
    }


def run_bar_close_aware_stability_window(
    *,
    health_fetcher: Callable[[], dict[str, Any]],
    packet_fetcher: Callable[[], dict[str, Any]],
    required_samples: int = DEFAULT_REQUIRED_SAMPLES,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
    provider_roll_latency_seconds: float | None = None,
    post_close_poll_seconds: float = 0.25,
    max_warmup_seconds: float = DEFAULT_MAX_WARMUP_SECONDS,
    health_freshness_seconds: float = DEFAULT_HEALTH_FRESHNESS_SECONDS,
    market_obs_freshness_seconds: float = DEFAULT_MARKET_OBS_FRESHNESS_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    now_fn: Callable[[], datetime] | None = None,
    lease_checker: Callable[[], tuple[bool, str | None]] | None = None,
) -> dict[str, Any]:
    """Wait for bar closes; sample only in post-close window; one valid sample per close.

    Warmup (missed windows, sync to next close) does not consume the valid-sample budget.
    Valid-sample counting starts on the first eligible post-close window.
    """
    overall_started = monotonic_fn()
    samples: list[dict[str, Any]] = []
    warmup_events: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    gateway_timeouts: list[dict[str, Any]] = []
    seen_closed_bars: set[str] = set()
    stop_reason: str | None = None
    classification: str | None = None
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    counting_started = False
    counting_started_at_utc: str | None = None
    valid_window_started_mono: float | None = None
    valid_deadline: float | None = None
    roll_latency = (
        provider_roll_latency_seconds
        if provider_roll_latency_seconds is not None
        else resolve_provider_roll_latency_seconds()
    )

    if lease_checker is not None:
        lease_ok, lease_reason = lease_checker()
        if not lease_ok:
            return _finalize_window(
                started=overall_started,
                monotonic_fn=monotonic_fn,
                required_samples=required_samples,
                max_duration_seconds=max_duration_seconds,
                samples=samples,
                skipped=skipped,
                warmup_events=warmup_events,
                gateway_timeouts=gateway_timeouts,
                consecutive=len(samples),
                confirmed=False,
                stop_reason=lease_reason or "lease_occupied",
                classification=BLOCKED_CLASSIFICATION,
                sampling_mode="bar_close_aware",
                post_close_window_seconds=post_close_window_seconds,
                counting_started_at_utc=None,
            )

    def _valid_budget_exhausted() -> bool:
        return counting_started and valid_deadline is not None and monotonic_fn() >= valid_deadline

    def _begin_valid_window() -> None:
        nonlocal counting_started, valid_window_started_mono, valid_deadline, counting_started_at_utc
        if counting_started:
            return
        counting_started = True
        counting_started_at_utc = utc_now()
        valid_window_started_mono = monotonic_fn()
        valid_deadline = valid_window_started_mono + max_duration_seconds

    def _fetch_packet(phase: str, expected_close_utc: str | None = None) -> dict[str, Any] | None:
        try:
            return packet_fetcher()
        except Exception as exc:
            _record_fetch_failure(
                gateway_timeouts,
                phase=phase,
                endpoint="/packet",
                exc=exc,
                expected_close_utc=expected_close_utc,
            )
            return None

        nonlocal counting_started, valid_window_started_mono, valid_deadline, counting_started_at_utc
        if counting_started:
            return
        counting_started = True
        counting_started_at_utc = utc_now()
        valid_window_started_mono = monotonic_fn()
        valid_deadline = valid_window_started_mono + max_duration_seconds

    while len(samples) < required_samples and not _valid_budget_exhausted():
        if not counting_started and (monotonic_fn() - overall_started) > max_warmup_seconds:
            stop_reason = "warmup_sync_timeout"
            classification = BLOCKED_BAR_CLOSE_WINDOW
            break

        packet = _fetch_packet("warmup" if not counting_started else "valid", None)
        if packet is None:
            sleep_fn(0.5)
            continue

        ctx = extract_bar_close_context(packet, now=now_fn())
        if ctx is None:
            event = {"reason": "bar_close_context_missing", "phase": "warmup" if not counting_started else "valid", "fetched_utc": utc_now()}
            (warmup_events if not counting_started else skipped).append(event)
            sleep_fn(1.0)
            continue

        expected_close = expected_close_for_context(ctx)
        window_end = expected_close + timedelta(seconds=post_close_window_seconds)
        sample_window_end = window_end
        if roll_latency > 0 and ctx.latest_bar_partial and ctx.prior_completed_bar_utc:
            sample_window_end = expected_close + timedelta(
                seconds=post_close_window_seconds + roll_latency
            )
        now = now_fn()
        phase = "warmup" if not counting_started else "valid"
        expected_close_iso = expected_close.isoformat().replace("+00:00", "Z")

        if now < expected_close:
            if not _sleep_until(
                expected_close,
                sleep_fn=sleep_fn,
                now_fn=now_fn,
                monotonic_fn=monotonic_fn,
                monotonic_deadline=valid_deadline if counting_started else None,
            ):
                break
            now = now_fn()

        if not is_post_close_sample(
            now,
            ctx,
            post_close_window_seconds=post_close_window_seconds,
            provider_roll_latency_seconds=roll_latency,
        ):
            warmup_events.append(
                {
                    "reason": "missed_post_close_window",
                    "phase": phase,
                    "expected_close_utc": expected_close_iso,
                    "fetched_utc": now.isoformat().replace("+00:00", "Z"),
                    "latest_bar_utc": ctx.latest_bar_utc,
                    "bar_age_ms": ctx.bar_age_ms,
                    "provider_roll_latency_seconds": roll_latency,
                }
            )
            next_close = expected_close + timedelta(minutes=1)
            _sleep_until(
                next_close,
                sleep_fn=sleep_fn,
                now_fn=now_fn,
                monotonic_fn=monotonic_fn,
                monotonic_deadline=(
                    (overall_started + max_warmup_seconds)
                    if not counting_started
                    else valid_deadline
                ),
            )
            sleep_fn(1.0)
            continue

        if not counting_started:
            _begin_valid_window()

        captured = False
        while now_fn() <= sample_window_end and not captured and not _valid_budget_exhausted():
            sample_dt = now_fn()
            sample_utc = sample_dt.isoformat().replace("+00:00", "Z")
            try:
                health = health_fetcher()
            except Exception as exc:
                _record_fetch_failure(
                    gateway_timeouts,
                    phase="valid",
                    endpoint="/health",
                    exc=exc,
                    expected_close_utc=expected_close_iso,
                )
                sleep_fn(post_close_poll_seconds)
                continue

            packet = _fetch_packet("valid", expected_close_iso)
            if packet is None:
                sleep_fn(post_close_poll_seconds)
                continue

            ctx = extract_bar_close_context(packet, now=sample_dt)
            if ctx is None:
                sleep_fn(post_close_poll_seconds)
                continue

            closed_bar_key = _close_reference_utc(ctx)
            verdict = evaluate_operational_stability_sample(
                health=health,
                packet=packet,
                fetched_utc=sample_utc,
                health_freshness_seconds=health_freshness_seconds,
                market_obs_freshness_seconds=market_obs_freshness_seconds,
                now=sample_dt,
                require_closed_bar=True,
                bar_close_context=ctx,
                post_close_window_seconds=post_close_window_seconds,
                provider_roll_latency_seconds=roll_latency,
            )

            row = {
                "sample_index": len(samples),
                "fetched_utc": sample_utc,
                "ok": verdict.ok,
                "reasons": verdict.reasons,
                "detail": verdict.detail,
                "closed_bar_utc": closed_bar_key,
                "phase": "valid",
            }

            if not is_post_close_sample(
                sample_dt,
                ctx,
                post_close_window_seconds=post_close_window_seconds,
                provider_roll_latency_seconds=roll_latency,
            ):
                skipped.append({**row, "sample_index": None, "reason": "sample_before_bar_close_window"})
                sleep_fn(post_close_poll_seconds)
                continue

            if not verdict.ok:
                samples.append(row)
                stop_reason = verdict.reasons[0] if verdict.reasons else "sample_failed"
                if any(r.startswith("status_degraded") or r == "degraded" for r in verdict.reasons):
                    stop_reason = "degraded_during_window"
                elif "account_state_stale" in verdict.reasons:
                    stop_reason = "account_state_stale"
                elif "health_packet_state_complete_divergence" in verdict.reasons:
                    stop_reason = "health_packet_divergence"
                classification = BLOCKED_CLASSIFICATION
                break

            if closed_bar_key in seen_closed_bars:
                sleep_fn(post_close_poll_seconds)
                continue

            seen_closed_bars.add(closed_bar_key)
            row["sample_index"] = len(samples)
            samples.append(row)
            captured = True
            next_bar_close = expected_close + timedelta(minutes=1)
            _sleep_until(
                next_bar_close,
                sleep_fn=sleep_fn,
                now_fn=now_fn,
                monotonic_fn=monotonic_fn,
                monotonic_deadline=valid_deadline,
            )

        if stop_reason and classification == BLOCKED_CLASSIFICATION:
            break

        if not captured:
            skipped.append(
                {
                    "reason": "missed_post_close_window",
                    "phase": "valid",
                    "expected_close_utc": expected_close_iso,
                    "fetched_utc": utc_now(),
                }
            )

    confirmed = len(samples) >= required_samples and stop_reason is None
    if not confirmed and classification is None:
        if gateway_timeouts and stop_reason is None:
            stop_reason = "gateway_timeout_exhausted"
            classification = BLOCKED_CLASSIFICATION
        else:
            stop_reason = stop_reason or BLOCKED_BAR_CLOSE_WINDOW
            classification = BLOCKED_BAR_CLOSE_WINDOW

    counting_started_at_utc_out = counting_started_at_utc

    return _finalize_window(
        started=overall_started,
        monotonic_fn=monotonic_fn,
        required_samples=required_samples,
        max_duration_seconds=max_duration_seconds,
        samples=samples,
        skipped=skipped,
        warmup_events=warmup_events,
        gateway_timeouts=gateway_timeouts,
        consecutive=len(samples) if confirmed else len(samples),
        confirmed=confirmed,
        stop_reason=stop_reason,
        classification=None if confirmed else classification,
        sampling_mode="bar_close_aware",
        post_close_window_seconds=post_close_window_seconds,
        provider_roll_latency_seconds=roll_latency,
        counting_started_at_utc=counting_started_at_utc_out,
        valid_window_elapsed_seconds=(
            round(monotonic_fn() - valid_window_started_mono, 3)
            if valid_window_started_mono is not None
            else None
        ),
    )


def _finalize_window(
    *,
    started: float,
    monotonic_fn: Callable[[], float],
    required_samples: int,
    max_duration_seconds: float,
    samples: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    warmup_events: list[dict[str, Any]] | None = None,
    gateway_timeouts: list[dict[str, Any]] | None = None,
    consecutive: int,
    confirmed: bool,
    stop_reason: str | None,
    classification: str | None,
    sampling_mode: str,
    post_close_window_seconds: float | None = None,
    provider_roll_latency_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    counting_started_at_utc: str | None = None,
    valid_window_elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": GATE_SCHEMA,
        "generated_utc": utc_now(),
        "sampling_mode": sampling_mode,
        "confirmed": confirmed,
        "classification": classification,
        "required_consecutive_samples": required_samples,
        "consecutive_ok": consecutive,
        "max_duration_seconds": max_duration_seconds,
        "elapsed_seconds": round(monotonic_fn() - started, 3),
        "stop_reason": stop_reason,
        "samples": samples,
        "skipped_samples": skipped,
        "warmup_events": warmup_events or [],
        "gateway_timeouts": gateway_timeouts or [],
    }
    if counting_started_at_utc is not None:
        doc["counting_started_at_utc"] = counting_started_at_utc
    if valid_window_elapsed_seconds is not None:
        doc["valid_window_elapsed_seconds"] = valid_window_elapsed_seconds
    if post_close_window_seconds is not None:
        doc["post_close_window_seconds"] = post_close_window_seconds
    if provider_roll_latency_seconds is not None:
        doc["provider_roll_latency_seconds"] = provider_roll_latency_seconds
    if poll_interval_seconds is not None:
        doc["poll_interval_seconds"] = poll_interval_seconds
    return doc


def run_operational_stability_window(
    *,
    health_fetcher: Callable[[], dict[str, Any]],
    packet_fetcher: Callable[[], dict[str, Any]] | None = None,
    required_samples: int = DEFAULT_REQUIRED_SAMPLES,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    post_close_window_seconds: float = DEFAULT_POST_CLOSE_WINDOW_SECONDS,
    provider_roll_latency_seconds: float | None = None,
    health_freshness_seconds: float = DEFAULT_HEALTH_FRESHNESS_SECONDS,
    market_obs_freshness_seconds: float = DEFAULT_MARKET_OBS_FRESHNESS_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    now_fn: Callable[[], datetime] | None = None,
    bar_close_aware: bool = True,
    lease_checker: Callable[[], tuple[bool, str | None]] | None = None,
) -> dict[str, Any]:
    """Bounded stability window. Defaults to bar-close-aware when packet_fetcher is provided."""
    if bar_close_aware and packet_fetcher is not None:
        return run_bar_close_aware_stability_window(
            health_fetcher=health_fetcher,
            packet_fetcher=packet_fetcher,
            required_samples=required_samples,
            max_duration_seconds=max_duration_seconds,
            post_close_window_seconds=post_close_window_seconds,
            provider_roll_latency_seconds=provider_roll_latency_seconds,
            health_freshness_seconds=health_freshness_seconds,
            market_obs_freshness_seconds=market_obs_freshness_seconds,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
            now_fn=now_fn,
            lease_checker=lease_checker,
        )

    # ponytail: legacy fixed-interval poll retained for health-only callers/tests
    started = monotonic_fn()
    deadline = started + max_duration_seconds
    samples: list[dict[str, Any]] = []
    consecutive = 0
    stop_reason: str | None = None
    classification: str | None = None
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    while monotonic_fn() < deadline and consecutive < required_samples:
        fetched_utc = utc_now()
        try:
            health = health_fetcher()
        except Exception as exc:
            stop_reason = f"health_fetch_error:{exc}"
            classification = BLOCKED_CLASSIFICATION
            samples.append(
                {
                    "sample_index": len(samples),
                    "fetched_utc": fetched_utc,
                    "ok": False,
                    "reasons": [stop_reason],
                }
            )
            break

        packet = None
        packet_error: str | None = None
        if packet_fetcher is not None:
            try:
                packet = packet_fetcher()
            except Exception as exc:
                packet_error = str(exc)

        verdict = evaluate_operational_stability_sample(
            health=health,
            packet=packet,
            fetched_utc=fetched_utc,
            health_freshness_seconds=health_freshness_seconds,
            market_obs_freshness_seconds=market_obs_freshness_seconds,
            now=now_fn(),
        )
        if packet_error:
            verdict = StabilitySampleVerdict(
                ok=False,
                reasons=sorted(set(verdict.reasons + [f"packet_fetch_error:{packet_error}"])),
                detail={**verdict.detail, "packet_error": packet_error},
            )

        row = {
            "sample_index": len(samples),
            "fetched_utc": fetched_utc,
            "ok": verdict.ok,
            "reasons": verdict.reasons,
            "detail": verdict.detail,
        }
        samples.append(row)

        if not verdict.ok:
            if any(r.startswith("status_degraded") or r == "degraded" for r in verdict.reasons):
                stop_reason = "degraded_during_window"
            elif "state_complete_false" in verdict.reasons or "health_state_complete_false" in verdict.reasons:
                stop_reason = "state_incomplete_during_window"
            else:
                stop_reason = verdict.reasons[0] if verdict.reasons else "sample_failed"
            classification = BLOCKED_CLASSIFICATION
            consecutive = 0
            break

        consecutive += 1
        if consecutive < required_samples and monotonic_fn() < deadline:
            sleep_fn(max(0.0, poll_interval_seconds))

    confirmed = consecutive >= required_samples
    if not confirmed and classification is None:
        stop_reason = stop_reason or "stability_window_incomplete"
        classification = BLOCKED_CLASSIFICATION

    return _finalize_window(
        started=started,
        monotonic_fn=monotonic_fn,
        required_samples=required_samples,
        max_duration_seconds=max_duration_seconds,
        samples=samples,
        skipped=[],
        consecutive=consecutive,
        confirmed=confirmed,
        stop_reason=stop_reason,
        classification=None if confirmed else classification,
        sampling_mode="legacy_poll",
        poll_interval_seconds=poll_interval_seconds,
    )


def write_stability_artifact(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
