import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("telegram_notify", SCRIPTS / "telegram_notify.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def intent(action="HOLD"):
    return {
        "schema_version": "glitch.intent.v2",
        "intent_id": "intent-1",
        "action": action,
        "instrument": "MNQ",
        "account": "TopstepX-50K",
        "confidence": 0.61,
        "reason": "Momentum intact",
    }


def packet():
    return {
        "packet_id": "packet-1",
        "instrument": "MNQ",
        "account": {"name": "TopstepX-50K"},
        "market": {
            "last": 21000.5,
            "ask": 21000.75,
            "bid": 21000.25,
            "features": {"regime_1m": "trend"},
        },
        "policy": {"daily_realized_pnl_usd": 42.5},
    }


class TelegramNotifyTests(unittest.TestCase):
    def test_should_notify_skips_nothing(self):
        self.assertFalse(MODULE.should_notify_action("NOTHING"))
        self.assertFalse(MODULE.should_notify_action("NO_ACTION"))
        self.assertTrue(MODULE.should_notify_action("HOLD"))
        self.assertTrue(MODULE.should_notify_action("ENTER_LONG"))

    def test_format_message_includes_action_and_reason(self):
        message = MODULE.format_decision_message(intent("ENTER_LONG"), packet())
        self.assertIn("ENTRADA LONG", message)
        self.assertIn("Momentum intact", message)

    def test_format_message_includes_regime_daily_pnl_and_rr(self):
        value = intent("ENTER_LONG")
        value.update(
            {
                "quantity": 1,
                "stop_loss": 20990.0,
                "take_profit_1": 21020.0,
            }
        )
        message = MODULE.format_decision_message(value, packet())
        self.assertIn("Regime: Tendencia", message)
        self.assertIn("PnL do dia: +$42.50", message)
        self.assertIn("R:R 1:", message)

    def test_compute_risk_reward_short(self):
        ratio = MODULE.compute_risk_reward(
            "ENTER_SHORT",
            stop=21010.0,
            target=20980.0,
            market={"last": 21000.0, "bid": 21000.0},
        )
        self.assertEqual(ratio, "1:2.00")

    def test_format_trade_pnl_message(self):
        message = MODULE.format_trade_pnl_message({
            "instrument": "MNQ",
            "account": "50K",
            "action": "ENTER_LONG",
            "net_pnl_usd": 42.5,
            "exit_utc": "2026-01-01T12:00:00Z",
            "intent_id": "abc",
        })
        self.assertIn("Trade fechado", message)
        self.assertIn("+$42.50", message)

    def test_format_daily_summary_message(self):
        message = MODULE.format_daily_summary_message({
            "session_date_et": "2026-01-01",
            "net_performance": "Dia positivo",
            "what_worked": ["Disciplina em NOTHING"],
            "what_failed": ["Entrada tardia"],
            "tomorrow_questions": ["Esperar confirmacao"],
        })
        self.assertIn("Resumo do dia", message)
        self.assertIn("Disciplina", message)

    def test_maybe_notify_deduplicates_by_packet(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with mock.patch.dict(
                "os.environ",
                {
                    "GLITCH_TOPSTEP_TELEGRAM_BOT_TOKEN": "token",
                    "GLITCH_TOPSTEP_TELEGRAM_CHAT_ID": "123",
                },
                clear=False,
            ):
                with mock.patch.object(MODULE, "send_telegram_message", return_value={"ok": True, "result": {"message_id": 9}}) as send:
                    self.assertTrue(MODULE.maybe_notify_telegram(state, intent("HOLD"), packet()))
                    self.assertFalse(MODULE.maybe_notify_telegram(state, intent("HOLD"), packet()))
                    send.assert_called_once()

    def test_maybe_notify_records_failure_without_raising(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with mock.patch.dict(
                "os.environ",
                {
                    "GLITCH_TOPSTEP_TELEGRAM_BOT_TOKEN": "token",
                    "GLITCH_TOPSTEP_TELEGRAM_CHAT_ID": "123",
                },
                clear=False,
            ):
                with mock.patch.object(MODULE, "send_telegram_message", side_effect=RuntimeError("boom")):
                    self.assertFalse(MODULE.maybe_notify_telegram(state, intent("EXIT"), packet()))
            events = (state / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("telegram_notify_failed", events)


if __name__ == "__main__":
    unittest.main()
