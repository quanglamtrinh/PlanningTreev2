# Phase 5 Rehearsal Runbook

## Required Environment

Set these before starting the backend:

- `PLANNINGTREE_EXECUTION_AUDIT_V2_REHEARSAL=1`
- `PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT=<absolute sandbox root>`

Rules:

- the attached project folder must resolve under `PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT`
- do not point the sandbox root at a real working repository
- use a copied or temporary workspace only

## Recommended Sandbox Layout

Example:

```text
<tmp-or-sandbox-root>/
  rehearsal-copy/
    .git/
    .planningtree/
    ...
```

Attach `rehearsal-copy/` as the project folder.

## Manual Rehearsal Steps

1. Start the backend with the rehearsal env vars above.
2. Attach a copied workspace under the rehearsal root.
3. Open the hidden breadcrumb route:
   - `/projects/<projectId>/nodes/<nodeId>/chat-v2`
4. Confirm frame and spec for the execution target node.
5. Trigger `Finish Task` through the existing detail action.
6. Observe the V2 `execution` thread on `/chat-v2`.
7. Confirm the node reaches local-review state.
8. Submit `accept-local-review` through the existing detail action.
9. Observe the V2 `audit` thread on `/chat-v2` for the review rollup.
10. Capture evidence listed below.

## Evidence To Collect

- screenshot or recording of `/chat-v2` showing execution thread updates
- screenshot or recording of `/chat-v2` showing audit rollup updates
- backend logs showing rehearsal flag enabled
- backend logs or API response proving unsafe workspaces are rejected when tested
- V2 snapshot evidence:
  - `execution` thread has canonical assistant/tool items
  - `audit` thread has canonical assistant/system items
- proof that final `fileChange` item uses authoritative files, not preview-only files

## Safety Checklist

- verify the attached project path is under the configured rehearsal root
- verify the workspace is a copied or disposable repo
- verify no production repo path is attached during rehearsal
- verify no legacy `/chat` rendering is used as acceptance evidence for this phase
