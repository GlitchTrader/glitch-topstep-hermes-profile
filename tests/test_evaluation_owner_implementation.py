"""Behavioral tests for OwnerKind=evaluation implementation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evaluation_owner import (  # noqa: E402
    COGNITIVE_REPLAY_ALLOWED,
    EvaluationOwnerSession,
    assert_cognitive_replay_blocked,
    assert_evaluation_write_allowed,
    ensure_evaluation_auth_ready,
    evaluation_auth_mode,
    evaluation_hermes_home,
    evaluation_hermes_subprocess_env,
    evaluation_run_state_root,
    evaluation_uses_hermes_model_routing,
    is_evaluation_state_root,
    is_forbidden_production_path,
    load_evaluation_budget,
    load_evaluation_credentials,
    open_evaluation_session,
    production_lane_active,
    production_profile_root,
    read_checkpoint,
    resolve_evaluation_model_provider,
    write_checkpoint,
)
from model_owner_lock import (  # noqa: E402
    PRIORITY,
    acquire_model_owner,
    model_owner_lock_path,
    read_model_owner,
    release_model_owner,
)


class EvaluationPriorityTests(unittest.TestCase):
    def test_priority_constant_is_40(self) -> None:
        self.assertEqual(PRIORITY["evaluation"], 40)

    def test_evaluation_defers_to_direct_cycle_repair_wake_monitor(self) -> None:
        for blocker in ("direct_cycle", "repair", "wake_monitor"):
            with self.subTest(blocker=blocker):
                with tempfile.TemporaryDirectory() as root:
                    state = Path(root)
                    self.assertTrue(
                        acquire_model_owner(
                            state,
                            owner_kind=blocker,  # type: ignore[arg-type]
                            invocation_id=f"run-{blocker}",
                        )
                    )
                    self.assertFalse(
                        acquire_model_owner(
                            state,
                            owner_kind="evaluation",
                            invocation_id="run-eval",
                        )
                    )

    def test_evaluation_preempts_learning_on_shared_state(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="learning",
                    invocation_id="run-learning",
                )
            )
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="run-eval",
                )
            )
            owner = read_model_owner(model_owner_lock_path(state))
            assert isinstance(owner, dict)
            self.assertEqual(owner["owner_kind"], "evaluation")


class EvaluationIsolationTests(unittest.TestCase):
    def test_state_root_under_evaluation_state(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            state = evaluation_run_state_root("run-a", repo_root=repo)
            self.assertTrue(is_evaluation_state_root(state, repo_root=repo))
            self.assertFalse(is_evaluation_state_root(repo / "state", repo_root=repo))

    def test_session_rejects_production_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                EvaluationOwnerSession(
                    run_id="bad",
                    state=Path(root) / "state",
                    invocation_id="inv-1",
                    hermes_home=Path(root) / "eval-home",
                )

    def test_hermes_home_differs_from_production(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            eval_home = Path(root) / "glitch-topstep-evaluation"
            os.environ["EVALUATION_HERMES_HOME"] = str(eval_home)
            try:
                self.assertEqual(evaluation_hermes_home(), eval_home.resolve())
                session = open_evaluation_session("run-home", repo_root=Path(root))
                self.assertEqual(session.hermes_home, eval_home.resolve())
                self.assertNotEqual(session.hermes_home, production_profile_root())
            finally:
                os.environ.pop("EVALUATION_HERMES_HOME", None)

    def test_forbidden_production_paths(self) -> None:
        for rel in (
            "state/decisions.jsonl",
            "state/receipts.jsonl",
            "state/outbox/pkt.json",
            "state/profile-state.sqlite",
            "state/model-owner.lock",
        ):
            with self.subTest(path=rel):
                self.assertTrue(is_forbidden_production_path(Path(rel)))
                with self.assertRaises(PermissionError):
                    assert_evaluation_write_allowed(Path(rel))

    def test_checkpoint_write_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            session = open_evaluation_session("run-ckpt", repo_root=Path(root))
            write_checkpoint(session.state, {"phase": "started", "frames_done": 0})
            payload = read_checkpoint(session.state)
            assert isinstance(payload, dict)
            self.assertEqual(payload["phase"], "started")
            write_checkpoint(session.state, {"phase": "resumed", "frames_done": 1})
            resumed = read_checkpoint(session.state)
            assert isinstance(resumed, dict)
            self.assertEqual(resumed["phase"], "resumed")


class EvaluationProductionLaneTests(unittest.TestCase):
    def test_production_lane_active_when_direct_cycle_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            prod_state = Path(root) / "production" / "state"
            prod_state.mkdir(parents=True)
            self.assertTrue(
                acquire_model_owner(
                    prod_state,
                    owner_kind="direct_cycle",
                    invocation_id="prod-1",
                )
            )
            self.assertTrue(production_lane_active(production_state=prod_state))

    def test_evaluation_defers_when_production_lane_active(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            prod_state = repo / "production" / "state"
            prod_state.mkdir(parents=True)
            acquire_model_owner(
                prod_state,
                owner_kind="direct_cycle",
                invocation_id="prod-1",
            )
            session = open_evaluation_session("run-defer", repo_root=repo)
            self.assertFalse(session.acquire(production_state=prod_state))

    def test_evaluation_lock_isolated_while_production_lane_active(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            prod_state = repo / "production" / "state"
            prod_state.mkdir(parents=True)
            acquire_model_owner(
                prod_state,
                owner_kind="direct_cycle",
                invocation_id="prod-1",
            )
            session = open_evaluation_session("run-iso", repo_root=repo)
            with mock.patch.dict(os.environ, {"EVALUATION_TEST_ALLOW_LANE_OVERLAP": "true"}):
                self.assertTrue(
                    session.acquire(
                        defer_if_production_lane=False,
                        production_state=prod_state,
                    )
                )
            session.release()

    def test_lane_overlap_blocked_without_test_env(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            session = open_evaluation_session("run-guard", repo_root=Path(root))
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EVALUATION_TEST_ALLOW_LANE_OVERLAP", None)
                with self.assertRaises(PermissionError):
                    session.acquire(defer_if_production_lane=False)


class EvaluationConcurrencyTests(unittest.TestCase):
    def test_two_evaluation_runs_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            prod_state = repo / "production" / "state"
            prod_state.mkdir(parents=True)
            results: list[bool] = []
            barrier = threading.Barrier(2)

            def attempt(run_id: str) -> None:
                barrier.wait()
                session = open_evaluation_session(run_id, repo_root=repo)
                results.append(session.acquire(production_state=prod_state))
                if results[-1]:
                    session.release()

            threads = [
                threading.Thread(target=attempt, args=("run-a",)),
                threading.Thread(target=attempt, args=("run-b",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(results, [True, True])

    def test_concurrent_acquire_same_run_exactly_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            state = evaluation_run_state_root("run-same", repo_root=repo)
            results: list[bool] = []
            barrier = threading.Barrier(2)

            def attempt(invocation_id: str) -> None:
                barrier.wait()
                results.append(
                    acquire_model_owner(
                        state,
                        owner_kind="evaluation",
                        invocation_id=invocation_id,
                    )
                )

            threads = [
                threading.Thread(target=attempt, args=("inv-1",)),
                threading.Thread(target=attempt, args=("inv-2",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(sum(1 for won in results if won), 1)


class EvaluationFaultTests(unittest.TestCase):
    def test_stale_lock_recovery_without_harming_unrelated_owner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = evaluation_run_state_root("run-stale", repo_root=Path(root))
            state.mkdir(parents=True)
            lock_path = model_owner_lock_path(state)
            stale = {
                "schema_version": "glitch.topstep.model_owner.v1",
                "owner_kind": "evaluation",
                "invocation_id": "dead-run",
                "pid": 999999,
                "process_start_utc": "2020-01-01T00:00:00Z",
                "acquired_utc": "2020-01-01T00:00:00Z",
                "priority": 40,
                "generation": 1,
                "state": "active",
            }
            lock_path.write_text(json.dumps(stale, separators=(",", ":")), encoding="utf-8")
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="live-run",
                )
            )
            owner = read_model_owner(lock_path)
            assert isinstance(owner, dict)
            self.assertEqual(owner["invocation_id"], "live-run")

    def test_release_does_not_steal_new_evaluation_owner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = evaluation_run_state_root("run-toctou", repo_root=Path(root))
            state.mkdir(parents=True)
            lock_path = model_owner_lock_path(state)
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="run-a",
                )
            )
            original = read_model_owner(lock_path)
            assert isinstance(original, dict)
            successor = {
                **original,
                "invocation_id": "run-b",
                "generation": int(original.get("generation") or 0) + 1,
            }
            lock_path.write_text(json.dumps(successor, separators=(",", ":")), encoding="utf-8")
            release_model_owner(state, owner_kind="evaluation", invocation_id="run-a")
            current = read_model_owner(lock_path)
            assert isinstance(current, dict)
            self.assertEqual(current.get("invocation_id"), "run-b")

    def test_acquire_after_simulated_owner_crash(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            state = evaluation_run_state_root("run-crash", repo_root=Path(root))
            state.mkdir(parents=True)
            lock_path = model_owner_lock_path(state)
            crashed = {
                "schema_version": "glitch.topstep.model_owner.v1",
                "owner_kind": "evaluation",
                "invocation_id": "crashed-run",
                "pid": 999999,
                "process_start_utc": "2020-01-01T00:00:00Z",
                "acquired_utc": "2020-01-01T00:00:00Z",
                "priority": 40,
                "generation": 3,
                "state": "active",
            }
            lock_path.write_text(json.dumps(crashed, separators=(",", ":")), encoding="utf-8")
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="after-crash",
                )
            )
            release_model_owner(state, owner_kind="evaluation", invocation_id="after-crash")
            self.assertTrue(
                acquire_model_owner(
                    state,
                    owner_kind="evaluation",
                    invocation_id="after-release",
                )
            )

    def test_tree_kill_helper_available_for_timeout_path(self) -> None:
        from process_supervisor import terminate_pid_tree

        with mock.patch("process_supervisor.subprocess.run") as run:
            with mock.patch("process_supervisor.sys.platform", "win32"):
                terminate_pid_tree(4242, grace_seconds=0)
        run.assert_called()


class EvaluationBudgetAndCredentialsTests(unittest.TestCase):
    def test_budget_loaded_from_ensemble_config(self) -> None:
        budget = load_evaluation_budget()
        self.assertEqual(budget["max_calls_per_snapshot"], 6)
        self.assertEqual(budget["per_profile_timeout_ms"], 35000)

    def test_session_timeout_seconds_from_budget(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            session = open_evaluation_session("run-timeout", repo_root=Path(root))
            self.assertEqual(session.supervised_timeout_seconds(), 35)
            self.assertEqual(session.total_timeout_seconds(), 120)

    def test_evaluation_credentials_ignore_production_keys(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            env_path = Path(root) / "evaluation.env"
            env_path.write_text(
                "EVALUATION_OPENROUTER_API_KEY=test-key\nGLITCH_LOCAL_TOKEN=prod\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"GLITCH_LOCAL_TOKEN": "prod"}, clear=False):
                creds = load_evaluation_credentials(env_path=env_path)
            self.assertEqual(creds["EVALUATION_OPENROUTER_API_KEY"], "test-key")
            self.assertNotIn("GLITCH_LOCAL_TOKEN", creds)

    def test_oauth_mode_ready_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "eval-home"
            home.mkdir()
            (home / "config.yaml").write_text(
                "model:\n  default: gpt-5.6-luna\n  provider: openai-codex\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(evaluation_auth_mode(), "oauth")
                ok, err = ensure_evaluation_auth_ready(home)
            self.assertTrue(ok, err)
            self.assertEqual(err, "")

    def test_oauth_mode_rejects_non_codex_provider(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "eval-home"
            home.mkdir()
            (home / "config.yaml").write_text(
                "model:\n  default: openai/gpt-4o-mini\n  provider: openrouter\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                ok, err = ensure_evaluation_auth_ready(home)
            self.assertFalse(ok)
            self.assertIn("openai-codex", err)

    def test_api_key_mode_requires_openrouter_key(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "eval-home"
            home.mkdir()
            (home / "config.yaml").write_text(
                "model:\n  default: gpt-5.6-luna\n  provider: openai-codex\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"EVALUATION_AUTH_MODE": "api_key"}, clear=True):
                with mock.patch("evaluation_owner._seed_evaluation_openrouter_api_key", return_value=False):
                    with mock.patch("evaluation_owner.load_evaluation_credentials", return_value={}):
                        ok, err = ensure_evaluation_auth_ready(home)
            self.assertFalse(ok)
            self.assertEqual(err, "missing_evaluation_openrouter_api_key")

    def test_oauth_subprocess_env_uses_hermes_model_routing(self) -> None:
        env = evaluation_hermes_subprocess_env({}, auth_mode="oauth")
        self.assertEqual(env["GLITCH_TOPSTEP_USE_HERMES_MODEL"], "true")
        self.assertNotIn("OPENROUTER_API_KEY", env)

    def test_resolve_model_provider_reads_config_in_oauth_mode(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "eval-home"
            home.mkdir()
            (home / "config.yaml").write_text(
                "model:\n  default: gpt-5.6-luna\n  provider: openai-codex\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                model, provider = resolve_evaluation_model_provider(home)
            self.assertEqual(model, "gpt-5.6-luna")
            self.assertEqual(provider, "openai-codex")
            self.assertTrue(evaluation_uses_hermes_model_routing())


class EvaluationReplayGateTests(unittest.TestCase):
    def test_cognitive_replay_remains_blocked(self) -> None:
        self.assertFalse(COGNITIVE_REPLAY_ALLOWED)
        with self.assertRaises(RuntimeError):
            assert_cognitive_replay_blocked()


if __name__ == "__main__":
    unittest.main()
