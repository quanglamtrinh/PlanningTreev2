import type { MouseEvent } from 'react'

export type MarkdownLocalFileOpenArgs = {
  path: string
  event: MouseEvent<HTMLAnchorElement>
}

export type MarkdownFileContextMenuArgs = {
  href: string
  path: string | null
  event: MouseEvent<HTMLAnchorElement>
}

export type MarkdownThreadLinkOpenArgs = {
  threadId: string
  event: MouseEvent<HTMLAnchorElement>
}

export type MarkdownImageLightboxArgs = {
  src: string
  alt: string
  event: MouseEvent<HTMLImageElement>
}

export type MarkdownCopyCodeBlockArgs = {
  code: string
  event: MouseEvent<HTMLElement>
}

export type ConversationMarkdownDesktopHooks = {
  openLocalFile: (args: MarkdownLocalFileOpenArgs) => boolean | void
  onFileLinkContextMenu: (args: MarkdownFileContextMenuArgs) => void
  openThreadLink: (args: MarkdownThreadLinkOpenArgs) => boolean | void
  openImageLightbox: (args: MarkdownImageLightboxArgs) => boolean | void
  copyCodeBlock: (args: MarkdownCopyCodeBlockArgs) => void
}

const NOOP_MARKDOWN_DESKTOP_HOOKS: ConversationMarkdownDesktopHooks = {
  openLocalFile: () => false,
  onFileLinkContextMenu: () => undefined,
  openThreadLink: () => false,
  openImageLightbox: () => false,
  copyCodeBlock: () => undefined,
}

let activeMarkdownDesktopHooks: ConversationMarkdownDesktopHooks = NOOP_MARKDOWN_DESKTOP_HOOKS

export function setConversationMarkdownDesktopHooks(
  overrides: Partial<ConversationMarkdownDesktopHooks> | null,
) {
  if (!overrides) {
    activeMarkdownDesktopHooks = NOOP_MARKDOWN_DESKTOP_HOOKS
    return
  }
  activeMarkdownDesktopHooks = {
    ...NOOP_MARKDOWN_DESKTOP_HOOKS,
    ...overrides,
  }
}

export function resetConversationMarkdownDesktopHooks() {
  activeMarkdownDesktopHooks = NOOP_MARKDOWN_DESKTOP_HOOKS
}

export function getConversationMarkdownDesktopHooks(): ConversationMarkdownDesktopHooks {
  return activeMarkdownDesktopHooks
}
