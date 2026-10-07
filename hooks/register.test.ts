import { expect, test } from 'claude-code/testing'

test('a prompt that starts with "+ " is parked and never reaches the model', async ($, on) => {
  let reachedModel = false
  const parked: string[][] = []
  on('session.id', () => ({ value: 'test-session' }))
  on('process.run', ($, e) => {
    parked.push([...e.argv])
    return { value: { exitCode: 0, stdout: '#1 parked', stderr: '' } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.submit', ($, e) => {
    reachedModel = true
    return { text: e.text }
  })

  const result = await $.prompt.submit({ text: '+ cache price lookups' })

  expect(reachedModel).toBe(false)
  expect(result).toEqual({ drop: 'parked by sidequest' })
  expect(parked[0].slice(-6)).toEqual(['--session', 'test-session', '--via', 'capture', 'park', 'cache price lookups'])
})

test('an ordinary prompt passes through untouched', async ($, on) => {
  on('prompt.submit', ($, e) => ({ text: e.text }))

  const result = await $.prompt.submit({ text: 'what is a GSI?' })

  expect(result).toEqual(expect.objectContaining({ text: 'what is a GSI?' }))
})

const STATE = {
  current: 2,
  focus: 1,
  topics: [
    { id: 1, title: 'Fix the production outage', parent: null, status: 'open' },
    { id: 2, title: 'Restart the web pods', parent: 1, status: 'open' },
    { id: 3, title: 'Compare one order with the report', parent: 1, status: 'open', delegable: true, delegation: null },
    { id: 4, title: 'Read the logs', parent: 1, status: 'open', delegable: false },
    { id: 5, title: 'Cache price lookups', parent: null, status: 'parked' },
  ],
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the panel on ${surface} pins focus, offers delegation only on elected topics, and folds parked ideas`, async ($, on) => {
    on('session.id', () => ({ value: 'test-session' }))
    on('env.get', () => ({ value: '/home/test' }))
    on('fs.read', () => ({ value: JSON.stringify(STATE) }))

    const ui = await $.ui.mount({ plugin: 'sidequest', surface, component: 'AbovePrompt', props: { hasSurvey: false } as never })

    expect(await ui.find({ key: 'unfocus' })).toBeDefined()
    expect(await ui.find({ key: 'delegate-3' })).toBeDefined()
    expect(await ui.find({ key: 'delegate-4' })).toBeUndefined()
    expect(await ui.find({ key: 'open-5' })).toBeUndefined()

    await ui.press({ key: 'parked' })

    expect(await ui.find({ key: 'open-5' })).toBeDefined()
  })
}

test('the topics tool runs the CLI for this session and returns its output', async ($, on) => {
  const calls: string[][] = []
  on('session.id', () => ({ value: 'test-session' }))
  on('process.run', ($, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: '#1 Fix the login timeout · depth 1', stderr: '' } }
  })

  const result = await $.tool.call({ tool: 'mcp__sidequest__topics', args: ['fork', 'Fix the login timeout'] } as never)

  expect(calls[0].slice(-4)).toEqual(['--session', 'test-session', 'fork', 'Fix the login timeout'])
  expect(result).toEqual(expect.objectContaining({ result: '#1 Fix the login timeout · depth 1' }))
})

test('a failing topics command comes back as an error the model can read', async ($, on) => {
  on('session.id', () => ({ value: 'test-session' }))
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: 'no topic #9' } }))

  const result = await $.tool.call({ tool: 'mcp__sidequest__topics', args: ['done', '9'] } as never)

  expect(result).toEqual(expect.objectContaining({ result: 'no topic #9', isError: true }))
})

const WIDE = { columns: 160, rows: 40 }
const BRANCHY = {
  current: 2,
  focus: null,
  topics: [
    { id: 1, title: 'Fix the checkout timeout', parent: null, status: 'open', sessions: ['test-session'] },
    { id: 2, title: 'Read the gateway logs', parent: 1, status: 'open', sessions: ['test-session'] },
    { id: 3, title: 'Restart the web pods', parent: 1, status: 'done' },
    { id: 4, title: 'Check the load balancer', parent: 1, status: 'done' },
    { id: 6, title: 'Plan the team offsite', parent: null, status: 'open', sessions: ['test-session'] },
    { id: 7, title: 'Book the venue', parent: 6, status: 'open', sessions: ['old-session'] },
  ],
}

function stubs(on: Parameters<Parameters<typeof test>[1] & ((...args: never[]) => unknown)>[1], state: unknown) {
  on('session.id', () => ({ value: 'test-session' }))
  on('env.get', () => ({ value: '/home/test' }))
  on('fs.read', () => ({ value: JSON.stringify(state) }))
}

test('branches off the active path start folded and unfold on press', async ($, on) => {
  stubs(on, BRANCHY)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  expect(await ui.find({ key: 'switch-2' })).toBeDefined()
  expect(await ui.find({ key: 'switch-7' })).toBeUndefined()

  await ui.press({ key: 'fold-6' })

  expect(await ui.find({ key: 'switch-7' })).toBeDefined()
})

test('finished siblings collapse into one row that expands', async ($, on) => {
  stubs(on, BRANCHY)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  expect(await ui.find({ key: 'switch-3' })).toBeUndefined()

  await ui.press({ key: 'fold-closed--2' })

  expect(await ui.find({ key: 'switch-3' })).toBeDefined()
})

test('a very narrow terminal gets a one-line panel', async ($, on) => {
  stubs(on, BRANCHY)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: { columns: 24, rows: 20 } } as never)

  expect(await ui.find({ key: 'collapse' })).toBeUndefined()
  expect(await ui.find({ key: 'switch-2' })).toBeUndefined()
})

test('a narrow terminal shrinks the action buttons to their glyphs', async ($, on) => {
  stubs(on, BRANCHY)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: { columns: 44, rows: 20 } } as never)

  expect((await ui.find({ key: 'done' }))?.text).toContain('✓')
  expect((await ui.find({ key: 'done' }))?.text).not.toContain('done')
})

test('clearing a typed draft without sending parks it as an idea', async ($, on) => {
  const calls: string[][] = []
  on('session.id', () => ({ value: 'test-session' }))
  on('process.run', ($, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: '#9 parked', stderr: '' } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('prompt.edit', ($, e) => ({ text: '', cursor: 0 }) as never)
  const draft = 'maybe cache the price lookups'

  await $.prompt.edit({ origin: 'person', text: draft, cursor: draft.length, start: 0, end: draft.length, inputText: '' } as never)

  expect(calls[0].slice(-2)).toEqual(['park', draft])
})

test('a single deleted word is not parked', async ($, on) => {
  const calls: string[][] = []
  on('session.id', () => ({ value: 'test-session' }))
  on('process.run', ($, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('prompt.edit', () => ({ text: '', cursor: 0 }) as never)

  await $.prompt.edit({ origin: 'person', text: 'hmm', cursor: 3, start: 0, end: 3, inputText: '' } as never)

  expect(calls).toEqual([])
})

test('a session with no topics yet shows a one-line empty state', async ($, on) => {
  stubs(on, { current: null, topics: [] })
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  expect(await ui.find({ key: 'empty' })).toBeDefined()
  expect(await ui.find({ key: 'collapse' })).toBeUndefined()
})

test('clicking a topic switches to it without refolding the tree', async ($, on) => {
  const live = JSON.parse(JSON.stringify(BRANCHY))
  const calls: string[][] = []
  on('session.id', () => ({ value: 'test-session' }))
  on('env.get', () => ({ value: '/home/test' }))
  on('fs.read', () => ({ value: JSON.stringify(live) }))
  on('process.run', ($, e) => {
    const args = [...e.argv]
    calls.push(args)
    if (args.at(-2) === 'now') live.current = Number(args.at(-1))
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)
  await ui.press({ key: 'fold-6' })
  const before = Boolean(await ui.find({ key: 'switch-2' }))

  await ui.press({ key: 'switch-7' })

  expect(calls.at(-1)?.slice(-2)).toEqual(['now', '7'])
  expect(Boolean(await ui.find({ key: 'switch-2' }))).toBe(before)
})

test('finished, dropped, and running topics cannot be clicked', async ($, on) => {
  stubs(on, {
    current: 1,
    topics: [
      { id: 1, title: 'Fix the checkout timeout', parent: null, status: 'open', sessions: ['test-session'] },
      { id: 2, title: 'Restart the web pods', parent: 1, status: 'done' },
      { id: 3, title: 'Rewrite the cache', parent: 1, status: 'dropped' },
      { id: 4, title: 'Compare one order with the report', parent: 1, status: 'open', delegable: true, delegation: { status: 'running', agent: 'a1' } },
      { id: 5, title: 'Read the gateway logs', parent: 1, status: 'open', sessions: ['test-session'] },
    ],
  })
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)
  await ui.press({ key: 'fold-closed--2' })
  const buttons = (await ui.findAll({ type: 'Button' })).map(found => (found as { key?: string }).key)

  expect(buttons).not.toContain('switch-2')
  expect(buttons).not.toContain('switch-3')
  expect(buttons).not.toContain('switch-4')
  expect(buttons).toContain('switch-5')
  expect(buttons).not.toContain('done')
})

const FOCUSABLE = {
  current: 2,
  focus: null,
  topics: [
    { id: 1, title: 'Plan the team offsite', parent: null, status: 'open', sessions: ['test-session'] },
    { id: 2, title: 'Book the venue', parent: 1, status: 'open', sessions: ['test-session'] },
  ],
}

function focusStubs(on: Parameters<Parameters<typeof test>[1] & ((...args: never[]) => unknown)>[1], draft: string, submitted: string[]) {
  stubs(on, FOCUSABLE)
  on('process.run', ($, e) => {
    const args = [...e.argv]
    const stdout = args.includes('focus') ? 'focus on #2 Book the venue\npaused #1 Plan the team offsite' : ''
    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('prompt.read', () => ({ value: { text: draft, cursor: draft.length } }) as never)
  on('prompt.submit', ($, e) => {
    submitted.push(e.text)
    return { text: e.text, context: e.context }
  })
  on('ui.toast', () => ({ value: undefined }))
}

test('pressing focus with an empty prompt starts Claude on the focus topic', async ($, on) => {
  const submitted: string[] = []
  focusStubs(on, '', submitted)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  await ui.press({ key: 'focus' })

  expect(submitted).toHaveLength(1)
  expect(submitted[0]).toContain('Focus is now on #2')
  expect(submitted[0]).toContain('progress entry on #1')
})

test('pressing focus while typing attaches the focus switch to the typed message instead', async ($, on) => {
  const submitted: string[] = []
  focusStubs(on, 'look at the logs first', submitted)
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  await ui.press({ key: 'focus' })

  expect(submitted).toHaveLength(0)

  const result = await $.prompt.submit({ text: 'look at the logs first' })

  expect((result as { context?: string[] }).context?.join(' ')).toContain('Focus is now on #2')
})

test('capture opens a focused box that parks the idea on Enter', async ($, on) => {
  const calls: string[][] = []
  stubs(on, FOCUSABLE)
  on('process.run', ($, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: '#9 parked', stderr: '' } }
  })
  on('ui.toast', () => ({ value: undefined }))
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  expect(await ui.find({ key: 'idea' })).toBeUndefined()

  await ui.press({ key: 'capture' })
  await ui.input({ key: 'idea', text: 'cache the price lookups' })

  expect(calls.at(-1)?.slice(-4)).toEqual(['--via', 'capture', 'park', 'cache the price lookups'])
  expect(await ui.find({ key: 'idea' })).toBeUndefined()
})

test('an idea longer than 255 characters is cut at 255', async ($, on) => {
  const calls: string[][] = []
  stubs(on, FOCUSABLE)
  on('process.run', ($, e) => {
    calls.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('ui.toast', () => ({ value: undefined }))
  const ui = await $.ui.mount({ plugin: 'sidequest', surface: 'terminal', component: 'AbovePrompt', props: { hasSurvey: false } as never, viewport: WIDE } as never)

  await ui.press({ key: 'capture' })
  await ui.input({ key: 'idea', text: 'x'.repeat(300) })

  expect(calls.at(-1)?.at(-1)).toHaveLength(255)
})
