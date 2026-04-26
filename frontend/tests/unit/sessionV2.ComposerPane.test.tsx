import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ComposerPane } from '../../src/features/session_v2/components/ComposerPane'

describe('ComposerPane', () => {
  it('routes slash text to command popup and submits on Enter', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )

    const textarea = screen.getByPlaceholderText('Send a follow-up message') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '/plan investigate' } })
    expect(screen.getByText('/plan')).toBeInTheDocument()

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('enables reverse search with Ctrl+R', () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )
    const textarea = screen.getByPlaceholderText('Send a follow-up message') as HTMLTextAreaElement
    fireEvent.keyDown(textarea, { key: 'r', ctrlKey: true })
    expect(screen.getByPlaceholderText('Search history')).toBeInTheDocument()
  })

  it('renders attach icon button with hover tooltip text', () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )

    const attachButton = screen.getByRole('button', { name: 'Attach photos and files' })
    expect(attachButton.getAttribute('title')).toBe('Attach photos and files')
  })

  it('renders model and intelligence dropdown and includes selections in submit payload', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    const onModelChange = vi.fn()

    function StatefulComposer() {
      const [selectedModel, setSelectedModel] = useState('gpt-5.4')
      return (
        <ComposerPane
          isTurnRunning={false}
          onSubmit={onSubmit}
          onInterrupt={onInterrupt}
          modelOptions={[
            { value: 'gpt-5.4', label: 'GPT-5.4' },
            { value: 'gpt-5.2', label: 'GPT-5.2' },
          ]}
          selectedModel={selectedModel}
          onModelChange={(model) => {
            onModelChange(model)
            setSelectedModel(model)
          }}
        />
      )
    }

    render(
      <StatefulComposer />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Select model and thinking effort' }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /^High$/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Select model and thinking effort' }))
    fireEvent.mouseEnter(screen.getByRole('menuitem', { name: /GPT-5\.4/ }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /GPT-5\.2/ }))
    expect(onModelChange).toHaveBeenCalledWith('gpt-5.2')

    const textarea = screen.getByPlaceholderText('Send a follow-up message') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Test model submit' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      text: 'Test model submit',
      input: [
        {
          type: 'text',
          text: 'Test model submit',
          text_elements: [],
        },
      ],
      requestedPolicy: {
        model: 'gpt-5.2',
        accessMode: 'full-access',
        effort: 'high',
        workMode: 'local',
        streamMode: 'streaming',
      },
    })
  })

  it('submits mention text as native text elements with PlanningTree metadata off the input item top level', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )

    const textarea = screen.getByPlaceholderText('Send a follow-up message') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Check @' } })
    fireEvent.click(screen.getByText('@README.md'))
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0]?.[0]
    expect(payload?.input[0]).toMatchObject({
      type: 'text',
      text: 'Check @ @README.md',
      text_elements: [
        {
          byteRange: { start: 8, end: 18 },
          placeholder: '@README.md',
        },
      ],
    })
    expect(payload?.input[0]).not.toHaveProperty('mentionBindings')
    expect(payload?.metadata).toEqual({
      planningTree: {
        mentionBindings: {
          '@README.md': 'README.md',
        },
      },
    })
  })

  it('renders current cwd pill beside full access pill', () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
        currentCwd="C:/Users/Thong/PlanningTreeMain"
      />,
    )

    expect(screen.getByRole('button', { name: /current cwd/i })).toBeInTheDocument()
    expect(screen.getByText('C:/Users/Thong/PlanningTreeMain')).toBeInTheDocument()
  })

  it('submits read-only permissions from the permissions dropdown', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /full access/i }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /read-only/i }))

    const textarea = screen.getByPlaceholderText('Send a follow-up message') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Read only please' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0]?.[0].requestedPolicy).toMatchObject({
      accessMode: 'read-only',
    })
  })
})
