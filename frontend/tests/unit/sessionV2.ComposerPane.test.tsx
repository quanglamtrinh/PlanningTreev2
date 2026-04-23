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

    const textarea = screen.getByPlaceholderText('Ask for follow-up changes') as HTMLTextAreaElement
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
    const textarea = screen.getByPlaceholderText('Ask for follow-up changes') as HTMLTextAreaElement
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

  it('renders model dropdown and includes selected model in submit payload', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    const onModelChange = vi.fn()
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
        modelOptions={[
          { value: 'gpt-5.4', label: 'GPT-5.4' },
          { value: 'gpt-5.2', label: 'GPT-5.2' },
        ]}
        selectedModel="gpt-5.4"
        onModelChange={onModelChange}
      />,
    )

    const modelSelect = screen.getByRole('combobox', { name: 'Select model' })
    expect(modelSelect).toHaveValue('gpt-5.4')
    fireEvent.change(modelSelect, { target: { value: 'gpt-5.2' } })
    expect(onModelChange).toHaveBeenCalledWith('gpt-5.2')

    const textarea = screen.getByPlaceholderText('Ask for follow-up changes') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Test model submit' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
      model: 'gpt-5.4',
      text: 'Test model submit',
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
})
