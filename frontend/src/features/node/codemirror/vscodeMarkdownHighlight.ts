import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags } from '@lezer/highlight'

/**
 * Tag → static class names; colors live in `tokens.css` (--syntax-*) and are scoped in
 * `NodeDetailCard.module.css` under `.documentPanel` so the editor matches the app theme.
 */
const sx = {
  mdH1: 'pt-sx-md-h1',
  mdH2: 'pt-sx-md-h2',
  mdH3: 'pt-sx-md-h3',
  mdH4: 'pt-sx-md-h4',
  mdH5: 'pt-sx-md-h5',
  mdH6: 'pt-sx-md-h6',
  mdH: 'pt-sx-md-h',
  strong: 'pt-sx-strong',
  em: 'pt-sx-em',
  strike: 'pt-sx-strike',
  link: 'pt-sx-link',
  url: 'pt-sx-url',
  list: 'pt-sx-list',
  quote: 'pt-sx-quote',
  hr: 'pt-sx-hr',
  code: 'pt-sx-code',
  meta: 'pt-sx-meta',
  keyword: 'pt-sx-keyword',
  control: 'pt-sx-control',
  string: 'pt-sx-string',
  stringSpecial: 'pt-sx-string-special',
  regexp: 'pt-sx-regexp',
  number: 'pt-sx-number',
  comment: 'pt-sx-comment',
  var: 'pt-sx-var',
  fn: 'pt-sx-fn',
  type: 'pt-sx-type',
  class: 'pt-sx-class',
  enum: 'pt-sx-enum',
  namespace: 'pt-sx-namespace',
  property: 'pt-sx-property',
  operator: 'pt-sx-operator',
  delimiter: 'pt-sx-delimiter',
  bracket: 'pt-sx-bracket',
  bracketList: 'pt-sx-bracket-list',
  angle: 'pt-sx-angle',
  tag: 'pt-sx-tag',
  invalid: 'pt-sx-invalid',
  inserted: 'pt-sx-inserted',
  deleted: 'pt-sx-deleted',
  name: 'pt-sx-name',
  content: 'pt-sx-content',
  literal: 'pt-sx-literal',
} as const

/**
 * Order: more specific / nested tags first (CodeMirror applies first matching rule by tag specificity).
 */
const projectMarkdownHighlightStyle = HighlightStyle.define([
  { tag: tags.heading1, class: sx.mdH1 },
  { tag: tags.heading2, class: sx.mdH2 },
  { tag: tags.heading3, class: sx.mdH3 },
  { tag: tags.heading4, class: sx.mdH4 },
  { tag: tags.heading5, class: sx.mdH5 },
  { tag: tags.heading6, class: sx.mdH6 },
  { tag: tags.heading, class: sx.mdH },

  { tag: tags.strong, class: sx.strong },
  { tag: tags.emphasis, class: sx.em },
  { tag: tags.strikethrough, class: sx.strike },
  { tag: tags.link, class: sx.link },
  { tag: tags.url, class: sx.url },
  { tag: tags.list, class: sx.list },
  { tag: tags.quote, class: sx.quote },
  { tag: tags.contentSeparator, class: sx.hr },
  { tag: tags.monospace, class: sx.code },

  { tag: tags.documentMeta, class: sx.meta },
  { tag: tags.processingInstruction, class: sx.keyword },
  { tag: tags.annotation, class: sx.fn },
  { tag: tags.meta, class: sx.meta },

  { tag: tags.keyword, class: sx.keyword },
  { tag: tags.modifier, class: sx.keyword },
  { tag: tags.operatorKeyword, class: sx.keyword },
  { tag: tags.controlKeyword, class: sx.control },
  { tag: tags.definitionKeyword, class: sx.keyword },
  { tag: tags.moduleKeyword, class: sx.keyword },
  { tag: tags.self, class: sx.keyword },
  { tag: tags.null, class: sx.keyword },
  { tag: tags.atom, class: sx.keyword },
  { tag: tags.bool, class: sx.keyword },
  { tag: tags.unit, class: sx.number },

  { tag: tags.string, class: sx.string },
  { tag: tags.docString, class: sx.string },
  { tag: tags.character, class: sx.string },
  { tag: tags.special(tags.string), class: sx.stringSpecial },
  { tag: tags.regexp, class: sx.regexp },

  { tag: tags.number, class: sx.number },
  { tag: tags.integer, class: sx.number },
  { tag: tags.float, class: sx.number },

  { tag: tags.comment, class: sx.comment },
  { tag: tags.lineComment, class: sx.comment },
  { tag: tags.blockComment, class: sx.comment },
  { tag: tags.docComment, class: sx.comment },

  { tag: tags.variableName, class: sx.var },
  { tag: tags.constant(tags.variableName), class: sx.stringSpecial },
  { tag: tags.local(tags.variableName), class: sx.var },
  { tag: tags.definition(tags.variableName), class: sx.var },
  { tag: tags.function(tags.variableName), class: sx.fn },
  { tag: tags.labelName, class: sx.enum },

  { tag: tags.propertyName, class: sx.property },
  { tag: tags.attributeName, class: sx.property },
  { tag: tags.attributeValue, class: sx.string },

  { tag: tags.typeName, class: sx.type },
  { tag: tags.className, class: sx.class },
  { tag: tags.namespace, class: sx.namespace },
  { tag: tags.macroName, class: sx.fn },

  { tag: tags.operator, class: sx.operator },
  { tag: tags.derefOperator, class: sx.operator },
  { tag: tags.arithmeticOperator, class: sx.operator },
  { tag: tags.logicOperator, class: sx.operator },
  { tag: tags.bitwiseOperator, class: sx.operator },
  { tag: tags.compareOperator, class: sx.operator },
  { tag: tags.updateOperator, class: sx.operator },
  { tag: tags.definitionOperator, class: sx.operator },
  { tag: tags.typeOperator, class: sx.keyword },
  { tag: tags.controlOperator, class: sx.operator },

  { tag: tags.punctuation, class: sx.delimiter },
  { tag: tags.separator, class: sx.delimiter },

  { tag: tags.bracket, class: sx.bracket },
  { tag: tags.squareBracket, class: sx.bracketList },
  { tag: tags.angleBracket, class: sx.angle },
  { tag: tags.paren, class: sx.delimiter },
  { tag: tags.brace, class: sx.delimiter },

  { tag: tags.tagName, class: sx.tag },
  { tag: tags.escape, class: sx.string },
  { tag: tags.color, class: sx.number },

  { tag: tags.inserted, class: sx.inserted },
  { tag: tags.deleted, class: sx.deleted },
  { tag: tags.changed, class: sx.keyword },

  { tag: tags.invalid, class: sx.invalid },
  { tag: tags.name, class: sx.name },
  { tag: tags.content, class: sx.content },
  { tag: tags.literal, class: sx.literal },
])

/**
 * Must NOT use `{ fallback: true }`: basicSetup’s defaultHighlightStyle would win that facet.
 */
export const vscodeMarkdownSyntaxHighlighting = syntaxHighlighting(projectMarkdownHighlightStyle)
