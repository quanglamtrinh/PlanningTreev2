export function indexToReviewLetter(index: number): string {
  let next = Math.max(1, Math.trunc(index))
  let label = ''

  while (next > 0) {
    next -= 1
    label = String.fromCharCode(65 + (next % 26)) + label
    next = Math.floor(next / 26)
  }

  return label
}

export function formatReviewChainLabel(
  parentHierarchicalNumber: string,
  index: number,
): string {
  return `${parentHierarchicalNumber}.${indexToReviewLetter(index)}`
}

export function parentHierarchicalNumberFromReviewNode(
  hierarchicalNumber: string,
): string {
  return hierarchicalNumber.endsWith('.R')
    ? hierarchicalNumber.slice(0, -2)
    : hierarchicalNumber
}
