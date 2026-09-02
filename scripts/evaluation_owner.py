"""Evaluation lane ownership — isolated state, HERMES_HOME, and production guards."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from common import PROFILE_NAME, utc_now, write_json_atomic
from model_owner_lock import (
    PRIORITY,
    acquire_model_owner,
    active_model_owner,
    release_model_owner,
)

EVALUATION_PROFILE_NAME = "glitch-topstep-evaluation"
EVALUATION_STATE_SEGMENT = Path("evaluation") / "state"
COGNITIVE_REPLAY_ALLOWED = False
EVALUATION_TEST_ALLOW_LANE_OVERLAP = "EVALUATION_TEST_ALLOW_LANE_OVERLAP"
_cognitive_replay_scope: ContextVar[bool] = ContextVar("cognitive_replay_scope", default=False)

FORBIDDEN_PRODUCTION_RELATIVE = (
    "state/decisions.jsonl",
    "state/receipts.jsonl",
    "state/outbox",
    "state/profile-state.sqlite",
    "state/model-owner.lock",
)

PRODUCTION_LANE_OWNER_KINDS = frozenset({"direct_cycle", "repair", "wake_monitor"})


def evaluation_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def evaluation_run_state_root(run_id: str, *, repo_root: Path | None = None) -> Path:
    safe = str(run_id).strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        raise ValueError("invalid_evaluation_run_id")
    return (repo_root or evaluation_repo_root()) / EVALUATION_STATE_SEGMENT / safe


def _canonical_evaluation_hermes_home() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "hermes" / "profiles" / EVALUATION_PROFILE_NAME).resolve()
    return (Path.home() / ".hermes" / "profiles" / EVALUATION_PROFILE_NAME).resolve()


def evaluation_hermes_home() -> Path:
    explicit = os.environ.get("EVALUATION_HERMES_HOME")
    if explicit:
        resolved = Path(explicit).expanduser().resolve()
        if resolved.name.lower() == EVALUATION_PROFILE_NAME.lower():
            return resolved
    return _canonical_evaluation_hermes_home()


def production_profile_root() -> Path:
    explicit = os.environ.get("HERMES_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _canonical_production_profile_root()


def _canonical_production_profile_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data) / "hermes" / "profiles" / PROFILE_NAME).resolve()
    return (Path.home() / ".hermes" / "profiles" / PROFILE_NAME).resolve()


def production_state_root() -> Path:
    return production_profile_root() / "state"


def production_lane_active(*, production_state: Path | None = None) -> bool:
    state = production_state or production_state_root()
    owner = active_model_owner(state)
    if not isinstance(owner, dict):
        return False
    return str(owner.get("owner_kind") or "") in PRODUCTION_LANE_OWNER_KINDS


def is_evaluation_state_root(state: Path, *, repo_root: Path | None = None) -> bool:
    resolved = state.resolve()
    parts = [part.lower() for part in resolved.parts]
    try:
        eval_idx = parts.index("evaluation")
    except ValueError:
        return False
    if eval_idx + 1 >= len(parts) or parts[eval_idx + 1] != "state":
        return False
    if repo_root is not None:
        base = repo_root.resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            return False
    return True


def is_forbidden_production_path(path: Path) -> bool:
    text = path.as_posix().replace("\\", "/")
    for rel in FORBIDDEN_PRODUCTION_RELATIVE:
        if rel in text or text.endswith(rel):
            return True
    prod_state = production_state_root().resolve()
    try:
        path.resolve().relative_to(prod_state)
        return True
    except ValueError:
        return False


def assert_evaluation_write_allowed(path: Path) -> None:
    if is_forbidden_production_path(path):
        raise PermissionError(f"evaluation_write_forbidden:{path}")


def load_evaluation_budget(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or (evaluation_repo_root() / "evaluation" / "ensemble_config.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    budget = payload.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("evaluation_budget_missing")
    return budget


EVALUATION_AUTH_MODE_OAUTH = "oauth"
EVALUATION_AUTH_MODE_API_KEY = "api_key"
EVALUATION_OAUTH_PROVIDER = "openai-codex"


def evaluation_auth_mode() -> str:
    raw = os.environ.get("EVALUATION_AUTH_MODE", EVALUATION_AUTH_MODE_OAUTH).strip().lower()
    if raw in ("api_key", "openrouter", "api-key"):
        return EVALUATION_AUTH_MODE_API_KEY
    return EVALUATION_AUTH_MODE_OAUTH


def evaluation_uses_hermes_model_routing(auth_mode: str | None = None) -> bool:
    return (auth_mode or evaluation_auth_mode()) == EVALUATION_AUTH_MODE_OAUTH


def load_evaluation_credentials(env_path: Path | None = None) -> dict[str, str]:
    """Return EVALUATION_* keys or evaluation/.env without production outbox routing."""
    collected: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("EVALUATION_") and value.strip():
            collected[key] = value.strip()
    dotenv = env_path or (evaluation_repo_root() / "evaluation" / ".env")
    if dotenv.is_file():
        for raw in dotenv.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key.startswith("EVALUATION_") and key and key not in collected:
                collected[key] = value
    return collected


def evaluation_provider_env(credentials: dict[str, str]) -> dict[str, str]:
    """Map EVALUATION_OPENROUTER_API_KEY -> OPENROUTER_API_KEY for Hermes subprocess."""
    mapped: dict[str, str] = {}
    for key, value in credentials.items():
        if not key.startswith("EVALUATION_") or not value.strip():
            continue
        mapped[key.removeprefix("EVALUATION_")] = value.strip()
    return mapped


def _seed_evaluation_openrouter_api_key() -> bool:
    if os.environ.get("EVALUATION_OPENROUTER_API_KEY", "").strip():
        return True
    parent_env = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
    if not parent_env.is_file():
        return False
    for raw in parent_env.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("OPENROUTER_API_KEY="):
            os.environ["EVALUATION_OPENROUTER_API_KEY"] = (
                line.split("=", 1)[1].strip().strip('"').strip("'")
            )
            return bool(os.environ["EVALUATION_OPENROUTER_API_KEY"])
    return False


def ensure_evaluation_auth_ready(hermes_home: Path) -> tuple[bool, str]:
    """Gate replay entrypoints: OAuth (default, same as production) or legacy API key."""
    mode = evaluation_auth_mode()
    if mode == EVALUATION_AUTH_MODE_API_KEY:
        if _seed_evaluation_openrouter_api_key() or load_evaluation_credentials():
            return True, ""
        return False, "missing_evaluation_openrouter_api_key"
    if not (hermes_home / "config.yaml").is_file():
        return False, "evaluation_hermes_home_missing_config"
    from common import read_model_config

    _model, provider = read_model_config(hermes_home)
    if provider != EVALUATION_OAUTH_PROVIDER:
        return False, f"evaluation_oauth_requires_{EVALUATION_OAUTH_PROVIDER}:configured={provider}"
    return True, ""


def evaluation_auth_present(hermes_home: Path | None = None) -> bool:
    home = hermes_home or evaluation_hermes_home()
    ok, _ = ensure_evaluation_auth_ready(home)
    return ok


def evaluation_hermes_subprocess_env(
    credentials: dict[str, str],
    auth_mode: str | None = None,
) -> dict[str, str]:
    mode = auth_mode or evaluation_auth_mode()
    if mode == EVALUATION_AUTH_MODE_OAUTH:
        return {"GLITCH_TOPSTEP_USE_HERMES_MODEL": "true"}
    mapped = evaluation_provider_env(credentials)
    mapped["GLITCH_TOPSTEP_USE_HERMES_MODEL"] = "false"
    return mapped


def resolve_evaluation_model_provider(hermes_home: Path) -> tuple[str, str]:
    from common import read_model_config

    if evaluation_uses_hermes_model_routing():
        return read_model_config(hermes_home)
    model = os.environ.get("EVALUATION_GLITCH_TOPSTEP_CORE_MODEL", "openai/gpt-4o-mini").strip()
    provider = os.environ.get("EVALUATION_GLITCH_TOPSTEP_CORE_PROVIDER", "openrouter").strip()
    return model, provider


def bootstrap_evaluation_hermes_home(
    *,
    source_repo: Path | None = None,
    target: Path | None = None,
) -> Path:
    """Copy skills + config from profile repo into isolated evaluation HERMES_HOME."""
    import shutil

    repo = source_repo or evaluation_repo_root()
    home = target or _canonical_evaluation_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    for name in ("config.yaml", "SOUL.md", "operator.json", "paired-contract.json"):
        src = repo / name
        if src.is_file():
            shutil.copy2(src, home / name)
    skills_src = repo / "skills"
    skills_dst = home / "skills"
    if skills_src.is_dir():
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(skills_src, skills_dst)
    (home / "state").mkdir(parents=True, exist_ok=True)
    return home


def checkpoint_path(state: Path) -> Path:
    return state / "checkpoint.json"


def read_checkpoint(state: Path) -> dict[str, Any] | None:
    path = checkpoint_path(state)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def write_checkpoint(state: Path, payload: dict[str, Any]) -> None:
    assert_evaluation_write_allowed(checkpoint_path(state))
    write_json_atomic(
        checkpoint_path(state),
        {
            **payload,
            "schema_version": "glitch.topstep.evaluation_checkpoint.v1",
            "recorded_utc": utc_now(),
        },
    )


@dataclass
class EvaluationOwnerSession:
    run_id: str
    state: Path
    invocation_id: str
    hermes_home: Path = field(default_factory=evaluation_hermes_home)
    budget: dict[str, Any] = field(default_factory=load_evaluation_budget)
    repo_root: Path | None = None

    def __post_init__(self) -> None:
        if not is_evaluation_state_root(self.state, repo_root=self.repo_root):
            raise ValueError("evaluation_state_root_required")
        if self.hermes_home.resolve() == _canonical_production_profile_root().resolve():
            raise ValueError("evaluation_hermes_home_must_differ_from_production")
        if not os.environ.get("EVALUATION_HERMES_HOME"):
            if self.hermes_home.name.lower() != EVALUATION_PROFILE_NAME.lower():
                raise ValueError("evaluation_hermes_home_profile_mismatch")
        self.state.mkdir(parents=True, exist_ok=True)

    def acquire(
        self,
        *,
        defer_if_production_lane: bool = True,
        production_state: Path | None = None,
    ) -> bool:
        if not defer_if_production_lane:
            assert_lane_overlap_permitted()
        if defer_if_production_lane and production_lane_active(production_state=production_state):
            return False
        return acquire_model_owner(
            self.state,
            owner_kind="evaluation",
            invocation_id=self.invocation_id,
        )

    def release(self) -> None:
        release_model_owner(
            self.state,
            owner_kind="evaluation",
            invocation_id=self.invocation_id,
        )

    def __enter__(self) -> EvaluationOwnerSession:
        if not self.acquire():
            raise RuntimeError("evaluation_owner_acquire_failed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def supervised_timeout_seconds(self) -> int:
        return int(self.budget.get("per_profile_timeout_ms", 35000)) // 1000

    def total_timeout_seconds(self) -> int:
        return int(self.budget.get("total_timeout_ms", 120000)) // 1000


def open_evaluation_session(
    run_id: str,
    *,
    invocation_id: str | None = None,
    repo_root: Path | None = None,
) -> EvaluationOwnerSession:
    state = evaluation_run_state_root(run_id, repo_root=repo_root)
    return EvaluationOwnerSession(
        run_id=run_id,
        state=state,
        invocation_id=invocation_id or f"eval-{run_id}",
        repo_root=repo_root,
        hermes_home=evaluation_hermes_home(),
    )


def lane_overlap_permitted() -> bool:
    return os.environ.get(EVALUATION_TEST_ALLOW_LANE_OVERLAP, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def assert_lane_overlap_permitted() -> None:
    if not lane_overlap_permitted():
        raise PermissionError("evaluation_lane_overlap_requires_test_env")


def cognitive_replay_permitted() -> bool:
    return COGNITIVE_REPLAY_ALLOWED or _cognitive_replay_scope.get()


@contextmanager
def cognitive_replay_controlled_scope() -> Iterator[None]:
    """ponytail: only tests may enter; module flag stays false in production."""
    token = _cognitive_replay_scope.set(True)
    try:
        yield
    finally:
        _cognitive_replay_scope.reset(token)


def assert_cognitive_replay_blocked() -> None:
    if not cognitive_replay_permitted():
        raise RuntimeError("cognitive_replay_blocked")
