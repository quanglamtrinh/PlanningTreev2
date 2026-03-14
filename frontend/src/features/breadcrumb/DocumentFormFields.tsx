import type { ReactNode } from 'react'
import styles from './DocumentPanel.module.css'

type SectionCardProps = {
  title: string
  children: ReactNode
}

type FieldRowProps = {
  label: string
  children: ReactNode
}

type ReadOnlyFieldRowProps = {
  label: string
  value: string | string[]
}

type ListFieldRowProps = {
  label: string
  values: string[]
  readOnly?: boolean
  placeholder?: string
  onChange?: (values: string[]) => void
}

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <section className={styles.sectionCard}>
      <div className={styles.sectionHeader}>
        <h4 className={styles.sectionTitle}>{title}</h4>
      </div>
      <div className={styles.sectionBody}>{children}</div>
    </section>
  )
}

export function FieldRow({ label, children }: FieldRowProps) {
  return (
    <div className={styles.formRow}>
      <div className={styles.formRowLabel}>{label}</div>
      <div className={styles.formRowBody}>{children}</div>
    </div>
  )
}

export function ReadOnlyFieldRow({ label, value }: ReadOnlyFieldRowProps) {
  const items = Array.isArray(value) ? value.filter((item) => item.trim().length > 0) : []
  const text = Array.isArray(value) ? '' : value

  return (
    <FieldRow label={label}>
      {Array.isArray(value) ? (
        items.length > 0 ? (
          <ul className={styles.readOnlyList}>
            {items.map((item, index) => (
              <li key={`${label}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : (
          <div className={styles.readOnlyEmpty}>Empty</div>
        )
      ) : text.trim().length > 0 ? (
        <div className={styles.readOnlyValue}>{text}</div>
      ) : (
        <div className={styles.readOnlyEmpty}>Empty</div>
      )}
    </FieldRow>
  )
}

export function ListFieldRow({
  label,
  values,
  readOnly = false,
  placeholder = 'Add item',
  onChange,
}: ListFieldRowProps) {
  const items = values.length > 0 ? values : ['']

  return (
    <FieldRow label={label}>
      {readOnly ? (
        values.length > 0 ? (
          <ul className={styles.readOnlyList}>
            {values.map((item, index) => (
              <li key={`${label}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : (
          <div className={styles.readOnlyEmpty}>Empty</div>
        )
      ) : (
        <div className={styles.listEditor}>
          {items.map((value, index) => (
            <div key={`${label}-${index}`} className={styles.listItemRow}>
              <input
                className={styles.input}
                value={value}
                aria-label={`${label} item ${index + 1}`}
                placeholder={placeholder}
                onChange={(event) => {
                  if (!onChange) {
                    return
                  }
                  const nextValues = [...items]
                  nextValues[index] = event.target.value
                  onChange(nextValues)
                }}
              />
              <button
                type="button"
                className={styles.inlineRemoveButton}
                onClick={() => {
                  if (!onChange) {
                    return
                  }
                  const nextValues = items.filter((_, itemIndex) => itemIndex !== index)
                  onChange(nextValues)
                }}
              >
                Remove
              </button>
            </div>
          ))}
          <div className={styles.listActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => onChange?.([...values, ''])}
            >
              Add Item
            </button>
          </div>
        </div>
      )}
    </FieldRow>
  )
}
