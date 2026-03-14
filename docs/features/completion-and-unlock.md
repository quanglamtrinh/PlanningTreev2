# Completion And Unlock

## Route

- `POST /v1/projects/{project_id}/nodes/{node_id}/complete`

## Completion Rules

- Only leaf nodes with no active children may complete.
- Only `ready` and `in_progress` nodes may complete.
- Successful completion sets the node status to `done`.
- If the completed node is the active node, clear `active_node_id` to `null`.

## Unlock Rules

- After completion, scan siblings in `child_ids` order.
- Promote the next active sibling still in `locked` to `ready`.

## Ancestor Cascade

- If all active children of a parent are `done`, auto-close the parent to `done`.
- After auto-closing a parent, unlock that parent's next eligible active sibling.
- Continue upward until the root or until an ancestor still has an active child not `done`.

## Rejections

- Non-leaf completion returns `complete_not_allowed`.
- `locked`, `draft`, `done`, and superseded nodes cannot complete.
