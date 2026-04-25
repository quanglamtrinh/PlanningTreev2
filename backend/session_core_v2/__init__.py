"""Session Core V2 package (parallel rewrite lane)."""

from backend.session_core_v2.connection import ConnectionStateMachine, SessionManagerV2
from backend.session_core_v2.protocol import SessionProtocolClientV2
from backend.session_core_v2.storage import RuntimeStoreV2
from backend.session_core_v2.thread_store import ThreadMetadataStore, ThreadRolloutRecorder
from backend.session_core_v2.transport import StdioJsonRpcTransportV2

__all__ = [
    "ConnectionStateMachine",
    "RuntimeStoreV2",
    "SessionManagerV2",
    "SessionProtocolClientV2",
    "StdioJsonRpcTransportV2",
    "ThreadMetadataStore",
    "ThreadRolloutRecorder",
]
