# sidequest

[![checks](https://github.com/imhalawa/sidequest/actions/workflows/checks.yml/badge.svg)](https://github.com/imhalawa/sidequest/actions/workflows/checks.yml)

A live topic tree for Claude Code. It shows where a session forked off, keeps urgent work in front, and parks new ideas instead of losing them.

```
[ − ]  sidequest  ☐ 4  ✓ 3  ◇ 1  │ Fix the checkout timeout › Read the gateway logs · depth 2

├─[ − ] ☐ Fix the checkout timeout
│   ├────── ▶ Read the gateway logs
│   ├────── ☐ Compare one order with the report  [ ⇢ delegate ]
│   └─[ + ] ✓ 2 finished
└─[ + ] ☐ Plan the team offsite  +2 · 1 open
[ + ] ◇ parked ideas 1

[ ↑ up ] [ ✓ done ] [ ✗ drop ] [ ◉ focus ]
[ ◇ capture ] [ ✓ hide finished ]
```

## Quick start

1. In a Claude Code terminal session, run:
   ```
   /plugin install sidequest --marketplace imhalawa/sidequest
   ```
2. Answer `y` to add the marketplace, pick a scope, and keep the default settings.
3. Start working. Claude records topics from your first message, and the tree appears.

Requires `python3` on the `PATH`.

## Features

### Track

| Feature | What it does |
|---|---|
| Topic tree | Every subject and side question becomes a topic, nested where it forked off; work on the same PR, ticket, or goal goes under that topic |
| Clear titles | Each title names the action and what it acts on, so it reads on its own a day later |
| Notes and links | Findings, decisions, Jira keys, PRs, Slack threads, and files stay on their topic; a new topic links its git branch by itself |
| Progress | Leaving a topic saves where it stood: done, decided, ruled out, next step |
| Depth alert | When you are 3 levels deep, Claude says so and names where you started |

### Focus

| Feature | What it does |
|---|---|
| Focus mode | `◉ focus` pins an urgent topic, pauses the one you were on, and starts Claude on it right away |
| Guarded switching | While focus is on, leaving needs a reason, and the reason is saved on the focus topic |
| Resume | `end focus`, or finishing the focus topic, brings Claude back to the paused topic from its last progress entry |

### Capture

| Feature | What it does |
|---|---|
| Parking | New ideas during focus, and side thoughts inside a task message, are parked as `◇` instead of derailing you |
| `◇ capture` | One press opens a 3-line box, up to 255 characters; Enter parks the idea without reaching Claude |
| `◇ park` | Parks the topic you are on with its whole branch, so the tree stays about what you are doing now |
| Bringing one back | Clicking a parked idea asks first, then restores it under its old parent when that is still open |
| `+ ` prefix | A message that starts with `+ ` is parked instead of sent |
| Lost-thought recovery | A draft of more than one word that you clear without sending is parked |

### Remember

| Feature | What it does |
|---|---|
| Carry-over | A new session in the same folder offers the last session's open topics |
| Past topics | Bring up something you worked on before, and Claude offers: start fresh, continue with the saved progress, or resume the old conversation |
| Reminders | At natural breaks, Claude lists parked ideas, most valuable first: your priority, then how often the idea came back, then how close it is to your current work |
| Priority | A new topic gets one quick question, now, today, or later, as a picker when the question tool is available |

### Review

| Feature | What it does |
|---|---|
| Standup | Done and open topics since yesterday, across sessions |
| Stats | Forks per day, where your attention went, rabbit holes with no result, and setting suggestions from your own habits |

### Delegate

| Feature | What it does |
|---|---|
| Election | Claude marks topics a sub-agent could finish alone from their notes and links |
| `⇢ delegate` | Appears only on elected topics; one press starts a sub-agent with the topic's brief, and its findings come back as notes |

## The panel

| Where | Shows |
|---|---|
| Terminal | The tree in a panel above the prompt |
| Desktop app | The tree in a side panel that opens with the session, plus a one-line strip above the prompt with `open topics`. `/sidequest` reopens the side panel |

### Glyphs

| Glyph | Meaning |
|---|---|
| `☐` | Open |
| `▶` | Current topic |
| `✓` | Done |
| `✗` | Dropped |
| `◇` | Parked idea |
| `⇢` | A sub-agent is working on it |
| `!` | A sub-agent needs you |
| `◉` | Focus |

### Buttons and keys

Keys work once the panel has the focus (ctrl+x tab).

| Button | Key | Does |
|---|---|---|
| `[ − ]` / `[ + ]` in the header | `c` | Collapse or expand the panel |
| `[ − ]` / `[ + ]` next to a topic | | Fold or unfold its branch |
| A topic's title | | Switch to it; the folds stay as they are |
| `↑ up` | `u` | Go to the nearest open parent |
| `✓ done` | `d` | Finish the current topic |
| `✗ drop` | `x` | Drop the current topic and its open subtopics |
| `◇ park` | `k` | Park the current topic with its branch |
| `◉ focus` | `f` | Focus on the current topic |
| `◇ parked ideas` | `p` | Show or hide parked ideas; clicking one asks before bringing it back |
| `◇ capture` | `i` | Open the capture box |
| `✓ hide finished` | `h` | Hide or show finished topics |
| `⌨ shortcuts` | `s` | Show every shortcut in one line |
| `⇢ delegate` | | Start a sub-agent on an elected topic |

### What it keeps you from doing by accident

| Case | Behaviour |
|---|---|
| Finished, dropped, or delegated topics | Shown, not clickable |
| Focus is on | Only topics inside the focus topic are clickable |
| `✓ done` with open subtopics | Hidden until the subtopics are finished or dropped |
| Reopening a finished topic | Only when you ask for it |

The panel fits the terminal: long titles shorten with `…`, buttons shrink to their glyphs, and a very narrow terminal gets one line. A session with no topics shows `sidequest · no topics yet`.

## Settings

Open `/plugin` → Installed → sidequest.

| Setting | Choices | Default |
|---|---|---|
| Depth alert | 2 levels: strict · 3 levels: balanced · 4 levels: relaxed · off | 3 levels: balanced |
| Parked ideas per reminder | top 3 · top 5 · all | all |

`stats` suggests a depth alert from your own history.

## Reporting a bug

1. Run `/sidequest-report`, or `/sidequest-report redact` to hide titles and notes.
2. Attach the file whose path it prints to your issue.

The file holds the plugin version, every panel and Claude action with its result, and the topic tree. Actions are logged per session in `~/.claude/sidequest/logs/`, tagged `panel`, `claude`, `capture`, `draft`, or `sub-agent`.

## Commands

Claude records through the plugin's own `topics` tool, so Bash sandboxing never blocks it. The same commands work from a shell: `python3 scripts/topics.py --session ID <command>`.

| Command | Does |
|---|---|
| `fork "<title>" [--under <id>\|root]` | New topic |
| `done <id>` · `drop <id>` · `now <id> [--reopen]` · `rename <id> "<title>"` · `move <id> --under <id>\|root` | Change a topic |
| `note` · `progress` · `link <kind> <value>` | Add to a topic; `--on <id>` for another one |
| `park "<idea>"` · `shelve <id>` · `unpark <id>` · `focus <id> \| --off` · `priority <id> now\|today\|later` | Focus and parking |
| `elect <id>` · `brief <id>` · `delegation <id> <status>` | Delegation |
| `carry <session>` · `back <session> <id> --mode fresh\|progress\|resume` | Past sessions |
| `show [--ids]` · `report [--redact]` | The tree, a bug report |
| `find "<words>"` · `parked` · `standup` · `stats` | Across all sessions; no `--session` needed |

## Storage

One JSON file per session in `~/.claude/sidequest/`, never pruned. `SIDEQUEST_HOME` moves it.

## Development

| Check | Command |
|---|---|
| Unit tests | `python3 -B -m unittest discover -s tests -v` |
| Panel tests | `claude plugin test .` |
| Validation | `claude plugin validate .` |
| Evals | `claude plugin eval . --allow-tools mcp__sidequest__topics Agent` |

`SIDEQUEST_NOW` fixes the clock in tests. `EVAL_SIDEQUEST_SEED` starts an eval session from a JSON file, or from a folder of session files whose `current.json` is the new session.

See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

## License

MIT
