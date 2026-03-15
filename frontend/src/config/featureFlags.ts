function readBooleanEnvFlag(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) {
    return defaultValue
  }
  const normalized = value.trim().toLowerCase()
  if (normalized === 'true' || normalized === '1') {
    return true
  }
  if (normalized === 'false' || normalized === '0') {
    return false
  }
  return defaultValue
}

export function isExecutionConversationV2Enabled(): boolean {
  return readBooleanEnvFlag(import.meta.env.VITE_EXECUTION_CONVERSATION_V2_ENABLED, false)
}
