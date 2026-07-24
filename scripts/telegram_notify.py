"""Telegram alerts for non-NOTHING Topstep decisions."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from common import append_jsonl, load_dotenv, profile_root, read_jsonl, utc_now, write_json_atomic

ACTION_LABELS = {
    "ENTER_LONG": "ENTRADA LONG",
    "ENTER_SHORT": "ENTRADA SHORT",
    "HOLD": "MANTER",
    "EXIT": "SAIR",
    "MOVE_STOP": "MOVER STOP",
}

REGIME_LABELS = {
    "trend": "Tendencia",
    "chop": "Lateral",
    "transition": "Transicao",
    "unknown": "Desconhecido",
}


def _truthy(value: str | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_telegram_env() -> None:
    root = profile_root()
    load_dotenv(root / ".env")
    global_env = root.parent.parent / ".env"
    if global_env.is_file():
        load_dotenv(global_env)


def telegram_enabled() -> bool:
    _load_telegram_env()
    raw = os.environ.get("GLITCH_TOPSTEP_TELEGRAM_ENABLED")
    if raw is not None and not _truthy(raw, default=True):
        return False
    return bool(telegram_bot_token() and telegram_chat_id())


def telegram_bot_token() -> str:
    _load_telegram_env()
    for key in ("GLITCH_TOPSTEP_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def telegram_chat_id() -> str:
    _load_telegram_env()
    for key in (
        "GLITCH_TOPSTEP_TELEGRAM_CHAT_ID",
        "TELEGRAM_HOME_CHANNEL",
        "TELEGRAM_CHAT_ID",
    ):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def should_notify_action(action: Any) -> bool:
    normalized = str(action or "").strip().upper()
    return normalized not in {"", "NOTHING", "NO_ACTION"}


def _action_emoji(action: str) -> str:
    return {
        "ENTER_LONG": "🟢",
        "ENTER_SHORT": "🔴",
        "HOLD": "🟡",
        "EXIT": "⚪",
        "MOVE_STOP": "🔵",
    }.get(action, "📣")


def _format_usd(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    amount = float(value)
    sign = "+" if amount > 0 else ""
    return f"{sign}${amount:.2f}"


def extract_regime(packet: dict[str, Any]) -> str | None:
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    features = market.get("features") if isinstance(market.get("features"), dict) else {}
    raw = features.get("regime_1m") or market.get("regime")
    if not raw:
        return None
    key = str(raw).strip().lower()
    return REGIME_LABELS.get(key, str(raw))


def extract_daily_pnl(packet: dict[str, Any]) -> float | None:
    policy = packet.get("policy") if isinstance(packet.get("policy"), dict) else {}
    session = packet.get("session_activity") if isinstance(packet.get("session_activity"), dict) else {}
    for key in ("daily_realized_pnl_usd",):
        value = policy.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    for key in ("net_pnl_usd", "realized_pnl_usd"):
        value = session.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def extract_unrealized_pnl(packet: dict[str, Any]) -> float | None:
    position = packet.get("position_state") if isinstance(packet.get("position_state"), dict) else {}
    value = position.get("unrealized_pnl_usd")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    account = packet.get("account") if isinstance(packet.get("account"), dict) else {}
    value = account.get("unrealized_pnl")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def compute_risk_reward(
    action: str,
    *,
    stop: Any,
    target: Any,
    market: dict[str, Any],
) -> str | None:
    if action not in {"ENTER_LONG", "ENTER_SHORT"}:
        return None
    if not isinstance(stop, (int, float)) or not isinstance(target, (int, float)):
        return None
    if isinstance(stop, bool) or isinstance(target, bool):
        return None
    last = market.get("last")
    ask = market.get("ask", last)
    bid = market.get("bid", last)
    if action == "ENTER_LONG":
        reference = ask if isinstance(ask, (int, float)) and not isinstance(ask, bool) else last
        risk = float(reference) - float(stop)
        reward = float(target) - float(reference)
    else:
        reference = bid if isinstance(bid, (int, float)) and not isinstance(bid, bool) else last
        risk = float(stop) - float(reference)
        reward = float(reference) - float(target)
    if risk <= 0 or reward <= 0:
        return None
    return f"1:{reward / risk:.2f}"


def format_decision_message(
    intent: dict[str, Any],
    packet: dict[str, Any],
    *,
    receipt: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> str:
    action = str(intent.get("action") or "").upper()
    instrument = str(intent.get("instrument") or packet.get("instrument") or "?")
    account = str(intent.get("account") or packet.get("account", {}).get("name") or "?")
    confidence = intent.get("confidence")
    reason = str(intent.get("reason") or "").strip()
    packet_id = str(packet.get("packet_id") or intent.get("intent_id") or "?")
    market = packet.get("market") if isinstance(packet.get("market"), dict) else {}
    last = market.get("last")
    label = ACTION_LABELS.get(action, action)

    lines = [
        f"{_action_emoji(action)} Glitch Topstep — {label}",
        f"Instrumento: {instrument}",
        f"Conta: {account}",
    ]
    if confidence is not None:
        lines.append(f"Confianca: {confidence}")
    if last is not None:
        lines.append(f"Ultimo: {last}")
    regime = extract_regime(packet)
    if regime:
        lines.append(f"Regime: {regime}")
    daily_pnl = extract_daily_pnl(packet)
    if daily_pnl is not None:
        formatted = _format_usd(daily_pnl)
        if formatted:
            lines.append(f"PnL do dia: {formatted}")
    unrealized = extract_unrealized_pnl(packet)
    if unrealized is not None and unrealized != 0:
        formatted = _format_usd(unrealized)
        if formatted:
            lines.append(f"PnL aberto: {formatted}")
    if action in {"ENTER_LONG", "ENTER_SHORT"}:
        quantity = intent.get("quantity")
        stop = intent.get("stop_loss")
        target = intent.get("take_profit_1")
        if quantity is not None:
            lines.append(f"Quantidade: {quantity}")
        if stop is not None:
            lines.append(f"Stop: {stop}")
        if target is not None:
            lines.append(f"Alvo: {target}")
        risk_reward = compute_risk_reward(action, stop=stop, target=target, market=market)
        if risk_reward:
            lines.append(f"R:R {risk_reward}")
    if reason:
        lines.append(f"Motivo: {reason[:500]}")
    lines.append(f"Packet: {packet_id}")
    if dry_run:
        lines.append("Modo: dry-run (nao enviado ao gateway)")
    elif receipt:
        result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
        body = result.get("body") if isinstance(result.get("body"), dict) else {}
        mode = body.get("mode") or body.get("trading_mode")
        status = body.get("status") or result.get("http_status")
        if mode:
            lines.append(f"Gateway: {mode}")
        if status is not None:
            lines.append(f"Resposta: {status}")
    return "\n".join(lines)


def format_trade_pnl_message(outcome: dict[str, Any]) -> str:
    action = str(outcome.get("action") or "").upper()
    instrument = str(outcome.get("instrument") or "MNQ")
    account = str(outcome.get("account") or "?")
    pnl = float(outcome.get("net_pnl_usd", outcome.get("realized_pnl_usd")) or 0)
    emoji = "✅" if pnl >= 0 else "❌"
    lines = [
        f"{emoji} Trade fechado — {instrument}",
        f"Conta: {account}",
    ]
    if action:
        lines.append(f"Acao original: {ACTION_LABELS.get(action, action)}")
    intent = outcome.get("intent") if isinstance(outcome.get("intent"), dict) else {}
    if intent.get("quantity") is not None:
        lines.append(f"Quantidade: {intent['quantity']}")
    evidence = outcome.get("evidence") if isinstance(outcome.get("evidence"), dict) else {}
    if evidence.get("exit_price") is not None:
        lines.append(f"Saida: {evidence['exit_price']}")
    formatted = _format_usd(pnl)
    if formatted:
        lines.append(f"PnL liquido: {formatted}")
    if outcome.get("shadow_only"):
        lines.append("Modo: shadow")
    lines.append(f"Saida UTC: {outcome.get('exit_utc') or '?'}")
    intent_id = str(outcome.get("intent_id") or "")
    if intent_id:
        lines.append(f"Intent: {intent_id[:36]}")
    return "\n".join(lines)


def _bullet_block(title: str, items: Any, *, limit: int = 3, width: int = 280) -> list[str]:
    if not isinstance(items, list) or not items:
        return []
    lines = [title]
    for item in items[:limit]:
        text = str(item).strip()
        if text:
            lines.append(f"- {text[:width]}")
    extra = len(items) - limit
    if extra > 0:
        lines.append(f"- ... +{extra} mais")
    return lines


def format_daily_summary_message(journal: dict[str, Any]) -> str:
    session_date = str(journal.get("session_date_et") or "?")
    lines = [f"📊 Resumo do dia — {session_date}"]
    performance = str(journal.get("net_performance") or "").strip()
    if performance:
        lines.append("")
        lines.append(performance[:1200])
    lines.extend(_bullet_block("\nO que funcionou:", journal.get("what_worked")))
    lines.extend(_bullet_block("\nO que falhou:", journal.get("what_failed")))
    lines.extend(_bullet_block("\nFoco amanha:", journal.get("tomorrow_questions")))
    return "\n".join(lines)


def maybe_notify_trade_outcome(state_root: Path, outcome: dict[str, Any]) -> bool:
    if not telegram_enabled():
        return False
    if outcome.get("shadow_only"):
        return False
    intent_id = str(outcome.get("intent_id") or "")
    outcome_id = str(outcome.get("outcome_id") or intent_id)
    if not outcome_id:
        return False
    marker = _marker_path(state_root, "outcomes", outcome_id)
    if marker.is_file():
        return False
    try:
        response = send_telegram_message(format_trade_pnl_message(outcome))
    except Exception as error:
        append_jsonl(state_root / "events.jsonl", {
            "schema_version": "glitch.topstep.cycle_event.v1",
            "event": "telegram_notify_failed",
            "kind": "trade_outcome",
            "recorded_utc": utc_now(),
            "outcome_id": outcome_id,
            "error": f"{type(error).__name__}:{error}"[:500],
        })
        return False
    write_json_atomic(marker, {
        "schema_version": "glitch.topstep.telegram_notification.v1",
        "kind": "trade_outcome",
        "recorded_utc": utc_now(),
        "outcome_id": outcome_id,
        "intent_id": intent_id,
        "message_id": response.get("result", {}).get("message_id"),
    })
    return True


def maybe_notify_daily_summary(state_root: Path, journal: dict[str, Any]) -> bool:
    if not telegram_enabled():
        return False
    journal_id = str(journal.get("journal_id") or "")
    session_date = str(journal.get("session_date_et") or "")
    key = journal_id or session_date
    if not key:
        return False
    marker = _marker_path(state_root, "daily", key)
    if marker.is_file():
        return False
    try:
        response = send_telegram_message(format_daily_summary_message(journal))
    except Exception as error:
        append_jsonl(state_root / "events.jsonl", {
            "schema_version": "glitch.topstep.cycle_event.v1",
            "event": "telegram_notify_failed",
            "kind": "daily_summary",
            "recorded_utc": utc_now(),
            "journal_id": journal_id,
            "error": f"{type(error).__name__}:{error}"[:500],
        })
        return False
    write_json_atomic(marker, {
        "schema_version": "glitch.topstep.telegram_notification.v1",
        "kind": "daily_summary",
        "recorded_utc": utc_now(),
        "journal_id": journal_id,
        "session_date_et": session_date,
        "message_id": response.get("result", {}).get("message_id"),
    })
    return True


def notify_new_trade_outcomes(state_root: Path, outcome_ids: list[str], root: Path) -> int:
    if not outcome_ids:
        return 0
    from reconcile_topstep_outcomes import outcomes_canonical_path

    rows = {
        str(row.get("outcome_id")): row
        for row in read_jsonl(outcomes_canonical_path(root))
        if row.get("outcome_id")
    }
    sent = 0
    for outcome_id in outcome_ids:
        row = rows.get(outcome_id)
        if row and maybe_notify_trade_outcome(state_root, row):
            sent += 1
    return sent


def send_telegram_message(text: str) -> dict[str, Any]:
    token = telegram_bot_token()
    chat_id = telegram_chat_id()
    if not token or not chat_id:
        raise RuntimeError("telegram_not_configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"telegram_http_{error.code}:{detail[:240]}") from error
    if not body.get("ok"):
        raise RuntimeError(f"telegram_api_error:{json.dumps(body, ensure_ascii=False)[:240]}")
    return body


def _marker_path(state_root: Path, category: str, key: str) -> Path:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in key)
    return state_root / "telegram-notified" / category / f"{safe}.json"


def _notification_marker(state_root: Path, packet_id: str) -> Path:
    return _marker_path(state_root, "decisions", packet_id)


def maybe_notify_telegram(
    state_root: Path,
    intent: dict[str, Any],
    packet: dict[str, Any],
    *,
    receipt: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> bool:
    if not should_notify_action(intent.get("action")):
        return False
    if not telegram_enabled():
        return False

    packet_id = str(packet.get("packet_id") or intent.get("intent_id") or "").strip()
    if not packet_id:
        return False

    marker = _notification_marker(state_root, packet_id)
    if marker.is_file():
        return False

    message = format_decision_message(intent, packet, receipt=receipt, dry_run=dry_run)
    try:
        response = send_telegram_message(message)
    except Exception as error:
        append_jsonl(
            state_root / "events.jsonl",
            {
                "schema_version": "glitch.topstep.cycle_event.v1",
                "event": "telegram_notify_failed",
                "recorded_utc": utc_now(),
                "packet_id": packet_id,
                "action": intent.get("action"),
                "error": f"{type(error).__name__}:{error}"[:500],
            },
        )
        return False

    write_json_atomic(
        marker,
        {
            "schema_version": "glitch.topstep.telegram_notification.v1",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": intent.get("intent_id"),
            "action": intent.get("action"),
            "message_id": response.get("result", {}).get("message_id"),
            "dry_run": dry_run,
        },
    )
    append_jsonl(
        state_root / "telegram-notifications.jsonl",
        {
            "schema_version": "glitch.topstep.telegram_notification.v1",
            "recorded_utc": utc_now(),
            "packet_id": packet_id,
            "intent_id": intent.get("intent_id"),
            "action": intent.get("action"),
            "dry_run": dry_run,
        },
    )
    return True
