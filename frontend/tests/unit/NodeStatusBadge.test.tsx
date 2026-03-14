import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NodeStatusBadge } from '../../src/features/node/NodeStatusBadge'

describe('NodeStatusBadge', () => {
  it('renders the five phase-3 status labels', () => {
    render(
      <div>
        <NodeStatusBadge status="locked" />
        <NodeStatusBadge status="draft" />
        <NodeStatusBadge status="ready" />
        <NodeStatusBadge status="in_progress" />
        <NodeStatusBadge status="done" />
      </div>,
    )

    expect(screen.getByText('Locked')).toBeInTheDocument()
    expect(screen.getByText('Draft')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('In Progress')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })
})
