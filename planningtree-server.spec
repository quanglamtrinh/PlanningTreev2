# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PlanningTree backend.

Build:  pyinstaller planningtree-server.spec --distpath build/dist
Output: build/dist/planningtree-server/  (one-dir mode)
"""

import os
import sys

block_cipher = None

ROOT = os.path.abspath(os.path.dirname(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'backend', 'server_entry.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'frontend', 'dist'), os.path.join('frontend', 'dist')),
    ],
    hiddenimports=[
        # Uvicorn uses lazy/dynamic imports for these modules
        'uvicorn.logging',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        # FastAPI / Starlette internals
        'multipart',
        'multipart.multipart',
        # Backend modules (ensure all are bundled)
        'backend',
        'backend.main',
        'backend.split_contract',
        'backend.config',
        'backend.config.app_config',
        'backend.errors',
        'backend.errors.app_errors',
        'backend.routes',
        'backend.routes.bootstrap',
        'backend.routes.codex',
        'backend.routes.nodes',
        'backend.routes.projects',
        'backend.routes.split',
        'backend.services',
        'backend.services.project_service',
        'backend.services.tree_service',
        'backend.services.node_service',
        'backend.services.split_service',
        'backend.services.chat_service',
        'backend.services.snapshot_view_service',
        'backend.services.codex_account_service',
        'backend.services.planningtree_workspace',
        'backend.storage',
        'backend.storage.storage',
        'backend.storage.project_store',
        'backend.storage.project_ids',
        'backend.storage.project_locks',
        'backend.storage.file_utils',
        'backend.storage.config_store',
        'backend.storage.split_state_store',
        'backend.storage.chat_state_store',
        'backend.ai',
        'backend.ai.codex_client',
        'backend.ai.chat_prompt_builder',
        'backend.ai.split_prompt_builder',
        'backend.ai.split_context_builder',
        'backend.ai.part_accumulator',
        'backend.streaming',
        'backend.streaming.sse_broker',
        'backend.middleware',
        'backend.middleware.auth_token',
        # Third-party (dynamic/lazy imports)
        'aiofiles',
        'aiofiles.os',
        'aiofiles.threadpool',
        'yaml',
        'openai',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='planningtree-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='planningtree-server',
)
