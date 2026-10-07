import json
import os
import shutil
import subprocess
import sys

import tree

INSTRUCTIONS = """sidequest: this session keeps a tree of the topics the user moves through, so they can see where they forked off and what is still open.
Record every change with the CLI below, before you answer:
- The user starts a new subject or a side question: fork it. By default it goes under the current topic. Work on the same PR, ticket, branch, repo task, or goal as an open topic is a child of that topic: use --under <its id>. Use --under root only when the subject has nothing to do with any open topic. When fork prints a related open topic, decide, and run move if it belongs there.
- A topic is finished, its question answered or its task done: mark it done.
- The user goes back to an earlier topic: switch to it with now, then use the notes and links it prints. Never fork a topic that already exists. A finished topic stays finished; add --reopen only when the user asks to reopen it.
- A topic with open subtopics cannot be marked done: finish or drop the subtopics first. Dropping a topic drops its open subtopics too.
- The user abandons a topic ("forget that", "not needed"): drop it.
- A finding, decision, or next step worth keeping: note it on its topic, one short line.
- A Jira key, PR, Slack thread, or file the topic is about: link it.
- A follow-up on the current topic, or small talk, records nothing.
- A message that mixes the current task with a side thought ("fix this, oh and we should cache X someday"): park the side thought in the user's words, then answer the task. A message that is only a new subject is forked, not parked.
- A message that starts with [sidequest] comes from the user's panel, not from a typed request: act on it right away, without asking for a go. Focus set from the panel arrives this way, either as its own message or attached to the user's message.
- Something urgent: pin it with focus. While focus is on, a new idea outside the focus topic is parked, not forked: run park with the user's words, answer in one line ("parked: ..."), and go back to the focus topic. Leaving the focus topic needs the user's reason: ask why it is more urgent, then pass it as --reason. Never invent a reason.
- Leaving a topic, finishing one, or ending the session: save progress on it: what was done, decided, ruled out, and the next step, one short line each.
- A parked idea with unclear words: at the next natural break, rename it into a clear title; the original words are kept. Ask at most one question, only if it stays unclear.
- Every time you fork a topic the user brought up, ask its priority in the same turn, every time: call the AskUserQuestion tool with the choices now, today, and later; if that tool is not available, end your reply with the one line "Priority: now, today, or later?". Record the answer with priority.
- Ask every other question that has choices (the three ways back, why leaving focus is more urgent) with the AskUserQuestion tool too, one question per call; without the tool, ask it in one line at the end of your reply.
- The user parks a topic they are on ("park this", "put this aside"): run shelve <id>. A parked topic comes back only when the user asks: run unpark <id>.
- The user brings up something that may have been worked on before: run find with its key words. On a real match, offer three ways back in one line: start fresh, continue with the saved progress, or resume the old conversation; then run back with the chosen --mode.
- A topic whose notes and links are enough for a sub-agent to work alone: elect it, silently. Only when the user asks to delegate an elected topic: run brief, start a background sub-agent with it, and run delegation <id> running; when it reports, save its findings as notes and run delegation <id> done, or needs-input.
- Natural breaks are: the focus topic is done, a topic is done, or the session starts. Only then mention parked ideas, most valuable first, using parked.
- A new question about an earlier, still-open topic forks under that topic with --under <its id>, not under the current topic and not at the root.
- One message can need several commands: two new questions are two forks; "that's done, now X" is done then fork. Record each change as its own call.
Titles name the action and what it acts on, specific enough to read on their own a day later, in one short line in the user's language: "Fix the checkout timeout for 325 failed orders", not "CSV" or "check the database". When a topic turns out to be about something more specific, rename it.
Record silently: never mention the recording or show #ids in your reply. If the CLI reports an unknown id, run show --ids and retry.
When the user asks to see the topics, run show and print its output in a ``` code block. When they ask for a standup, run standup and print its output unchanged in a ``` code block. When they report a sidequest bug, run report (add --redact if they want titles hidden) and give them the file path.
The user sees the tree in a panel above the prompt, so never print it unasked. When the hook sends a depth alert, pass it on in one line.
"""


def seed(session):
    source = os.environ.get("EVAL_SIDEQUEST_SEED")
    if not source or tree.exists(session):
        return
    if not os.path.isabs(source):
        source = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), source)
    os.makedirs(tree.home(), exist_ok=True)
    if os.path.isdir(source):
        for name in os.listdir(source):
            if name.endswith(".json") and name != "current.json":
                shutil.copyfile(os.path.join(source, name), os.path.join(tree.home(), name))
        source = os.path.join(source, "current.json")
    if tree.read(source):
        shutil.copyfile(source, tree.path(session))


def carry_offer(session, cwd):
    for file in tree.sessions():
        if file == tree.path(session):
            continue
        other = tree.read(file)
        if other is None or other.get("carried") or other.get("cwd") != cwd:
            continue
        if not any(topic["status"] == "open" for topic in other["topics"]):
            continue
        source = os.path.basename(file)[:-len(".json")]
        return (f"\nThe last session in this folder left these topics open:\n{tree.render(tree.open_only(other), notes=True)}"
                f"Ask the user once, in one line, whether to carry them over. Yes: run carry {source}. "
                f"No: run carry {source} --dismiss.")
    return ""


def parked_ideas(session):
    ideas = [topic for name, state in tree.all_states() if name != session for topic in state["topics"] if topic["status"] == "parked"]
    if not ideas:
        return ""
    result = subprocess.run([sys.executable, tree.cli_path(), "parked"], capture_output=True, text=True, timeout=5)
    return f"\n\n{result.stdout.strip()}\nThe session start is a natural break: mention these in one short list, then ask what to work on."


def instructions(session):
    command = f'python3 "{tree.cli_path()}"'
    return (f"{INSTRUCTIONS}\n{tree.usage(session)}\n"
            f"{command} --session {session} carry <session> [--dismiss]   bring over a past session's open topics\n"
            f"{command} --session {session} back <session> <id> --mode fresh|progress|resume   pick up a past topic\n"
            f"{command} --session {session} brief <id> [--edits]   the sub-agent brief for a delegated topic\n"
            f"{command} --session {session} delegation <id> running|needs-input|done [--agent <id>]\n"
            f"{command} find \"<key words>\"   past topics on the same idea\n"
            f"{command} parked   parked ideas, most valuable first\n"
            f"{command} standup [--since YYYY-MM-DD]   done and open topics for a standup\n"
            f"{command} stats   forks per day, mind share, rabbit holes, and suggested settings")


def main():
    try:
        payload = json.load(sys.stdin)
        session = payload["session_id"]
    except (ValueError, KeyError, TypeError):
        return 0
    seed(session)
    state = tree.load(session)
    cwd = payload.get("cwd")
    if cwd:
        state["cwd"] = cwd
    state["started"] = True
    tree.save(session, state)
    context = instructions(session)
    if state["topics"]:
        context += f"\n\nCurrent topic map:\n{tree.render(state, ids=True, notes=True)}"
    elif payload.get("source") == "startup" and cwd:
        context += carry_offer(session, cwd)
    if payload.get("source") == "startup":
        context += parked_ideas(session)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
