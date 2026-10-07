# Changelog

## 0.4.0

- `◇ park` parks the current topic with its whole branch; it remembers where it was.
- Clicking a parked idea asks before bringing it back into the tree, under its old parent when that is still open.
- Questions with choices (priority, the three ways back, leaving focus) use the question tool when it is available.
- Nesting: work on the same PR, ticket, branch, or goal as an open topic is filed under it, not at the top. A top-level fork that shares words with an open topic prints a hint, and the new `move` command re-files it.
- `back` keeps a restored topic under the restored copy of its old parent, or under the current topic.
- `⌨ shortcuts` (key `s`) shows every panel shortcut in one line.
- The command list Claude gets with every message now includes move, progress, park, shelve, unpark, focus, priority, and elect.

## 0.3.0

- Desktop app: the topic tree lives in a side panel that opens with the session; the band above the prompt becomes one line with `open topics`. `/sidequest` reopens the panel. The terminal is unchanged.

## 0.2.0

- Focus: pressing `◉ focus` pauses the topic you were on and starts Claude on the focus topic at once; ending focus resumes the paused topic. Typing while you press it attaches the switch to your message instead.
- Panel: theme colors that read on light and dark terminals, a breadcrumb header, folds that stay put when you click, a `✓ hide finished` toggle, and a one-press `◇ capture` box up to 255 characters.
- Guards: finished, dropped, and running topics cannot be selected; `done` refuses a topic with open subtopics; `drop` drops the whole branch; `now` reopens a finished topic only with `--reopen`.
- Settings are choices: depth alert strict, balanced, relaxed, or off; parked ideas per reminder top 3, top 5, or all.
- A session with no topics shows a one-line empty state; a session that was already open when the plugin loaded gets the full instructions with its next message.
- Bug reports: every action is logged per session, and `/sidequest-report` writes one shareable file, with `redact` to hide titles and notes.

## 0.1.0

- Topic tree with fork, done, drop, now, rename, notes, links, progress, focus mode, parked ideas, quick capture, carry-over, past-session matching, stats, and elected delegation, drawn live above the prompt.
