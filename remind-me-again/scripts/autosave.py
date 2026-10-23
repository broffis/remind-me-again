"""Opt-in Copilot autosave and autoread hooks."""

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from uuid import UUID

from save_summary import save_summary
from storage import project_directory, validate_date


EVENTS = ("sessionStart", "userPromptSubmitted", "agentStop", "sessionEnd")
FEATURES = ("autosave", "autoread")
SESSION_SOURCES = ("startup", "resume", "new")
SCRIPT = Path(__file__).resolve()


def regular_path(path):
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic link: {path}")
    return path


def read_json(path):
    regular_path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path, value):
    """Atomically replace settings or state without leaving a partial JSON file."""
    regular_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".session-info-",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def copilot_home():
    return Path(os.environ.get("COPILOT_HOME", str(Path.home() / ".copilot"))).expanduser()


def repository(cwd):
    """Find the nearest Git root, including worktrees whose .git is a file."""
    directory = Path(cwd).expanduser().resolve(strict=True)
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def settings(path):
    regular_path(path)
    if not path.exists():
        return {"version": 1}
    value = read_json(path)
    if value.get("version") != 1:
        raise ValueError(f"Unsupported settings version: {path}")
    for feature in FEATURES:
        if feature in value and type(value[feature]) is not bool:
            raise ValueError(f"{feature} must be true or false: {path}")
    if value.get("checkpoint_transport", "shell") not in ("shell", "mcp"):
        raise ValueError(f"checkpoint_transport must be shell or mcp: {path}")
    return value


def enabled(cwd, feature="autosave"):
    """Resolve a feature's repo override before falling back to the global default."""
    if feature not in FEATURES:
        raise ValueError("Unknown session-info feature.")
    root = repository(cwd)
    if root is not None:
        local = settings(root / ".github/session-info.json")
        if feature in local:
            return local[feature]
    return settings(copilot_home() / "session-info-settings.json").get(feature, False)


def configuration_paths(scope, cwd):
    if scope == "global":
        base = copilot_home()
        config = base / "session-info-settings.json"
        hook_path = base / "hooks/session-info.json"
    else:
        base = repository(cwd)
        if base is None:
            raise ValueError("Repository configuration requires a Git repository.")
        config = base / ".github/session-info.json"
        hook_path = base / ".github/hooks/session-info.json"
    return config, hook_path


def configure_transport(cwd, transport):
    if transport not in ("shell", "mcp"):
        raise ValueError("Checkpoint transport must be shell or mcp.")
    root = repository(cwd)
    if root is None:
        raise ValueError("Checkpoint transport requires a Git repository.")
    path = root / ".github/session-info.json"
    value = settings(path)
    value["checkpoint_transport"] = transport
    write_json(path, value)
    return path


def checkpoint_transport(cwd):
    root = repository(cwd)
    if root is None:
        return "shell"
    return settings(root / ".github/session-info.json").get(
        "checkpoint_transport", "shell"
    )


def hook_configuration():
    hooks = {}
    for event in EVENTS:
        hooks[event] = [{
            "type": "command",
            "exec": sys.executable,
            "args": [str(SCRIPT), "hook", event],
            "timeoutSec": 10,
        }]
    return {
        "version": 1,
        "hooks": hooks,
    }


def configure(scope, mode, cwd, feature="autosave"):
    """Install our hooks and update only the selected feature's opt-in setting."""
    if scope not in ("global", "repo") or mode not in ("on", "off", "inherit"):
        raise ValueError("Invalid autosave scope or mode.")
    if feature not in FEATURES:
        raise ValueError("Unknown session-info feature.")
    config, hook_path = configuration_paths(scope, cwd)
    hooks = hook_configuration()
    regular_path(hook_path)
    if hook_path.exists() and read_json(hook_path) != hooks:
        raise ValueError(f"Refusing to overwrite an existing hook: {hook_path}")
    value = settings(config)
    if mode == "inherit":
        value.pop(feature, None)
    else:
        value[feature] = mode == "on"
    write_json(hook_path, hooks)
    write_json(config, value)
    return config


def state_path(cwd, session_id):
    if str(UUID(session_id)) != session_id.lower():
        raise ValueError("Session ID must be a hyphenated UUID.")
    _, project = project_directory(cwd)
    folder = project / ".autosave"
    if not folder.resolve().is_relative_to(project.resolve()):
        raise ValueError("Autosave state must remain inside the project storage.")
    return regular_path(folder / f"{session_id.lower()}.json")


def read_state(cwd, session_id):
    """Read turn hashes: latest user turn, last saved turn, and requested save."""
    path = state_path(cwd, session_id)
    if not path.exists():
        raise ValueError(
            "Missing autosave session state; use autosave.py initialize with "
            "the exact session ID and original --session-date, then resume."
        )
    state = read_json(path)
    validate_date(state["session_date"])
    if state.get("version") != 1:
        raise ValueError("Unsupported autosave state version.")
    for name in ("turn", "saved", "requested"):
        value = state[name]
        if value is not None and (
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"Invalid autosave state field: {name}")
    return state


@contextmanager
def state_lock(cwd, session_id):
    """Serialize hook events and checkpoint writes for one project/session."""
    path = state_path(cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = regular_path(path.with_suffix(".lock"))
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield path


def initialize(cwd, session_id, session_date):
    """Create state once; resuming must never change the original start date."""
    validate_date(session_date)
    with state_lock(cwd, session_id) as path:
        if path.exists():
            if read_state(cwd, session_id)["session_date"] != session_date:
                raise ValueError("Cannot change an existing session's start date.")
            return
        write_json(path, {
            "version": 1,
            "session_date": session_date,
            "turn": None,
            "saved": None,
            "requested": None,
        })


def event_date(payload):
    timestamp = payload["timestamp"]
    if type(timestamp) not in (int, float):
        raise ValueError("Hook timestamp must be epoch milliseconds.")
    return datetime.fromtimestamp(timestamp / 1000).astimezone().date().isoformat()


def prompt_token(payload):
    """Identify a submitted turn without persisting its prompt text."""
    event_date(payload)
    if not isinstance(payload["prompt"], str):
        raise ValueError("Hook prompt must be a string.")
    identity = json.dumps(
        [payload["sessionId"], payload["timestamp"], payload["prompt"]],
        ensure_ascii=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def request(cwd, session_id, state):
    """Ask the existing agent for one permission-respecting save continuation."""
    if checkpoint_transport(cwd) == "mcp":
        return {"decision": "block", "reason": "Session-summary autosave requested"}
    command = shlex.join([
        sys.executable, str(SCRIPT), "checkpoint", "--cwd", str(cwd),
        "--session-id", session_id, "--token", state["turn"],
    ])
    action = f"Send summary via quoted-heredoc stdin to:\n{command}\n"
    return {
        "decision": "block",
        "reason": (
            "Session-summary autosave requested. Follow automatic checkpoint "
            f"instructions in {SCRIPT.parent.parent / 'SKILL.md'}.\n"
            f"{action}"
        ),
    }


def autoread(payload):
    import retrieval

    cwd = payload["cwd"]
    if payload["source"] not in SESSION_SOURCES:
        raise ValueError("Unknown session start source.")
    event_date(payload)
    session_id = payload["sessionId"]
    # Share session ID/path validation, but keep reading state independent of
    # autosave initialization (including for previously unknown resumed sessions).
    project = state_path(cwd, session_id).parent.parent
    folder = project / ".autoread"
    if not folder.resolve().is_relative_to(project.resolve()):
        raise ValueError("Autoread state must remain inside the project storage.")
    folder.mkdir(parents=True, exist_ok=True)
    path = regular_path(folder / f"{session_id.lower()}.json")
    lock_path = regular_path(path.with_suffix(".lock"))
    event_details = [session_id, payload["timestamp"], payload["source"]]
    event_token = hashlib.sha256(
        json.dumps(event_details).encode("utf-8")
    ).hexdigest()
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            state = read_json(path)
            if state.get("version") != 1 or not isinstance(state.get("event"), str):
                raise ValueError("Invalid autoread state.")
            if state["event"] == event_token:
                return {}
        context = retrieval.retrieve(cwd)
        write_json(path, {"version": 1, "event": event_token})
        return {"additionalContext": context}


def handle(event, payload):
    """Dispatch root-agent hooks, keeping autoread and autosave opt-ins separate."""
    if event not in EVENTS:
        raise ValueError("Unknown autosave hook event.")
    if not isinstance(payload, dict):
        raise ValueError("Hook payload must be an object.")
    if payload.get("agentId"):
        return {}
    result = handle_autosave(event, payload)
    if event == "sessionStart" and enabled(payload["cwd"], "autoread"):
        result.update(autoread(payload))
    return result


def start_autosave_session(payload):
    cwd = payload["cwd"]
    session_id = payload["sessionId"]
    if payload["source"] not in SESSION_SOURCES:
        raise ValueError("Unknown session start source.")
    if not state_path(cwd, session_id).exists():
        if payload["source"] == "resume":
            read_state(cwd, session_id)
        initialize(cwd, session_id, event_date(payload))
    with state_lock(cwd, session_id) as path:
        state = read_state(cwd, session_id)
        state["requested"] = None
        if payload.get("initialPrompt"):
            initial_prompt = dict(payload, prompt=payload["initialPrompt"])
            state["turn"] = prompt_token(initial_prompt)
        write_json(path, state)
    return {}


def record_user_turn(payload, state, path):
    if (
        state["requested"] is not None
        and state["requested"] == state["turn"]
        and payload["prompt"] == request(
            payload["cwd"], payload["sessionId"], state
        )["reason"]
    ):
        return {}
    token = prompt_token(payload)
    if token != state["turn"]:
        state["turn"] = token
        state["requested"] = None
        write_json(path, state)
    return {}


def has_unsaved_progress(state):
    return state["turn"] is not None and state["saved"] != state["turn"]


def finish_agent_turn(payload, state, path):
    """Request one save, but never recursively request another during that save."""
    if type(payload.get("stop_hook_active")) is not bool:
        raise ValueError("agentStop requires boolean stop_hook_active.")
    unsaved = has_unsaved_progress(state)
    if payload["stop_hook_active"]:
        if unsaved:
            raise ValueError("Autosave continuation ended with unsaved progress.")
        return {}
    if not unsaved or state["requested"] == state["turn"]:
        return {}
    state["requested"] = state["turn"]
    write_json(path, state)
    return request(payload["cwd"], payload["sessionId"], state)


def handle_autosave(event, payload):
    cwd = payload["cwd"]
    if not enabled(cwd):
        return {}
    if event == "sessionStart":
        return start_autosave_session(payload)

    session_id = payload["sessionId"]
    with state_lock(cwd, session_id) as path:
        state = read_state(cwd, session_id)
        if event == "userPromptSubmitted":
            return record_user_turn(payload, state, path)
        if event == "sessionEnd":
            if has_unsaved_progress(state):
                raise ValueError(
                    "Session ended with unsaved progress; resume it to save. "
                    "Previously saved checkpoints are preserved."
                )
            return {}
        return finish_agent_turn(payload, state, path)


def checkpoint(cwd, session_id, token, summary):
    """Write idempotently before recording success, so failures remain retryable."""
    if not enabled(cwd):
        raise ValueError("Autosave is disabled for this working directory.")
    if not summary.strip():
        raise ValueError("Checkpoint summary must not be empty.")
    with state_lock(cwd, session_id) as path:
        state = read_state(cwd, session_id)
        if token != state["turn"] or token is None:
            raise ValueError("Checkpoint token is stale; a newer user turn exists.")
        destination = save_summary(
            cwd, session_id, state["session_date"], summary, checkpoint_id=token
        )
        state["saved"] = token
        write_json(path, state)
        return destination


def checkpoint_context(cwd, session_id):
    """Read only this exact session's pending request; never select a session."""
    if not enabled(cwd):
        raise ValueError("Autosave is disabled for this working directory.")
    # Validate existing state before acquiring a lock that could create directories.
    read_state(cwd, session_id)
    with state_lock(cwd, session_id):
        state = read_state(cwd, session_id)
        if not has_unsaved_progress(state) or state["requested"] != state["turn"]:
            raise ValueError("No current pending checkpoint for this session.")
        return {
            "session_id": session_id,
            "token": state["requested"],
            "session_date": state["session_date"],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("configure")
    config.add_argument("--scope", choices=("global", "repo"), required=True)
    config.add_argument("--mode", choices=("on", "off", "inherit"), required=True)
    config.add_argument("--feature", choices=FEATURES, default="autosave")
    config.add_argument("--cwd", default=str(Path.cwd()))
    transport = commands.add_parser("configure-transport")
    transport.add_argument("--cwd", required=True)
    transport.add_argument("--mode", choices=("shell", "mcp"), required=True)
    hook = commands.add_parser("hook")
    hook.add_argument("event", choices=EVENTS)
    for name in ("initialize", "checkpoint"):
        command = commands.add_parser(name)
        command.add_argument("--cwd", required=True)
        command.add_argument("--session-id", required=True)
        if name == "initialize":
            command.add_argument("--session-date", required=True)
        else:
            command.add_argument("--token", required=True)
    args = parser.parse_args()
    try:
        if args.command == "configure":
            print(configure(args.scope, args.mode, args.cwd, args.feature))
        elif args.command == "configure-transport":
            print(configure_transport(args.cwd, args.mode))
        elif args.command == "hook":
            print(json.dumps(handle(args.event, json.load(sys.stdin))))
        elif args.command == "initialize":
            initialize(args.cwd, args.session_id, args.session_date)
            print("Initialized autosave session date.")
        else:
            print(checkpoint(args.cwd, args.session_id, args.token, sys.stdin.read()))
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.exit(1, f"Session-info autosave error: {error}\n")


if __name__ == "__main__":
    main()
