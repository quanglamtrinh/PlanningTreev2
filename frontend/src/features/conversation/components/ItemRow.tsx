import type { ConversationItem, PendingUserInputRequest, UserInputAnswer } from '../../../api/types'
import { ErrorRow } from './ErrorRow'
import { MessageRow } from './MessageRow'
import { PlanRow } from './PlanRow'
import { ReasoningRow } from './ReasoningRow'
import { StatusRow } from './StatusRow'
import { ToolRow } from './ToolRow'
import { UserInputRow } from './UserInputRow'

export function ItemRow({
  item,
  pendingRequest,
  onResolveUserInput,
}: {
  item: ConversationItem
  pendingRequest?: PendingUserInputRequest
  onResolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void> | void
}) {
  switch (item.kind) {
    case 'message':
      return <MessageRow item={item} />
    case 'reasoning':
      return <ReasoningRow item={item} />
    case 'plan':
      return <PlanRow item={item} />
    case 'tool':
      return <ToolRow item={item} />
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
