import { useEffect, useRef, useState } from 'react'
import styles from './AgentSpinner.module.css'

export const SPINNER_WORDS_THINKING: readonly string[] = [
  'Thinking',
  'Working',
  'Reasoning',
  'Analyzing',
  'Processing',
]

export const SPINNER_WORDS_SPLITTING: readonly string[] = [
  'Splitting',
  'Planning',
  'Structuring',
  'Designing',
]

export const SPINNER_WORDS_GENERATING: readonly string[] = [
  'Generating',
  'Writing',
  'Drafting',
  'Composing',
]

export const SPINNER_WORDS_APPLYING: readonly string[] = ['Applying', 'Working', 'Processing']

const CYCLE_MS = 800

type AgentSpinnerProps = {
  words?: readonly string[]
  /** Extra class applied to the root wrapper (e.g. `styles.activity` from parent). */
  className?: string
}

/**
 * Claude Code–style activity indicator: a blinking star ✦ + rapidly cycling word.
 *
 * Accessibility: the visual is aria-hidden; the wrapper carries role="status" with
 * a stable aria-label so screen readers announce once without repeating each word.
 */
export function AgentSpinner({
  words = SPINNER_WORDS_THINKING,
  className,
}: AgentSpinnerProps) {
  const [index, setIndex] = useState(0)
  const wordsRef = useRef(words)
  wordsRef.current = words

  useEffect(() => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) return

    const id = setInterval(() => {
      setIndex((prev) => (prev + 1) % wordsRef.current.length)
    }, CYCLE_MS)
    return () => clearInterval(id)
  }, [])

  return (
    <span
      role="status"
      aria-label={words[0]}
      className={`${styles.root}${className ? ` ${className}` : ''}`}
    >
      <span className={styles.star} aria-hidden="true">
        ✦
      </span>
      <span className={styles.word} aria-hidden="true">
        {words[index]}
      </span>
    </span>
  )
}
