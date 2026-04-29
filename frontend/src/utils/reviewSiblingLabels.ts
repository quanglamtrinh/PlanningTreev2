import { formatHierarchicalDisplayIndex } from './nodeDisplayIndex'

export function formatReviewChainLabel(
  parentHierarchicalNumber: string,
  index: number,
): string {
  const parentNumber = parentHierarchicalNumber.trim()
  const numericIndex = Math.max(1, Math.trunc(index))
  return formatHierarchicalDisplayIndex(parentNumber ? `${parentNumber}.${numericIndex}` : String(numericIndex)) ?? String(numericIndex)
}

export function parentHierarchicalNumberFromReviewNode(
  hierarchicalNumber: string,
): string {
  return hierarchicalNumber.endsWith('.R')
    ? hierarchicalNumber.slice(0, -2)
    : hierarchicalNumber
}
