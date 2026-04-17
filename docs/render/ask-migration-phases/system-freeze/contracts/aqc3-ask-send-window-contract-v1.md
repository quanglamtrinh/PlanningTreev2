# AQC3 - Ask Send Window Contract v1

Status: Frozen contract.

Last updated: 2026-04-14.

Marker: `ask_send_window_contract_frozen`

- Ask queue auto-send is allowed only when lane is send-eligible.
- Blocked states must expose explicit pause reason.
- Send-window evaluation must be deterministic for a given snapshot and queue state.
