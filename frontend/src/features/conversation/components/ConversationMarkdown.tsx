import { useEffect } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './ConversationMarkdown.module.css'
import {
  getConversationMarkdownDesktopHooks,
} from './markdownDesktopHooks'
import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
  type ParseCacheMode,
} from './v3/parseCacheContract'
import { emitParseCacheTrace } from './v3/messagesV3ProfilingHooks'

export type ConversationMarkdownParseTrace = {
  threadId: string | null | undefined
  itemId: string
  updatedAt: string
  mode: ParseCacheMode
  rendererVersion?: string | null
  source?: string
}

function decodeHref(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function toLocalPathFromHref(href: string): string | null {
  const normalizedHref = decodeHref(href)
  if (!normalizedHref) {
    return null
  }
  if (normalizedHref.startsWith('file://')) {
    const filePath = normalizedHref.slice('file://'.length)
    if (/^\/[a-zA-Z]:[\\/]/.test(filePath)) {
      return filePath.slice(1)
    }
    return filePath
  }
  if (
    /^[a-zA-Z]:[\\/]/.test(normalizedHref) ||
    normalizedHref.startsWith('\\\\') ||
    normalizedHref.startsWith('/')
  ) {
    return normalizedHref
  }
  return null
}

function toThreadIdFromHref(href: string): string | null {
  const normalizedHref = decodeHref(href)
  if (!normalizedHref.startsWith('thread://')) {
    return null
  }
  const threadId = normalizedHref.slice('thread://'.length).trim()
  return threadId || null
}

function transformMarkdownUrl(url: string, key: string): string {
  if (toLocalPathFromHref(url)) {
    return url
  }
  if (key === 'href' && toThreadIdFromHref(url)) {
    return url
  }
  return defaultUrlTransform(url)
}

export function ConversationMarkdown({
  content,
  parseTrace,
}: {
  content: string
  parseTrace?: ConversationMarkdownParseTrace
}) {
  if (!content.trim()) {
    return null
  }

  const desktopHooks = getConversationMarkdownDesktopHooks()
  const traceSource = parseTrace?.source ?? 'conversation_markdown'
  const traceRendererVersion = parseTrace?.rendererVersion ?? PARSE_CACHE_RENDERER_VERSION
  const traceKey =
    parseTrace == null
      ? null
      : buildParseCacheKey({
          threadId: parseTrace.threadId,
          itemId: parseTrace.itemId,
          updatedAt: parseTrace.updatedAt,
          mode: parseTrace.mode,
          rendererVersion: traceRendererVersion,
        })

  useEffect(() => {
    if (parseTrace == null || traceKey == null) {
      return
    }
    emitParseCacheTrace({
      source: traceSource,
      threadId: parseTrace.threadId ?? null,
      itemId: parseTrace.itemId,
      updatedAt: parseTrace.updatedAt,
      mode: parseTrace.mode,
      rendererVersion: traceRendererVersion,
      key: traceKey,
    })
  })

  return (
    <div className={styles.root}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url, key) => transformMarkdownUrl(url, key)}
        components={{
          a: ({ node: _node, href, onClick, onContextMenu, children, ...props }) => {
            const safeHref = typeof href === 'string' ? href : ''
            const localPath = toLocalPathFromHref(safeHref)
            const threadId = toThreadIdFromHref(safeHref)
            return (
              <a
                {...props}
                href={safeHref}
                onClick={(event) => {
                  onClick?.(event)
                  if (event.defaultPrevented) {
                    return
                  }
                  if (localPath) {
                    if (desktopHooks.openLocalFile({ path: localPath, event }) === true) {
                      event.preventDefault()
                    }
                    return
                  }
                  if (threadId) {
                    if (desktopHooks.openThreadLink({ threadId, event }) === true) {
                      event.preventDefault()
                    }
                  }
                }}
                onContextMenu={(event) => {
                  onContextMenu?.(event)
                  if (event.defaultPrevented) {
                    return
                  }
                  desktopHooks.onFileLinkContextMenu({
                    href: safeHref,
                    path: localPath,
                    event,
                  })
                }}
              >
                {children}
              </a>
            )
          },
          img: ({ node: _node, src, alt, onClick, ...props }) => {
            const safeSrc = typeof src === 'string' ? src : ''
            const safeAlt = typeof alt === 'string' ? alt : ''
            return (
              <img
                {...props}
                src={safeSrc}
                alt={safeAlt}
                onClick={(event) => {
                  onClick?.(event)
                  if (event.defaultPrevented || !safeSrc) {
                    return
                  }
                  if (desktopHooks.openImageLightbox({ src: safeSrc, alt: safeAlt, event }) === true) {
                    event.preventDefault()
                  }
                }}
              />
            )
          },
          pre: ({ node: _node, children, onDoubleClick, ...props }) => (
            <pre
              {...props}
              onDoubleClick={(event) => {
                onDoubleClick?.(event)
                if (event.defaultPrevented) {
                  return
                }
                const code = String(event.currentTarget.textContent ?? '').trim()
                if (!code) {
                  return
                }
                desktopHooks.copyCodeBlock({ code, event })
              }}
            >
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
