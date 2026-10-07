export type Version = number
export type TopicId = number

declare module 'claude-code' {
  interface PluginState {
    sidequest: { isCollapsed: boolean; isParkedOpen: boolean; version: Version; toggled: TopicId[] }
  }
}
