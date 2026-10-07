import json
import sys

import tree


def nudge(session, state):
    current = tree.find(state, state["current"]) if state["current"] is not None else None
    topic = f'#{current["id"]} "{current["title"]}"' if current else "none"
    focus = tree.find(state, state["focus"]) if state["focus"] is not None else None
    focus_line = (f'Focus is on #{focus["id"]} "{focus["title"]}": a new idea outside it gets parked with park, '
                  "and leaving it needs the user's reason (--reason). " if focus else "")
    ready = [f"#{item['id']}" for item in state["topics"] if item["status"] == "open" and not item["delegable"]
             and item["notes"] and item["links"] and not item.get("elect_checked")]
    ready_line = (f"Elect now, silently, each of these topics that a sub-agent could finish alone from its notes and links: "
                  f"{', '.join(ready)} (elect <id>, or elect <id> --off if it could not). " if ready else "")
    return focus_line + ready_line + (
        f"sidequest: session {session} · current topic {topic}. Before answering, check this message for every change "
        "and record each one: every new subject is its own fork, a finished topic is done, a return is now, an "
        f"abandoned topic is drop.\n{tree.usage(session)}"
    )


def depth_alert(state):
    current = tree.find(state, state["current"]) if state["current"] is not None else None
    if current is None or state.get("alerted") == current["id"]:
        return None
    chain = tree.ancestors(state, current)
    limit = tree.option("DEPTH_ALERT", 3)
    if limit is None or len(chain) < limit:
        return None
    state["alerted"] = current["id"]
    path = " › ".join(topic["title"] for topic in chain)
    return (f"sidequest depth alert: the user is {len(chain)} levels deep: {path}. Their topic panel may be collapsed, "
            f'so start your reply with this line: "You\'re {len(chain)} levels deep, starting from {chain[0]["title"]}."')


def main():
    try:
        payload = json.load(sys.stdin)
        session = payload["session_id"]
    except (ValueError, KeyError, TypeError):
        return 0
    state = tree.load(session)
    state["messages"] += 1
    current = tree.find(state, state["current"]) if state["current"] is not None else None
    if current is not None:
        current["messages"] += 1
    parts = [nudge(session, state)]
    if not state.get("started") and not state.get("instructed"):
        import session_start
        parts.insert(0, session_start.instructions(session))
        state["instructed"] = True
    alert = depth_alert(state)
    if alert:
        parts.insert(0, alert)
    tree.save(session, state)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(parts)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
