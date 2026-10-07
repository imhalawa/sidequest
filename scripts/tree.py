import datetime
import json
import os
import re

OPEN, DONE, CURRENT, DROPPED, PARKED, DELEGATED, WAITING = "☐", "✓", "▶", "✗", "◇", "⇢", "!"


def home():
    return os.environ.get("SIDEQUEST_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME") or os.path.expanduser("~/.claude"), "sidequest")


def now():
    return os.environ.get("SIDEQUEST_NOW") or datetime.datetime.now().isoformat(timespec="seconds")


def path(session):
    safe = re.sub(r"[^\w-]", "_", session or "unknown")
    return os.path.join(home(), f"{safe}.json")


DEFAULTS = {"notes": [], "links": [], "progress": [], "sessions": [], "messages": 0, "priority": None,
            "raw": None, "parked_from": None, "delegable": False, "delegation": None, "created": None,
            "closed": None, "entered": None, "elect_checked": False}


def empty():
    return {"current": None, "messages": 0, "topics": [], "focus": None}


def option(name, default=None):
    value = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name}") or os.environ.get(f"SIDEQUEST_{name}")
    if not value:
        return default
    if value.strip().lower() in ("off", "all"):
        return None
    number = re.search(r"\d+", value)
    return max(1, int(number.group())) if number else default


def is_valid(state):
    return isinstance(state, dict) and isinstance(state.get("topics"), list) and isinstance(state.get("messages", 0), int)


def read(file):
    try:
        with open(file, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return None
    if not is_valid(state):
        return None
    state.setdefault("current", None)
    state.setdefault("messages", 0)
    state.setdefault("focus", None)
    for topic in state["topics"]:
        for key, value in DEFAULTS.items():
            topic.setdefault(key, list(value) if isinstance(value, list) else value)
    return state


def load(session):
    return read(path(session)) or empty()


def exists(session):
    return os.path.exists(path(session))


def save(session, state):
    os.makedirs(home(), exist_ok=True)
    target = path(session)
    temporary = f"{target}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
    os.replace(temporary, target)


def sessions():
    if not os.path.isdir(home()):
        return []
    files = [os.path.join(home(), name) for name in os.listdir(home()) if name.endswith(".json")]
    return sorted(files, key=os.path.getmtime, reverse=True)


def find(state, topic_id):
    return next((topic for topic in state["topics"] if topic["id"] == topic_id), None)


def ancestors(state, topic):
    chain = []
    while topic is not None:
        chain.insert(0, topic)
        topic = find(state, topic["parent"]) if topic["parent"] is not None else None
    return chain


def glyph(state, topic):
    delegation = (topic.get("delegation") or {}).get("status")
    if delegation == "running":
        return DELEGATED
    if delegation == "needs-input":
        return WAITING
    if topic["id"] == state["current"]:
        return CURRENT
    return {"done": DONE, "dropped": DROPPED, "parked": PARKED}.get(topic["status"], OPEN)


def all_states():
    for file in sessions():
        state = read(file)
        if state is not None:
            yield os.path.basename(file)[:-len(".json")], state


def counts(state):
    statuses = [topic["status"] for topic in state["topics"]]
    return statuses.count("open"), statuses.count("done")


def render(state, ids=False, notes=False):
    topics = state["topics"]
    if not topics:
        return "Topic map · no topics yet\n"
    open_count, done_count = counts(state)
    lines = [f"Topic map · {OPEN} {open_count} open · {DONE} {done_count} done", "", "session"]

    def walk(parent, prefix):
        children = [topic for topic in topics if topic["parent"] == parent]
        for index, topic in enumerate(children):
            last = index == len(children) - 1
            suffix = f"  #{topic['id']}" if ids else ""
            lines.append(f"{prefix}{'└── ' if last else '├── '}{glyph(state, topic)} {topic['title']}{suffix}")
            child_prefix = prefix + ("    " if last else "│   ")
            if notes and topic["status"] == "open":
                lines.extend(f"{child_prefix}  · {note}" for note in topic["notes"])
            walk(topic["id"], child_prefix)

    walk(None, "")
    return "\n".join(lines) + "\n"


def open_only(state):
    keep = set()
    for topic in state["topics"]:
        if topic["status"] == "open":
            keep.update(ancestor["id"] for ancestor in ancestors(state, topic))
    return dict(state, current=None, topics=[topic for topic in state["topics"] if topic["id"] in keep])


def describe(topic):
    lines = [f"#{topic['id']} {topic['title']}"]
    if topic["notes"]:
        lines += ["notes:"] + [f"- {note}" for note in topic["notes"]]
    if topic["links"]:
        lines += ["links:"] + [f"- {link}" for link in topic["links"]]
    return "\n".join(lines)


def cli_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "topics.py")


def usage(session):
    command = f'python3 "{cli_path()}" --session {session}'
    return (
        "Record with the mcp__sidequest__topics tool, args as a list, e.g. [\"fork\", \"<title>\"]. "
        "Only when that tool is missing, run the same command with Bash:\n"
        f'{command} fork "<title>" [--under <id>|root]   new topic, under the current one unless --under says otherwise\n'
        f"{command} done <id>                            topic finished\n"
        f"{command} drop <id>                            topic abandoned, not needed any more\n"
        f"{command} now <id>                             back to an earlier topic; prints its notes and links\n"
        f'{command} rename <id> "<title>"                a clearer title once the topic is better understood\n'
        f'{command} note "<text>" [--on <id>]            a finding, decision, or next step worth keeping\n'
        f"{command} link <kind> <value> [--on <id>]      a Jira key, PR, Slack thread, or file the topic is about\n"
        f"{command} show [--ids]                         print the tree"
    )
