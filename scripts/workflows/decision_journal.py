"""Decision journal — single indexed writer over decisions JSONL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common import read_jsonl, read_optional_json, utc_now
from parity import (
    classify_delivery_result,
    classify_gateway_rejection,
    compute_nothing_counterfactual,
    frame_for_packet_id,
    review_change_condition,
    suggest_flat_abstention_classification,
)
from state_store import ProfileStateStore
from workflows.learning_journal import append_unique, stable_id


GATEWAY_COGNITIVE_REJECTION_ERRORS = frozenset({
    "move_stop_unavailable",
})


def is_gateway_cognitive_rejection(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    http_status = result.get("http_status")
    if isinstance(http_status, int) and 400 <= http_status < 500:
        return True
    body = result.get("body")
    if not isinstance(body, dict):
        return False
    message = str(body.get("message") or body.get("error") or "")
    if message in GATEWAY_COGNITIVE_REJECTION_ERRORS:
        return True
    return str(body.get("status") or "").lower() in {"rejected", "invalid"}


def _packet_is_flat(packet: dict[str, Any]) -> bool:
    account = packet.get("account")
    if not isinstance(account, dict):
        return True
    return int(account.get("instrument_open_contracts") or 0) == 0


def _price_observation(frame: dict[str, Any]) -> dict[str, Any] | None:
    packet = frame.get("packet") if isinstance(frame.get("packet"), dict) else None
    if packet is None:
        return None
    market = packet.get("market")
    if not isinstance(market, dict):
        return None
    try:
        close = float(market["last"])
        high = float(market.get("high", close))
        low = float(market.get("low", close))
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "minute_id": frame.get("minute_id"),
        "close": close,
        "high": high,
        "low": low,
    }


class DecisionJournal:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._store: ProfileStateStore | None = None

    @property
    def store(self) -> ProfileStateStore:
        if self._store is None:
            self._store = ProfileStateStore(self.root)
        return self._store

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def bootstrap(self, jsonl_path: Path | None = None) -> None:
        path = jsonl_path or self.root / "decisions.jsonl"
        self.store.bootstrap_decisions(path)

    def append(self, row: dict[str, Any], *, jsonl_path: Path | None = None) -> None:
        path = jsonl_path or self.root / "decisions.jsonl"
        self.store.append_decision(row, jsonl_path=path)

    def tail(self, limit: int) -> list[dict[str, Any]]:
        return self.store.tail_decisions(limit)

    def collect_decision_episodes(self, supervisor: Path) -> list[dict[str, Any]]:
        state_root = self.root
        output_path = supervisor / "decision-episodes.jsonl"
        existing = {
            str(row.get("intent_id")) for row in read_jsonl(output_path) if row.get("intent_id")
        }
        frames_root = state_root / "minute-frames"
        records: list[dict[str, Any]] = []
        seen_intents: set[str] = set()

        def enqueue(packet_id: str, intent: dict[str, Any]) -> None:
            nonlocal records
            receipt_path = state_root / "receipts" / f"{packet_id}.json"
            if not receipt_path.is_file():
                return
            receipt = read_optional_json(receipt_path)
            if not isinstance(receipt, dict):
                return
            if classify_delivery_result(
                receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
            ) == "transport_uncertain":
                return
            intent_id = str(intent.get("intent_id") or receipt.get("intent_id") or "")
            if not intent_id or intent_id in existing or intent_id in seen_intents:
                return
            frame = frame_for_packet_id(frames_root, packet_id)
            if frame is None:
                return
            minute_id = str(frame.get("minute_id") or "")
            if not minute_id:
                return
            future_paths = [
                path for path in sorted(frames_root.glob("*.json")) if path.stem > minute_id
            ][:5]
            if len(future_paths) < 5:
                return
            future: list[dict[str, Any]] = []
            for path in future_paths:
                observed = _price_observation(read_optional_json(path) or {})
                if observed is None:
                    future = []
                    break
                future.append(observed)
            if len(future) < 5:
                return
            packet = frame.get("packet")
            if not isinstance(packet, dict):
                return
            action = str(intent.get("action") or "")
            flat_nothing = action == "NOTHING" and _packet_is_flat(packet)
            relevant_failure = (
                action in {"ENTER_LONG", "ENTER_SHORT", "MOVE_STOP", "EXIT"}
                and is_gateway_cognitive_rejection(receipt.get("result"))
            )
            if not flat_nothing and not relevant_failure:
                return
            try:
                initial = float(packet["market"]["last"])
            except (KeyError, TypeError, ValueError):
                return
            forward_high = max(row["high"] for row in future)
            forward_low = min(row["low"] for row in future)
            account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
            contract = packet.get("contract") if isinstance(packet.get("contract"), dict) else {}
            delivery_result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
            record: dict[str, Any] = {
                "schema_version": "glitch.topstep.decision_episode.v1",
                "episode_id": stable_id("decision-episode", intent_id),
                "recorded_utc": utc_now(),
                "intent_id": intent_id,
                "packet_id": packet_id,
                "decision_utc": intent.get("created_utc") or receipt.get("recorded_utc"),
                "account": intent.get("account") or account.get("name"),
                "instrument": intent.get("instrument") or contract.get("symbol"),
                "action": action,
                "reason": intent.get("reason"),
                "decision_audit": intent.get("decision_audit"),
                "pre_decision_state": {
                    "position_contracts": account.get("instrument_open_contracts"),
                    "initial_price": initial,
                    "regime": packet.get("regime"),
                },
                "proposed_geometry": {
                    key: intent.get(key)
                    for key in (
                        "quantity",
                        "stop_loss",
                        "take_profit_1",
                        "take_profit_2",
                        "quantity_tp1",
                        "stop_loss_2",
                        "take_profit_3",
                        "quantity_tp2",
                        "stop_loss_3",
                    )
                    if key in intent
                },
                "delivery_result": delivery_result,
                "rejection_class": classify_gateway_rejection(delivery_result),
                "evidence_kind": "flat_nothing" if flat_nothing else "rejected_or_nonexecuted_intent",
                "forward_observation_count": len(future),
                "forward_observations": future,
                "forward_high": forward_high,
                "forward_low": forward_low,
                "forward_close": future[-1]["close"],
                "upward_excursion_points": forward_high - initial,
                "downward_excursion_points": initial - forward_low,
                "classification": None,
                "classification_hint": (
                    suggest_flat_abstention_classification(
                        initial_price=initial,
                        forward_high=forward_high,
                        forward_low=forward_low,
                        forward_close=future[-1]["close"],
                    )
                    if flat_nothing
                    else None
                ),
                "classification_owner": "hermes",
            }
            if flat_nothing:
                counterfactual = compute_nothing_counterfactual(
                    {
                        "action": action,
                        "contract": contract,
                        "decision_audit": intent.get("decision_audit"),
                        "packet": packet,
                        "pre_decision_state": record["pre_decision_state"],
                    },
                    future,
                )
                record.update(
                    counterfactual_classification=counterfactual["classification"],
                    counterfactual_mfe_ticks=counterfactual["mfe_ticks"],
                    counterfactual_mae_ticks=counterfactual["mae_ticks"],
                )
                next_frame = read_optional_json(future_paths[-1]) or {}
                if isinstance(next_frame, dict):
                    subsequent = next(
                        (
                            row.get("intent")
                            for row in read_jsonl(state_root / "decisions.jsonl")
                            if isinstance(row.get("intent"), dict)
                            and str(row.get("packet_id") or "") > packet_id
                        ),
                        None,
                    )
                    if isinstance(subsequent, dict):
                        next_frame = dict(next_frame)
                        next_frame["subsequent_intent"] = subsequent
                    record["change_condition_review"] = review_change_condition(
                        {**intent, "packet": packet},
                        next_frame,
                    )
            records.append(record)
            seen_intents.add(intent_id)
            existing.add(intent_id)

        for row in read_jsonl(state_root / "decisions.jsonl"):
            packet_id = str(row.get("packet_id") or "")
            intent = row.get("intent")
            if packet_id and isinstance(intent, dict):
                enqueue(packet_id, intent)

        for outbox_path in sorted((state_root / "outbox").glob("*.json")):
            intent = read_optional_json(outbox_path)
            if isinstance(intent, dict):
                enqueue(outbox_path.stem, intent)

        append_unique(output_path, records, "episode_id")
        return read_jsonl(output_path)
