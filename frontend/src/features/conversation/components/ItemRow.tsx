import type { ConversationItem, PendingUserInputRequest, UserInputAnswer } from '../../../api/types'
import { ErrorRow } from './ErrorRow'
import { MessageRow } from './MessageRow'
import { PlanRow } from './PlanRow'
import { ReasoningRow } from './ReasoningRow'
import { StatusRow } from './StatusRow'
import { ToolRow } from './ToolRow'
import { UserInputRow } from './UserInputRow'
import type { ReasoningPresentationMeta } from './useConversationViewState'

export function ItemRow({
  item,
  pendingRequest,
  onResolveUserInput,
  isExpanded = false,
  onToggleExpanded,
  onRequestAutoScroll,
  reasoningMeta,
}: {
  item: ConversationItem
  pendingRequest?: PendingUserInputRequest
  onResolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void> | void
  isExpanded?: boolean
  onToggleExpanded?: (itemId: string) => void
  onRequestAutoScroll?: () => void
  reasoningMeta?: ReasoningPresentationMeta
}) {
  switch (item.kind) {
    case 'message':
      return <MessageRow item={item} />
    case 'reasoning':
      return (
        <ReasoningRow
          item={item}
          presentationMeta={reasoningMeta}
          isExpanded={isExpanded}
          onToggle={onToggleExpanded}
        />
      )
    case 'plan':
      return <PlanRow item={item} />
    case 'tool':
      return (
        <ToolRow
          item={item}
          isExpanded={isExpanded}
          onToggle={onToggleExpanded}
          onRequestAutoScroll={onRequestAutoScroll}
        />
      )
    case 'userInput':
      return <UserInputRow item={item} pendingRequest={pendingRequest} onResolve={onResolveUserInput} />
    case 'status':
      return <StatusRow item={item} />
    case 'error':
      return <ErrorRow item={item} />
    default:
      return null
  }
}
