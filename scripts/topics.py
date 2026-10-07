import argparse
import datetime
import os
import re
import sqlite3
import statistics
import subprocess
import sys

import tree

PRIORITIES = {"now": 0, "today": 1, None: 2, "later": 3}


def fail(message):
    print(message, file=sys.stderr)
    return 1


def parse_parent(value):
    return None if value == "root" else int(value)


def target(state, topic_id):
    topic_id = state["current"] if topic_id is None else topic_id
    return tree.find(state, topic_id) if topic_id is not None else None


def touch(topic, session):
    if session not in topic["sessions"]:
        topic["sessions"].append(session)


def current_branch():
    try:
        result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else None


def add_link(topic, link):
    if link not in topic["links"]:
        topic["links"].append(link)


def in_focus(state, topic_id):
    if state["focus"] is None or topic_id is None:
        return state["focus"] is None
    topic = tree.find(state, topic_id)
    return topic is not None and any(ancestor["id"] == state["focus"] for ancestor in tree.ancestors(state, topic))


def guard(state, destination_id, title, reason):
    if in_focus(state, destination_id):
        return None
    if not reason:
        focus = tree.find(state, state["focus"])
        return fail(f"focus is on #{focus['id']} {focus['title']}. Park the idea with park, or pass --reason "
                    "with the user's reason for leaving the focus topic.")
    tree.find(state, state["focus"])["notes"].append(f"left focus for {title}: {reason}")
    return None


def progress_prompt(state, leaving_id):
    topic = tree.find(state, leaving_id) if leaving_id is not None else None
    if topic is None or topic["status"] != "open":
        return ""
    entered = topic["entered"] or ""
    if any(entry["at"] >= entered for entry in topic["progress"]):
        return ""
    return (f"\nNo progress saved for #{topic['id']} {topic['title']} yet: write one with "
            f'progress "<done, decided, ruled out, next step>" --on {topic["id"]}')


def enter(state, topic):
    state["current"] = topic["id"]
    topic["entered"] = tree.now()


def new_topic(state, title, parent_id, session, status="open"):
    topic = dict({key: list(value) if isinstance(value, list) else value for key, value in tree.DEFAULTS.items()},
                 id=max((topic["id"] for topic in state["topics"]), default=0) + 1, title=title, parent=parent_id,
                 status=status, created=tree.now())
    touch(topic, session)
    state["topics"].append(topic)
    return topic


def fork(state, session, title, under, reason):
    title = title.strip()
    if not title:
        return fail("title is empty")
    parent_id = state["current"] if under is None else parse_parent(under)
    parent = tree.find(state, parent_id) if parent_id is not None else None
    if parent_id is not None and parent is None:
        return fail(f"no topic #{parent_id}")
    if state["focus"] is not None and (parent_id is None or not in_focus(state, parent_id)):
        refused = guard(state, None, title, reason)
        if refused:
            return refused
    leaving = state["current"]
    topic = new_topic(state, title, parent_id, session)
    branch = current_branch()
    inherited = [link for ancestor in (tree.ancestors(state, parent) if parent else []) for link in ancestor["links"]]
    if branch and f"branch: {branch}" not in inherited:
        add_link(topic, f"branch: {branch}")
    enter(state, topic)
    print(f"#{topic['id']} {title} · depth {len(tree.ancestors(state, topic))}{progress_prompt(state, leaving)}")
    return 0


def nearest_open_parent(state, topic):
    parent = tree.find(state, topic["parent"]) if topic["parent"] is not None else None
    while parent is not None and parent["status"] != "open":
        parent = tree.find(state, parent["parent"]) if parent["parent"] is not None else None
    return parent["id"] if parent else None


def parked_during(state, focus_id):
    return [topic for topic in state["topics"] if topic["status"] == "parked" and topic["parked_from"] is not None
            and any(ancestor["id"] == focus_id for ancestor in tree.ancestors(state, tree.find(state, topic["parked_from"]) or {"id": None, "parent": None}))]


def close(state, topic_id, status):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    message = progress_prompt(state, topic_id) if status == "done" else ""
    topic["status"] = status
    topic["closed"] = tree.now()
    if state["current"] == topic_id:
        state["current"] = nearest_open_parent(state, topic)
    print(f"#{topic_id} {status}{message}")
    if state["focus"] == topic_id:
        state["focus"] = None
        ideas = parked_during(state, topic_id)
        print(f"Focus finished. Parked while on it: {len(ideas)}")
        print("\n".join(f"- {idea['title']}  #{idea['id']}" for idea in ideas))
    return 0


def now(state, session, topic_id, reason):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    if state["focus"] is not None:
        refused = guard(state, topic_id, topic["title"], reason)
        if refused:
            return refused
    leaving = state["current"] if state["current"] != topic_id else None
    topic["status"] = "open"
    topic["closed"] = None
    touch(topic, session)
    message = progress_prompt(state, leaving)
    enter(state, topic)
    print(tree.describe(topic) + message)
    return 0


def rename(state, topic_id, title):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    if not title.strip():
        return fail("title is empty")
    topic["title"] = title.strip()
    print(f"#{topic_id} {topic['title']}")
    return 0


def note(state, session, text, on):
    topic = target(state, on)
    if topic is None:
        return fail("no topic to note on")
    topic["notes"].append(text.strip())
    touch(topic, session)
    print(f"#{topic['id']} noted")
    return 0


def progress(state, session, text, on):
    topic = target(state, on)
    if topic is None:
        return fail("no topic to save progress on")
    topic["progress"].append({"session": session, "at": tree.now(), "text": text.strip()})
    touch(topic, session)
    print(f"#{topic['id']} progress saved")
    return 0


def link(state, kind, value, on):
    topic = target(state, on)
    if topic is None:
        return fail("no topic to link")
    add_link(topic, f"{kind}: {value}")
    print(f"#{topic['id']} linked")
    return 0


def park(state, session, text):
    text = text.strip()
    if not text:
        return fail("idea is empty")
    idea = new_topic(state, text, None, session, status="parked")
    idea["raw"] = text
    idea["parked_from"] = state["current"]
    branch = current_branch()
    if branch:
        add_link(idea, f"branch: {branch}")
    print(f"#{idea['id']} parked")
    return 0


def focus(state, topic_id, off):
    if off:
        state["focus"] = None
        print("focus off")
        return 0
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    state["focus"] = topic_id
    print(f"focus on #{topic_id} {topic['title']}")
    return 0


def priority(state, topic_id, level):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    topic["priority"] = level
    print(f"#{topic_id} priority {level}")
    return 0


def elect(state, topic_id, off):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    topic["delegable"] = not off
    topic["elect_checked"] = True
    print(f"#{topic_id} {'not ' if off else ''}delegable")
    return 0


def delegation(state, topic_id, status, agent):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    if not topic["delegable"]:
        return fail(f"#{topic_id} is not elected for delegation")
    topic["delegation"] = {"status": status, "agent": agent or (topic["delegation"] or {}).get("agent")}
    if status == "done":
        topic["status"] = "done"
        topic["closed"] = tree.now()
    print(f"#{topic_id} delegation {status}")
    return 0


def brief(state, topic_id, edits):
    topic = tree.find(state, topic_id)
    if topic is None:
        return fail(f"no topic #{topic_id}")
    chain = tree.ancestors(state, topic)
    lines = [f"Goal: {topic['title']}"]
    if len(chain) > 1:
        lines.append(f"Part of: {' › '.join(ancestor['title'] for ancestor in chain[:-1])}")
    if topic["notes"]:
        lines += ["What is known:"] + [f"- {item}" for item in topic["notes"]]
    if topic["progress"]:
        lines += ["Progress so far:"] + [f"- {entry['text']}" for entry in topic["progress"]]
    if topic["links"]:
        lines += ["Where to look:"] + [f"- {item}" for item in topic["links"]]
    lines.append("You may edit files to finish the goal." if edits else
                 "Work read-only: investigate and report, change nothing.")
    lines.append("Report what you found, what you decided, and anything that needs the user, in short lines.")
    print("\n".join(lines))
    return 0


def carry(state, session, source, dismiss):
    other = tree.load(source)
    if not other["topics"]:
        return fail(f"no topics in session {source}")
    other["carried"] = True
    tree.save(source, other)
    if dismiss:
        print(f"dismissed {source}")
        return 0
    keep = {topic["id"] for topic in tree.open_only(other)["topics"]}
    start = max((topic["id"] for topic in state["topics"]), default=0)
    new_ids = {}
    for topic in other["topics"]:
        if topic["id"] in keep or topic["status"] == "parked":
            start += 1
            new_ids[topic["id"]] = start
            copy = dict(topic, id=start, parent=new_ids.get(topic["parent"]), parked_from=None)
            copy["sessions"] = list(topic["sessions"])
            touch(copy, session)
            state["topics"].append(copy)
    print(f"carried {len(new_ids)} topics from {source}")
    return 0


def words(text):
    return {word for word in re.findall(r"[\w']+", (text or "").lower()) if len(word) > 3}


def parked(limit):
    here = os.getcwd()
    branch = current_branch()
    ideas, everything = [], []
    for session, state in tree.all_states():
        for topic in state["topics"]:
            everything.append((session, topic))
            if topic["status"] == "parked":
                ideas.append((session, state, topic))

    def recurrence(session, topic):
        key = words(topic["title"]) | words(topic["raw"])
        return sum(1 for other_session, other in everything
                   if (other_session, other["id"]) != (session, topic["id"]) and key and key <= words(other["title"]) | words(" ".join(other["notes"])))

    def relevance(state, topic):
        return (state.get("cwd") == here) + (bool(branch) and f"branch: {branch}" in topic["links"])

    ranked = sorted(ideas, key=lambda item: (PRIORITIES.get(item[2]["priority"], 2), -recurrence(item[0], item[2]),
                                              -relevance(item[1], item[2]), item[2]["created"] or ""))
    if limit:
        ranked = ranked[:limit]
    if not ranked:
        print("no parked ideas")
        return 0
    print(f"Parked ideas, most valuable first ({len(ranked)} of {len(ideas)})")
    for session, state, topic in ranked:
        extra = f" · priority {topic['priority']}" if topic["priority"] else ""
        print(f"- {topic['title']}  ({session}#{topic['id']}{extra})")
    return 0


def find(query):
    rows = [(session, topic) for session, state in tree.all_states() for topic in state["topics"]]
    terms = [term for term in re.findall(r"[\w']+", query.lower()) if len(term) > 2]
    if not rows or not terms:
        print("no past topics match")
        return 0
    try:
        database = sqlite3.connect(":memory:")
        database.execute("create virtual table topics using fts5(key, title, body)")
        for session, topic in rows:
            body = " ".join(topic["notes"] + [entry["text"] for entry in topic["progress"]] + [topic["raw"] or ""])
            database.execute("insert into topics values (?, ?, ?)", (f"{session}#{topic['id']}", topic["title"], body))
        match = " OR ".join(f'"{term}"' for term in terms)
        keys = [key for (key,) in database.execute(
            "select key from topics where topics match ? order by bm25(topics) limit 10", (match,))]
    except sqlite3.OperationalError:
        scored = [(sum(term in (topic["title"] + " ".join(topic["notes"])).lower() for term in terms), f"{session}#{topic['id']}")
                  for session, topic in rows]
        keys = [key for score, key in sorted(scored, reverse=True) if score][:10]
    by_key = {f"{session}#{topic['id']}": topic for session, topic in rows}
    if not keys:
        print("no past topics match")
        return 0
    for key in keys:
        topic = by_key[key]
        last = max([topic["created"] or "", topic["closed"] or ""] + [entry["at"] for entry in topic["progress"]])
        print(f"{key} {topic['title']} · {topic['status']} · last {last[:10]}")
    return 0


def back(state, session, source, topic_id, mode):
    other = tree.load(source)
    old = tree.find(other, topic_id)
    if old is None:
        return fail(f"no topic {source}#{topic_id}")
    if mode == "resume":
        for past in old["sessions"] or [source]:
            print(f"claude --resume {past}")
        return 0
    topic = new_topic(state, old["title"], None, session)
    add_link(topic, f"from: {source}#{topic_id}")
    if mode == "progress":
        topic["notes"] = list(old["notes"])
        topic["progress"] = [dict(entry) for entry in old["progress"]]
        for item in old["links"]:
            add_link(topic, item)
        topic["priority"] = old["priority"]
    enter(state, topic)
    print(tree.describe(topic))
    return 0


def standup(since):
    today = datetime.datetime.fromisoformat(tree.now()).date()
    since = since or (today - datetime.timedelta(days=1)).isoformat()
    done, still_open = [], []
    for _, state in tree.all_states():
        touched = [topic for topic in state["topics"] if max(topic["created"] or "", topic["closed"] or "") >= since]
        if not touched:
            continue
        for topic in state["topics"]:
            root = tree.ancestors(state, topic)[0]
            label = topic["title"] if root is topic else f"{topic['title']} ({root['title']})"
            has_open_child = any(child["parent"] == topic["id"] and child["status"] == "open" for child in state["topics"])
            if topic["status"] == "done" and (topic["closed"] or "") >= since:
                done.append(label)
            elif topic["status"] == "open" and not has_open_child:
                still_open.append(label)
    lines = [f"Since {since}", "", "Done"] + [f"- {label}" for label in done or ["nothing"]]
    lines += ["", "Open"] + [f"- {label}" for label in still_open or ["nothing"]]
    print("\n".join(lines))
    return 0


def stats():
    forks, share, holes, depths, follow = {}, {}, [], [], {}
    for _, state in tree.all_states():
        for topic in state["topics"]:
            if topic["status"] != "parked" and topic["created"]:
                day = topic["created"][:10]
                forks[day] = forks.get(day, 0) + 1
        for root in [topic for topic in state["topics"] if topic["parent"] is None and topic["status"] != "parked"]:
            subtree = [topic for topic in state["topics"] if tree.ancestors(state, topic)[0] is root]
            messages = sum(topic["messages"] for topic in subtree)
            share[root["title"]] = share.get(root["title"], 0) + messages
            depths.append(max(len(tree.ancestors(state, topic)) for topic in subtree))
            statuses = [topic["status"] for topic in subtree]
            counts = follow.setdefault(root["title"], {"done": 0, "dropped": 0, "open": 0})
            for status in counts:
                counts[status] += statuses.count(status)
            results = statuses.count("done") + sum(len(topic["notes"]) + len(topic["progress"]) for topic in subtree)
            holes.append((root["title"], messages, len(subtree), results))
    if not forks:
        print("no history yet")
        return 0
    busy = [messages for _, messages, _, _ in holes if messages]
    middle = statistics.median(busy) if busy else 0
    rabbit = [title for title, messages, size, results in holes if size > 1 and messages and messages >= middle and not results]
    habit = round(statistics.median(depths)) if depths else 0
    lines = ["Forks per day", "", "| Day | Forks |", "|---|---|"]
    lines += [f"| {day} | {count} |" for day, count in sorted(forks.items())]
    lines += ["", "Mind share", "", "| Topic | Messages |", "|---|---|"]
    lines += [f"| {title} | {count} |" for title, count in sorted(share.items(), key=lambda item: -item[1])]
    lines += ["", "Follow-through", "", "| Topic | Done | Dropped | Open |", "|---|---|---|---|"]
    lines += [f"| {title} | {count['done']} | {count['dropped']} | {count['open']} |" for title, count in follow.items()]
    lines += ["", "Rabbit holes (many messages, nothing finished or noted)"] + [f"- {title}" for title in rabbit or ["none"]]
    lines += ["", f"Depth habit: you usually go {habit} levels deep."]
    suggestions = []
    limit = tree.option("DEPTH_ALERT", 3)
    if habit and limit and habit < limit:
        suggestions.append(f"- Set the depth alert to {habit} levels, your usual depth, so the alert comes before the dive.")
    suggestions += [f"- Turn on focus when working on {title}: it turned into a rabbit hole before." for title in rabbit]
    lines += ["", "Suggestions"] + (suggestions or ["- none"])
    print("\n".join(lines))
    return 0


def main(arguments):
    parser = argparse.ArgumentParser(prog="topics.py")
    parser.add_argument("--session")
    commands = parser.add_subparsers(dest="command", required=True)
    fork_parser = commands.add_parser("fork")
    fork_parser.add_argument("title")
    fork_parser.add_argument("--under")
    fork_parser.add_argument("--reason")
    for name in ["done", "drop"]:
        commands.add_parser(name).add_argument("id", type=int)
    now_parser = commands.add_parser("now")
    now_parser.add_argument("id", type=int)
    now_parser.add_argument("--reason")
    rename_parser = commands.add_parser("rename")
    rename_parser.add_argument("id", type=int)
    rename_parser.add_argument("title")
    for name in ["note", "progress"]:
        sub = commands.add_parser(name)
        sub.add_argument("text")
        sub.add_argument("--on", type=int)
    link_parser = commands.add_parser("link")
    link_parser.add_argument("kind")
    link_parser.add_argument("value")
    link_parser.add_argument("--on", type=int)
    commands.add_parser("park").add_argument("text")
    focus_parser = commands.add_parser("focus")
    focus_parser.add_argument("id", type=int, nargs="?")
    focus_parser.add_argument("--off", action="store_true")
    priority_parser = commands.add_parser("priority")
    priority_parser.add_argument("id", type=int)
    priority_parser.add_argument("level", choices=["now", "today", "later"])
    elect_parser = commands.add_parser("elect")
    elect_parser.add_argument("id", type=int)
    elect_parser.add_argument("--off", action="store_true")
    delegation_parser = commands.add_parser("delegation")
    delegation_parser.add_argument("id", type=int)
    delegation_parser.add_argument("status", choices=["running", "needs-input", "done"])
    delegation_parser.add_argument("--agent")
    brief_parser = commands.add_parser("brief")
    brief_parser.add_argument("id", type=int)
    brief_parser.add_argument("--edits", action="store_true")
    carry_parser = commands.add_parser("carry")
    carry_parser.add_argument("source")
    carry_parser.add_argument("--dismiss", action="store_true")
    back_parser = commands.add_parser("back")
    back_parser.add_argument("source")
    back_parser.add_argument("id", type=int)
    back_parser.add_argument("--mode", choices=["fresh", "progress", "resume"], default="progress")
    commands.add_parser("show").add_argument("--ids", action="store_true")
    commands.add_parser("standup").add_argument("--since")
    commands.add_parser("parked")
    commands.add_parser("find").add_argument("query")
    commands.add_parser("stats")
    options = parser.parse_args(arguments)

    global_commands = {
        "standup": lambda: standup(options.since),
        "parked": lambda: parked(tree.option("REMINDER_LIMIT")),
        "find": lambda: find(options.query),
        "stats": stats,
    }
    if options.command in global_commands:
        return global_commands[options.command]()
    if not options.session:
        return fail("--session is required")
    session = options.session
    state = tree.load(session)
    if options.command == "show":
        print(tree.render(state, options.ids), end="")
        return 0
    if options.command == "brief":
        return brief(state, options.id, options.edits)
    try:
        code = {
            "fork": lambda: fork(state, session, options.title, options.under, options.reason),
            "done": lambda: close(state, options.id, "done"),
            "drop": lambda: close(state, options.id, "dropped"),
            "now": lambda: now(state, session, options.id, options.reason),
            "rename": lambda: rename(state, options.id, options.title),
            "note": lambda: note(state, session, options.text, options.on),
            "progress": lambda: progress(state, session, options.text, options.on),
            "link": lambda: link(state, options.kind, options.value, options.on),
            "park": lambda: park(state, session, options.text),
            "focus": lambda: focus(state, options.id, options.off),
            "priority": lambda: priority(state, options.id, options.level),
            "elect": lambda: elect(state, options.id, options.off),
            "delegation": lambda: delegation(state, options.id, options.status, options.agent),
            "carry": lambda: carry(state, session, options.source, options.dismiss),
            "back": lambda: back(state, session, options.source, options.id, options.mode),
        }[options.command]()
    except ValueError:
        return fail("ids are numbers, or root")
    if code == 0:
        tree.save(session, state)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
