import { atom, read, update } from 'claude-code'
import type { Register, RenderChildren } from 'claude-code'

import type { TopicId, Version } from '../types'

type Status = 'open' | 'done' | 'dropped' | 'parked'
type Topic = {
  id: number
  title: string
  parent: number | null
  status: Status
  delegable?: boolean
  delegation?: { status: 'running' | 'needs-input' | 'done'; agent?: string | null } | null
  sessions?: string[]
}
type State = { current: number | null; focus?: number | null; topics: Topic[] }

const isCollapsed = atom({ plugin: 'sidequest', key: 'isCollapsed' } as const, false)
const isParkedOpen = atom({ plugin: 'sidequest', key: 'isParkedOpen' } as const, false)
const version = atom({ plugin: 'sidequest', key: 'version' } as const, 0 as Version)
const toggled = atom({ plugin: 'sidequest', key: 'toggled' } as const, [] as TopicId[])

const LOOKS = {
  current: { glyph: '▶', color: 'cyan' },
  open: { glyph: '☐', color: 'yellow' },
  done: { glyph: '✓', color: 'green' },
  dropped: { glyph: '✗', color: 'gray' },
  parked: { glyph: '◇', color: 'magenta' },
  running: { glyph: '⇢', color: 'blue' },
  waiting: { glyph: '!', color: 'red' },
} as const

const find = (state: State, id: number | null | undefined) => state.topics.find(topic => topic.id === id)

function chain(state: State, topic: Topic | undefined): Topic[] {
  const result: Topic[] = []
  while (topic) {
    result.unshift(topic)
    topic = find(state, topic.parent)
  }
  return result
}

function descendants(state: State, id: number): Topic[] {
  const children = state.topics.filter(topic => topic.parent === id)
  return children.flatMap(child => [child, ...descendants(state, child.id)])
}

function foldedByDefault(state: State, topic: Topic): boolean {
  const below = descendants(state, topic.id)
  return below.length > 0 && topic.status !== 'open' && below.every(child => child.status !== 'open')
}

function look(state: State, topic: Topic) {
  if (topic.delegation?.status === 'running') return LOOKS.running
  if (topic.delegation?.status === 'needs-input') return LOOKS.waiting
  if (topic.id === state.current) return LOOKS.current
  return LOOKS[topic.status]
}

const TOOL = 'mcp__sidequest__topics'

export const register: Register = (on, options) => {
  const depthMatch = /\d+/.exec(String(options.depth_alert ?? ''))
  const depthAlert = String(options.depth_alert) === 'off' ? Infinity : depthMatch ? Number(depthMatch[0]) : 3

  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: 'topics',
      description:
        'Records and reads the sidequest topic tree for this session. Pass the command and its arguments as args, ' +
        'e.g. ["fork", "Fix the login timeout"] (under the current topic), ["done", "3"], ["park", "cache price lookups"], ["show", "--ids"]. ' +
        'Commands: fork, done, drop, now, rename, note, progress, link, park, focus, priority, elect, brief, delegation, carry, back, show, find, parked, standup, stats.',
      inputSchema: {
        type: 'object',
        properties: { args: { type: 'array', items: { type: 'string' }, description: 'The command, then its arguments' } },
        required: ['args'],
      },
    })
    return next(e)
  })

  on('tool.call', { tool: TOOL }, async ($, e) => {
    const raw = e['args']
    const args = Array.isArray(raw) ? raw.map(String) : []
    const session = await $.session.id()
    const run = await $.process.run(['python3', `${$.plugin.root}/scripts/topics.py`, '--session', session, ...args])
    await update($, version, value => value + 1)
    const text = [run.stdout.trim(), run.stderr.trim()].filter(Boolean).join('\n') || 'ok'
    return run.exitCode === 0 ? { result: text } : { result: text, isError: true }
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    if (e.command.includes('topics.py')) {
      await update($, version, value => value + 1)
    }
    return result
  }).catch(($, e, next) => next(e))

  on('prompt.submit', async ($, e, next) => {
    if (!e.text.startsWith('+ ')) {
      return next(e)
    }
    const session = await $.session.id()
    const result = await $.process.run(
      ['python3', `${$.plugin.root}/scripts/topics.py`, '--session', session, 'park', e.text.slice(2)])
    await update($, version, value => value + 1)
    $.ui.toast(result.exitCode === 0 ? `parked: ${e.text.slice(2)}` : result.stderr.trim())
    return { drop: 'parked by sidequest' }
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (!e.agentId) {
      return result
    }
    const session = await $.session.id()
    const path = `${await $.env.get('HOME')}/.claude/sidequest/${session}.json`
    let state: State
    try {
      state = JSON.parse(await $.fs.read(path))
    } catch {
      return result
    }
    const topic = state.topics.find(item => item.delegation?.status === 'running' && item.delegation.agent === e.agentId)
    if (!topic) {
      return result
    }
    const cli = ['python3', `${$.plugin.root}/scripts/topics.py`, '--session', session]
    const findings = 'answer' in e && typeof e.answer === 'string' ? e.answer.trim() : ''
    if (findings) {
      await $.process.run([...cli, 'note', `sub-agent: ${findings.slice(0, 2000)}`, '--on', String(topic.id)])
    }
    const needsInput = /needs? (the )?user|question for (the )?user|blocked/i.test(findings)
    await $.process.run([...cli, 'delegation', String(topic.id), needsInput ? 'needs-input' : 'done'])
    await update($, version, value => value + 1)
    $.ui.toast(`sub-agent ${needsInput ? 'needs you' : 'finished'}: ${topic.title}`)
    return result
  }).catch(($, e, next) => next(e))

  on('prompt.edit', async ($, e, next) => {
    const result = await next(e)
    const after = e.text.slice(0, e.start) + e.inputText + e.text.slice(e.end)
    const before = e.text.trim()
    if (after.trim() === '' && before.includes(' ') && !before.startsWith('/') && !before.startsWith('+ ')) {
      const session = await $.session.id()
      await $.process.run(['python3', `${$.plugin.root}/scripts/topics.py`, '--session', session, 'park', before])
      await update($, version, value => value + 1)
      $.ui.toast('cleared draft parked as an idea')
    }
    return result
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    await read($, version)
    const session = await $.session.id()
    const path = `${await $.env.get('HOME')}/.claude/sidequest/${session}.json`
    let state: State
    try {
      state = JSON.parse(await $.fs.read(path))
    } catch {
      state = { current: null, topics: [] }
    }
    if (e.props.hasSurvey) {
      return next(e)
    }
    if (state.topics.length === 0) {
      const { Box: EmptyBox, Text: EmptyText } = $.ui.resolve(e)
      return (
        <EmptyBox key="empty" borderStyle="round" borderColor="cyan" paddingX={1}>
          <EmptyText dimColor>sidequest · no topics yet · start with + to park an idea</EmptyText>
        </EmptyBox>
      )
    }

    const cli = ['python3', `${$.plugin.root}/scripts/topics.py`, '--session', session]
    const run = async (...args: string[]) => {
      const result = await $.process.run([...cli, ...args])
      await update($, version, value => value + 1)
      if (result.exitCode !== 0) {
        $.ui.toast(result.stderr.trim())
      }
      return result
    }
    const delegate = async (topic: Topic) => {
      const brief = await $.process.run([...cli, 'brief', String(topic.id)])
      const started = await $.agent.spawn({ prompt: brief.stdout, description: `sidequest: ${topic.title}` })
      await run('delegation', String(topic.id), 'running', ...(started.agentId ? ['--agent', started.agentId] : []))
    }

    const elements = $.ui.resolve(e)
    const { Box, Text, Button } = elements
    const Input = 'Input' in elements ? elements.Input : null
    const collapsed = await read($, isCollapsed)
    const parkedOpen = await read($, isParkedOpen)
    const flipped = await read($, toggled)
    const current = find(state, state.current)
    const focus = find(state, state.focus)
    const path_ = chain(state, current)
    const levels = path_.length
    const onPath = new Set(path_.map(topic => topic.id))
    const count = (status: Status) => state.topics.filter(topic => topic.status === status).length
    const ideas = state.topics.filter(topic => topic.status === 'parked')
    const isStale = (topic: Topic) => topic.status === 'open' && !(topic.sessions ?? []).includes(session)
    const columns = e.viewport?.columns ?? Infinity
    const fit = (text: string, room: number) => (text.length <= room ? text : `${text.slice(0, Math.max(1, room - 1))}…`)

    const counts = `☐ ${count('open')} ✓ ${count('done')}${ideas.length ? ` ◇ ${ideas.length}` : ''}`
    const crumb = path_.map(topic => topic.title).join(' › ')
    const fixed = '[ − ] sidequest '.length + counts.length + ' · depth 99'.length + 4
    const isTiny = columns < '[ − ] sidequest '.length + counts.length + 4
    const crumbRoom = Math.max(8, columns - fixed - 4)

    const header = (
      <Box flexDirection="row" gap={1}>
        <Button key="collapse" hotkey="c" label={collapsed ? '+' : '−'} onPress={() => update($, isCollapsed, value => !value)} />
        <Text bold color="cyan">sidequest</Text>
        <Text color="yellow">☐ {count('open')}</Text>
        <Text color="green">✓ {count('done')}</Text>
        {ideas.length > 0 ? <Text color="magenta">◇ {ideas.length}</Text> : null}
        {current ? <Text color={levels >= depthAlert ? 'red' : 'cyan'}>▶ {fit(crumb, crumbRoom)} · depth {levels}</Text> : null}
      </Box>
    )
    const focusLine = focus ? (
      <Box flexDirection="row" gap={1}>
        <Text color="red" bold>◉ focus: {fit(focus.title, Math.max(8, columns - 20))}</Text>
        <Button key="unfocus" plain dimColor label="end focus" onPress={() => run('focus', '--off')} />
      </Box>
    ) : null
    const frame = (children: RenderChildren) => (
      <Box flexDirection="column" borderStyle="round" borderColor={focus ? 'red' : 'cyan'} paddingX={1}>{children}</Box>
    )
    if (collapsed || isTiny) {
      return frame(isTiny ? <Text color="cyan">▶ {fit(current ? current.title : 'sidequest', Math.max(4, columns - counts.length - 8))} · {counts}</Text> : [header, focusLine])
    }

    const isFolded = (topic: Topic) => {
      const byDefault = foldedByDefault(state, topic) || (current !== undefined && !onPath.has(topic.id) && topic.id !== state.focus)
      return byDefault !== flipped.includes(topic.id)
    }
    const flip = (id: number) =>
      update($, toggled, list => (list.includes(id) ? list.filter(item => item !== id) : [...list, id]))

    const rows: RenderChildren[] = []
    const row = (key: string, prefix: string, isLast: boolean, lead: RenderChildren, body: RenderChildren) =>
      rows.push(
        <Box key={key} flexDirection="row">
          <Text dimColor>{prefix + (isLast ? '└─' : '├─')}</Text>
          {lead}
          {body}
        </Box>,
      )
    const walk = (parent: number | null, prefix: string) => {
      const children = state.topics.filter(topic => topic.parent === parent && topic.status !== 'parked')
      const closedLeaves = children.filter(topic => topic.status !== 'open' && !descendants(state, topic.id).length && topic.id !== state.current)
      const showClosed = flipped.includes(-(parent ?? 0) - 1) || closedLeaves.length < 2
      const visible = showClosed ? children : children.filter(topic => !closedLeaves.includes(topic))
      const groupKey = -(parent ?? 0) - 1
      visible.forEach((topic, index) => {
        const isLast = index === visible.length - 1 && (showClosed || closedLeaves.length === 0)
        const hidden = descendants(state, topic.id)
        const folded = hidden.length > 0 && isFolded(topic)
        const hiddenOpen = hidden.filter(child => child.status === 'open').length
        const style = look(state, topic)
        const canDelegate = topic.delegable && topic.status === 'open' && !topic.delegation
        const room = columns - prefix.length - 18 - (canDelegate ? 14 : 0) - (folded ? 14 : 0)
        row(`topic-${topic.id}`, prefix, isLast,
          hidden.length > 0
            ? <Button key={`fold-${topic.id}`} dimColor label={folded ? '+' : '−'} onPress={() => flip(topic.id)} />
            : <Text dimColor>─────</Text>,
          <Box flexDirection="row">
            <Text color={topic.id === state.focus ? 'red' : style.color}> {style.glyph} </Text>
            <Button key={`switch-${topic.id}`} plain dimColor={topic.status !== 'open' || isStale(topic)} label={fit(topic.title, Math.max(8, room))}
              onPress={() => run('now', String(topic.id))} />
            {folded ? <Text dimColor> (+{hidden.length}{hiddenOpen > 0 ? `, ${hiddenOpen} open` : ''})</Text> : null}
            {canDelegate ? <Button key={`delegate-${topic.id}`} label={topic.title.length > room ? '⇢' : '⇢ delegate'} onPress={() => delegate(topic)} /> : null}
          </Box>)
        if (!folded) {
          walk(topic.id, prefix + (isLast ? '    ' : '│   '))
        }
      })
      if (closedLeaves.length >= 2) {
        row(`closed-${groupKey}`, prefix, true,
          <Button key={`fold-closed-${groupKey}`} dimColor label={showClosed ? '−' : '+'} onPress={() => flip(groupKey)} />,
          <Text dimColor color="green"> ✓ {closedLeaves.length} finished</Text>)
      }
    }
    walk(null, '')

    const parkedSection = ideas.length > 0 ? (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          <Button key="parked" hotkey="p" label={parkedOpen ? '−' : '+'} onPress={() => update($, isParkedOpen, value => !value)} />
          <Text color="magenta">◇ parked ideas ({ideas.length})</Text>
        </Box>
        {parkedOpen ? ideas.map(idea => (
          <Box key={`idea-${idea.id}`} flexDirection="row">
            <Text dimColor>      ◇ </Text>
            <Button key={`open-${idea.id}`} plain label={fit(idea.title, Math.max(8, columns - 12))} onPress={() => run('now', String(idea.id))} />
          </Box>
        )) : null}
      </Box>
    ) : null

    const actionBar = '[ ↑ up ] [ ✓ done ] [ ✗ drop ] [ ◉ focus ]'
    const compact = columns < actionBar.length + 4
    return frame([
      header,
      focusLine,
      <Box key="tree" flexDirection="column" marginTop={1}>{rows}</Box>,
      parkedSection,
      <Box key="actions" flexDirection="row" gap={1} marginTop={1}>
        {current ? <Button key="up" hotkey="u" label={compact ? '↑' : '↑ up'} onPress={() => current.parent !== null && run('now', String(current.parent))} /> : null}
        {current ? <Button key="done" hotkey="d" label={compact ? '✓' : '✓ done'} onPress={() => run('done', String(current.id))} /> : null}
        {current ? <Button key="drop" hotkey="x" label={compact ? '✗' : '✗ drop'} onPress={() => run('drop', String(current.id))} /> : null}
        {current && !focus ? <Button key="focus" hotkey="f" label={compact ? '◉' : '◉ focus'} onPress={() => run('focus', String(current.id))} /> : null}
      </Box>,
      Input ? (
        <Box key="capture" borderStyle="single" borderDimColor paddingX={1}>
          <Input key="capture" placeholder="capture an idea, Enter to park it" submitLabel="park"
            onSubmit={(value: string) => { if (value.trim()) { void run('park', value.trim()) } }} />
        </Box>
      ) : null,
    ])
  })
}
