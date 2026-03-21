import type { CodexRateLimits } from '../../api/types'

export type SidebarUsageLabels = {
  sessionPercent: number | null
  weeklyPercent: number | null
  sessionResetLabel: string | null
  weeklyResetLabel: string | null
  creditsLabel: string | null
  showWeekly: boolean
}

function clampPercent(value: number) {
  return Math.min(Math.max(Math.round(value), 0), 100)
}

function formatRelativeDuration(targetMs: number, nowMs: number) {
  const diffMs = Math.max(0, targetMs - nowMs)
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d`
  return `${Math.floor(diffDay / 7)}w`
}

function formatResetLabel(resetsAt: number | null | undefined, nowMs: number) {
  if (typeof resetsAt !== 'number' || !Number.isFinite(resetsAt)) {
    return null
  }
  const resetMs = resetsAt > 1_000_000_000_000 ? resetsAt : resetsAt * 1000
  return `Resets ${formatRelativeDuration(resetMs, nowMs)}`
}

function formatCreditsLabel(rateLimits: CodexRateLimits | null) {
  const credits = rateLimits?.credits ?? null
  if (!credits?.has_credits) {
    return null
  }
  if (credits.unlimited) {
    return 'Credits: Unlimited'
  }
  const balance = credits.balance?.trim() ?? ''
  if (!balance) {
    return null
  }
  const intValue = Number.parseInt(balance, 10)
  if (Number.isFinite(intValue) && intValue > 0) {
    return `Credits: ${intValue} credits`
  }
  const floatValue = Number.parseFloat(balance)
  if (Number.isFinite(floatValue) && floatValue > 0) {
    const rounded = Math.round(floatValue)
    return rounded > 0 ? `Credits: ${rounded} credits` : null
  }
  return null
}

export function getCodexUsageLabels(
  rateLimits: CodexRateLimits | null,
  nowMs = Date.now(),
): SidebarUsageLabels {
  const sessionPercent =
    typeof rateLimits?.primary?.used_percent === 'number'
      ? clampPercent(rateLimits.primary.used_percent)
      : null
  const weeklyPercent =
    typeof rateLimits?.secondary?.used_percent === 'number'
      ? clampPercent(rateLimits.secondary.used_percent)
      : null

  return {
    sessionPercent,
    weeklyPercent,
    sessionResetLabel: formatResetLabel(rateLimits?.primary?.resets_at, nowMs),
    weeklyResetLabel: formatResetLabel(rateLimits?.secondary?.resets_at, nowMs),
    creditsLabel: formatCreditsLabel(rateLimits),
    showWeekly: Boolean(rateLimits?.secondary),
  }
}
