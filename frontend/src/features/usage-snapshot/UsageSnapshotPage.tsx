import { useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { LocalUsageDay } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { Sidebar } from '../graph/Sidebar'
import graphStyles from '../graph/GraphWorkspace.module.css'
import { useLocalUsageSnapshot } from './useLocalUsageSnapshot'
import styles from './UsageSnapshotPage.module.css'

const numberFormatter = new Intl.NumberFormat('en-US')
const percentFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})

function formatNumber(value: number): string {
  return numberFormatter.format(value)
}

function formatPercent(value: number): string {
  return `${percentFormatter.format(value)}%`
}

function formatDayLabel(dayKey: string): string {
  const parsed = new Date(`${dayKey}T00:00:00`)
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatDuration(totalMs: number): string {
  if (totalMs < 60_000) {
    return `${Math.max(0, Math.round(totalMs / 1000))}s`
  }
  if (totalMs < 3_600_000) {
    return `${Math.round(totalMs / 60_000)}m`
  }
  return `${(totalMs / 3_600_000).toFixed(1)}h`
}

function formatUpdatedAt(timestampMs: number | null): string {
  if (timestampMs == null) {
    return '--'
  }
  const parsed = new Date(timestampMs)
  if (Number.isNaN(parsed.getTime())) {
    return '--'
  }
  return parsed.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function buildChartPoints(days: LocalUsageDay[]): string {
  if (days.length === 0) {
    return ''
  }
  const maxValue = Math.max(1, ...days.map((day) => day.total_tokens))
  const leftPad = 12
  const rightPad = 12
  const topPad = 10
  const bottomPad = 10
  const chartWidth = 320 - leftPad - rightPad
  const chartHeight = 120 - topPad - bottomPad

  return days
    .map((day, index) => {
      const x =
        days.length === 1
          ? leftPad + chartWidth / 2
          : leftPad + (index * chartWidth) / (days.length - 1)
      const y = topPad + chartHeight - (day.total_tokens / maxValue) * chartHeight
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

export function UsageSnapshotPage() {
  const { initialize, hasInitialized, isInitializing } = useProjectStore(
    useShallow((s) => ({
      initialize: s.initialize,
      hasInitialized: s.hasInitialized,
      isInitializing: s.isInitializing,
    })),
  )

  useEffect(() => {
    void initialize()
  }, [initialize])

  const {
    snapshot,
    isLoading,
    isRefreshing,
    error,
    lastSuccessfulAt,
    refresh,
  } = useLocalUsageSnapshot()

  if (!hasInitialized || isInitializing) {
    return (
      <section className={graphStyles.view}>
        <Sidebar />
        <div className={graphStyles.mainColumn}>
          <div className={graphStyles.loading}>Loading...</div>
        </div>
      </section>
    )
  }

  const chartDays = snapshot?.days.slice(-7) ?? []
  const chartPoints = buildChartPoints(chartDays)
  const totalWindowTokens = snapshot?.days.reduce((sum, day) => sum + day.total_tokens, 0) ?? 0
  const totalAgentRunsLast7 = chartDays.reduce((sum, day) => sum + day.agent_runs, 0)
  const totalAgentTimeLast7Ms = chartDays.reduce((sum, day) => sum + day.agent_time_ms, 0)
  const isEmptyState = snapshot != null && totalWindowTokens === 0
  const showBlockingError = snapshot == null && error != null
  const showNonBlockingError = snapshot != null && error != null
  const showInitialLoading = snapshot == null && isLoading

  return (
    <section className={graphStyles.view}>
      <Sidebar />
      <div className={`${graphStyles.mainColumn} ${styles.mainColumn}`}>
        <div className={styles.scroll}>
          <header className={styles.hero}>
            <div className={styles.heroRow}>
              <h1 className={styles.title}>Usage Snapshot</h1>
              <button
                type="button"
                className={styles.refreshButton}
                data-testid="usage-refresh-button"
                onClick={() => {
                  void refresh()
                }}
                disabled={isLoading || isRefreshing}
                aria-busy={isRefreshing ? 'true' : undefined}
              >
                {isRefreshing ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            <p className={styles.updatedAt}>
              Last updated: {formatUpdatedAt(snapshot?.updated_at ?? lastSuccessfulAt)}
            </p>
          </header>

          {showInitialLoading ? (
            <div className={styles.loadingShell} data-testid="usage-snapshot-loading">
              <div className={styles.skeletonCard} />
              <div className={styles.skeletonCard} />
            </div>
          ) : null}

          {showBlockingError ? (
            <section className={styles.blockingError} data-testid="usage-snapshot-error-blocking">
              <h2 className={styles.blockingErrorTitle}>Unable to load usage snapshot</h2>
              <p className={styles.blockingErrorBody}>{error}</p>
              <button
                type="button"
                className={styles.retryButton}
                onClick={() => {
                  void refresh()
                }}
                disabled={isLoading || isRefreshing}
              >
                {isLoading || isRefreshing ? 'Retrying...' : 'Retry'}
              </button>
            </section>
          ) : null}

          {snapshot ? (
            <>
              {showNonBlockingError ? (
                <div className={styles.errorBanner} role="alert" data-testid="usage-snapshot-error-banner">
                  Latest update failed: {error}
                </div>
              ) : null}

              {isEmptyState ? (
                <section className={styles.emptyState} data-testid="usage-snapshot-empty">
                  <h2 className={styles.emptyTitle}>No local usage yet</h2>
                  <p className={styles.emptyBody}>
                    We scanned your Codex sessions and found no token activity in this window. Run a
                    session and this view will populate automatically.
                  </p>
                </section>
              ) : (
                <div className={styles.grid} data-testid="usage-snapshot-content">
                  <section className={styles.summaryGrid} aria-label="Usage summary">
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Last 7 days</h2>
                      <p className={styles.metricValue}>{formatNumber(snapshot.totals.last7_days_tokens)}</p>
                      <p className={styles.metricHint}>Total tokens</p>
                    </article>
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Last 30 days</h2>
                      <p className={styles.metricValue}>{formatNumber(snapshot.totals.last30_days_tokens)}</p>
                      <p className={styles.metricHint}>Total tokens</p>
                    </article>
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Average daily</h2>
                      <p className={styles.metricValue}>{formatNumber(snapshot.totals.average_daily_tokens)}</p>
                      <p className={styles.metricHint}>Last 7 days</p>
                    </article>
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Cache hit rate</h2>
                      <p className={styles.metricValue}>{formatPercent(snapshot.totals.cache_hit_rate_percent)}</p>
                      <p className={styles.metricHint}>Last 7 days</p>
                    </article>
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Peak day</h2>
                      <p className={styles.metricValue}>
                        {snapshot.totals.peak_day ? formatDayLabel(snapshot.totals.peak_day) : '--'}
                      </p>
                      <p className={styles.metricHint}>{formatNumber(snapshot.totals.peak_day_tokens)} tokens</p>
                    </article>
                    <article className={styles.summaryCard}>
                      <h2 className={styles.cardTitle}>Agent runs (7d)</h2>
                      <p className={styles.metricValue}>{formatNumber(totalAgentRunsLast7)}</p>
                      <p className={styles.metricHint}>{formatDuration(totalAgentTimeLast7Ms)} active time</p>
                    </article>
                  </section>

                  <div className={styles.detailGrid}>
                    <section className={styles.panel}>
                      <div className={styles.panelHeader}>
                        <h2 className={styles.panelTitle}>7-day token trend</h2>
                      </div>
                      <svg className={styles.chart} viewBox="0 0 320 120" aria-label="7-day token chart">
                        <line x1="12" y1="110" x2="308" y2="110" className={styles.chartAxis} />
                        <polyline points={chartPoints} className={styles.chartLine} />
                      </svg>
                      <div className={styles.chartLabels}>
                        {chartDays.map((day) => (
                          <span key={day.day} className={styles.chartLabel}>
                            {formatDayLabel(day.day)}
                          </span>
                        ))}
                      </div>
                    </section>

                    <section className={styles.panel}>
                      <div className={styles.panelHeader}>
                        <h2 className={styles.panelTitle}>Top models</h2>
                      </div>
                      {snapshot.top_models.length === 0 ? (
                        <p className={styles.modelEmpty}>No model attribution available yet.</p>
                      ) : (
                        <ul className={styles.modelList}>
                          {snapshot.top_models.map((model) => (
                            <li key={model.model} className={styles.modelRow}>
                              <div>
                                <p className={styles.modelName}>{model.model}</p>
                                <p className={styles.modelTokens}>{formatNumber(model.tokens)} tokens</p>
                              </div>
                              <span className={styles.modelShare}>{formatPercent(model.share_percent)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  </div>
                </div>
              )}
            </>
          ) : null}

          {!showInitialLoading && !snapshot && !showBlockingError ? (
            <section className={styles.blockingError}>
              <h2 className={styles.blockingErrorTitle}>No snapshot available</h2>
              <p className={styles.blockingErrorBody}>
                Waiting for usage data from background polling.
              </p>
            </section>
          ) : null}
        </div>
      </div>
    </section>
  )
}
