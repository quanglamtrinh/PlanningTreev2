# Node CRUD

## Scope

The current public node surface is intentionally small.

- Create child nodes
- Update node title and description
- Launch split jobs for eligible nodes
- Persist active-node selection through the project route

All node content lives inline in `tree.json` in the current build.

## Public Routes

- `PATCH /v1/projects/{project_id}/active-node`
- `POST /v1/projects/{project_id}/nodes`
- `PATCH /v1/projects/{project_id}/nodes/{node_id}`
- `POST /v1/projects/{project_id}/nodes/{node_id}/split`

## Create Child

- Request body: `{ parent_id }`
- Creates a new structural node entry directly inside `tree.json`.
- Computes `depth`, `display_order`, and `hierarchical_number`.
- The first active child is `ready`; later active siblings are `locked`.
- If the parent or any ancestor is `locked`, the new child stays `locked`.
- Reject creation for `done` or superseded nodes.
- Sets `active_node_id` to the new child.

## Update Node

- Request body: `{ title?, description? }`
- Empty body is rejected.
- Empty `title` is rejected.
- `title` and `description` persist inline in `tree.json`.

## Split Node

- Request body: `{ mode }`
- Accepted modes: `workflow`, `simplify_workflow`, `phase_breakdown`, `agent_breakdown`
- Split is rejected for superseded nodes, done nodes, nodes that already have active children, nodes without a confirmed frame, or nodes whose latest confirmed frame still has clarify work remaining.
- Split is async: the route returns `202 accepted`, then the frontend polls project split status.
- Successful split creates new child nodes inline in `tree.json` and selects the first child.
