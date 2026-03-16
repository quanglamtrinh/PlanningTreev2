import type { ConversationSnapshot } from '../types'
import { deriveConversationBusy } from './deriveConversationBusy'

export function deriveExecutionBusy(snapshot: ConversationSnapshot | null | undefined): boolean {
  return deriveConversationBusy(snapshot)
}
