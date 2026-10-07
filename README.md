# sidequest

Keeps a tree of the topics a session forks into, shows it live above the prompt, and keeps urgent work in front while new ideas are parked, not lost.

## Install

In a Claude Code terminal session:

```
/plugin install sidequest --marketplace imhalawa/sidequest
```

Answer `y` to add the marketplace, pick a scope, then choose the settings or keep the defaults. Requires `python3` on the `PATH`.

## What you see

A panel above the prompt:

| Part | Does |
|---|---|
| Header | Open, done, and parked counts; a breadcrumb to the current topic and its depth, red at the depth alert |
| `◉ focus` line | The pinned urgent topic, with `end focus` |
| Tree | `☐` open, `▶` current, `✓` done, `✗` dropped, `⇢` delegated, `!` needs you. `[ + ]` / `[ − ]` fold a branch. Only the path to the current topic starts open; finished siblings collapse to `✓ N finished`; open topics not touched this session are dimmed |
| `◇ parked ideas` | Ideas saved while working on something else, folded by default |
| Buttons | `↑ up`, `✓ done`, `✗ drop`, `◉ focus`, and `⇢ delegate` on topics Claude elected |
| `◇ capture` | One press opens a 3-line idea box with the cursor in it, up to 255 characters; Enter parks the idea. It never reaches Claude |

Keys, once the panel has the focus (ctrl+x tab): `c` collapse, `u` up, `d` done, `x` drop, `f` focus, `p` parked ideas, `i` capture.

A session with no topics yet shows one line, `sidequest · no topics yet`, so you can tell the plugin is loaded.

A prompt that starts with `+ ` is parked the same way and never reaches Claude. A draft of more than one word that you clear without sending is parked too, so a thought you typed and deleted is not lost.

The panel fits the terminal: titles shorten with `…`, buttons shrink to their glyphs when the full bar does not fit, and a very narrow terminal gets one line.

## What Claude does

| Moment | Claude |
|---|---|
| New subject or side question | Forks a topic with a title that names the action and its object |
| Topic finished, abandoned, or returned to | Marks it done, drops it, or switches back and reads its notes |
| Leaving a topic | Saves a progress entry: done, decided, ruled out, next step |
| A side thought inside a task message | Parks it in your words, then answers the task |
| Focus is on and a new idea comes up | Parks it, replies in one line, goes back to the focus topic |
| Leaving focus | Asks why it is more urgent; the reason is saved on the focus topic |
| 3 levels deep | Says so in one line, naming where you started |
| A topic first comes up | Asks its priority once: now, today, or later |
| Something worked on before | Finds it and offers: start fresh, continue with progress, or resume the old conversation |
| Natural break (focus done, topic done, session start) | Lists parked ideas, most valuable first |
| A topic a sub-agent could handle alone | Elects it silently; `⇢ delegate` appears. Nothing runs until you press it |

Installed or reloaded in a session that is already open, the plugin sends its full instructions with your next message.

## Rules the panel keeps

| Case | What happens |
|---|---|
| A finished, dropped, or running topic | Shown, not clickable |
| Focus is on | Only topics inside the focus topic are clickable |
| `↑ up` | Goes to the nearest open parent; hidden when there is none |
| `✓ done` on a topic with open subtopics | Hidden; the CLI refuses it and names the subtopics |
| `✗ drop` on a topic with open subtopics | Drops the whole branch |
| Clicking a topic | Switches to it; the folds you see stay as they are |
| `◉ focus` | Pauses the topic you were on and starts Claude on the focus topic at once; if you are typing, the switch rides along with your message instead |
| `end focus`, or the focus topic done | Claude resumes the paused topic from its last progress entry |

## Reporting a bug

Run `/sidequest-report` (or `/sidequest-report redact` to hide titles and notes). It writes one file with the plugin version, every panel and Claude action with its result, and the topic tree, and prints its path. Attach that file to the issue.

Every action is logged per session in `~/.claude/sidequest/logs/`, tagged with where it came from: `panel`, `claude`, `capture`, `draft`, or `sub-agent`.

## Commands

Claude records through the plugin's `topics` tool (`mcp__sidequest__topics`), so Bash sandboxing never blocks it. The same commands work from a shell, `python3 scripts/topics.py --session ID <command>`:

| Command | Does |
|---|---|
| `fork "<title>" [--under <id>\|root] [--reason]` | New topic |
| `done`, `drop`, `now <id> [--reason]`, `rename <id> "<title>"` | Change a topic |
| `note`, `progress`, `link <kind> <value>` | Add to a topic, `--on <id>` for another than the current |
| `park "<idea>"`, `focus <id> \| --off`, `priority <id> now\|today\|later` | Focus and parking |
| `elect <id> [--off]`, `brief <id> [--edits]`, `delegation <id> running\|needs-input\|done` | Delegation |
| `carry <session> [--dismiss]`, `back <session> <id> --mode fresh\|progress\|resume` | Past sessions |
| `show [--ids]` | The tree |

Without `--session`: `find "<words>"`, `parked`, `standup [--since YYYY-MM-DD]`, `stats`. With it: `report [--redact]`.

## Settings

| Setting | Choices | Default |
|---|---|---|
| Depth alert | 2 levels: strict, 3 levels: balanced, 4 levels: relaxed, off | 3 levels: balanced |
| Parked ideas per reminder | top 3, top 5, all | all |

`stats` suggests values from your own history.

## Storage

One JSON file per session in `~/.claude/sidequest/`, never pruned. `SIDEQUEST_HOME` moves it.

## Development

| Check | Command |
|---|---|
| Unit tests | `python3 -B -m unittest discover -s tests -v` |
| Panel tests | `claude plugin test .` |
| Validation | `claude plugin validate .` |
| Evals | `claude plugin eval . --allow-tools mcp__sidequest__topics Agent` |

`SIDEQUEST_NOW` fixes the clock for tests. `EVAL_SIDEQUEST_SEED` starts an eval session from a JSON file, or from a folder of session files whose `current.json` is the new session.

## License

MIT
