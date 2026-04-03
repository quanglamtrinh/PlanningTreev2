export function logRendererDebug(
  tag: string,
  message: string,
  details?: Record<string, unknown>,
) {
  console.info(tag, message, details ?? {})
  try {
    window.electronAPI?.logDebug?.(tag, message, details)
  } catch {
    // Diagnostics should never interfere with the live UI.
  }
}

export function serializeDebugError(error: unknown): Record<string, unknown> {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack ?? null,
    }
  }

  return {
    value: typeof error === 'string' ? error : String(error),
  }
}
