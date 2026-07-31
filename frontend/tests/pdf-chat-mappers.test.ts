import assert from 'node:assert/strict'
import test from 'node:test'

import {
  toChatAnswerView,
  toChatTurnView,
} from '../src/features/pdf-knowledge/utils/pdf-chat-view.ts'
import type {
  PdfAnswerCitation,
  PdfChatAnswer,
  PdfChatTurn,
} from '../src/features/pdf-knowledge/types.ts'

function citation(
  citationId: string,
  fileId: string,
  chunkId: string,
): PdfAnswerCitation {
  return {
    citationId,
    evidenceId: `evidence-${citationId}`,
    fileId,
    fileName: `${fileId}.pdf`,
    chunkId,
    chunkIndex: Number.parseInt(chunkId.replace(/\D/g, ''), 10) || 0,
    pageLabel: 'Page 1',
    title: `Title ${citationId}`,
    quote: `Quote ${citationId}`,
  }
}

function answer(overrides: Partial<PdfChatAnswer> = {}): PdfChatAnswer {
  return {
    sessionId: 'session-1',
    question: 'Question',
    answerBlocks: [],
    citations: [],
    selectedDocuments: [],
    newlyAttachedDocuments: [],
    attachedDocuments: [],
    insufficientEvidence: false,
    followUpSuggestions: [],
    warnings: [],
    createdAt: '2026-07-31T12:00:00Z',
    ...overrides,
  }
}

test('keeps citations attached to their own answer block', () => {
  const view = toChatAnswerView(
    answer({
      answerBlocks: [
        { text: 'First conclusion', reasoning: '', citationIds: ['P1'] },
        { text: 'Second conclusion', reasoning: '', citationIds: ['P2'] },
      ],
      citations: [
        citation('P1', 'first', 'chunk-1'),
        citation('P2', 'second', 'chunk-2'),
      ],
    }),
    'turn-1',
  )

  assert.deepEqual(
    view.blocks.map((block) => block.citations.map((item) => item.citationId)),
    [['P1'], ['P2']],
  )
  assert.equal(view.blocks[0]?.citations[0]?.key, 'turn-1:P1')
  assert.equal(view.blocks[1]?.citations[0]?.fileId, 'second')
})

test('uses turn-scoped citation keys for repeated citation ids', () => {
  const firstTurn: PdfChatTurn = {
    turnId: 'turn-1',
    sessionId: 'session-1',
    question: 'First',
    answer: answer({
      answerBlocks: [{ text: 'First answer', reasoning: '', citationIds: ['P1'] }],
      citations: [citation('P1', 'first', 'chunk-1')],
    }),
    createdAt: '2026-07-31T12:00:00Z',
  }
  const secondTurn: PdfChatTurn = {
    ...firstTurn,
    turnId: 'turn-2',
    question: 'Second',
    answer: answer({
      answerBlocks: [{ text: 'Second answer', reasoning: '', citationIds: ['P1'] }],
      citations: [citation('P1', 'second', 'chunk-2')],
    }),
  }

  const firstView = toChatTurnView(firstTurn)
  const secondView = toChatTurnView(secondTurn)

  assert.equal(firstView.answer?.blocks[0]?.citations[0]?.key, 'turn-1:P1')
  assert.equal(secondView.answer?.blocks[0]?.citations[0]?.key, 'turn-2:P1')
  assert.notEqual(
    firstView.answer?.blocks[0]?.citations[0]?.fileId,
    secondView.answer?.blocks[0]?.citations[0]?.fileId,
  )
})

test('preserves router documents and answer warnings', () => {
  const view = toChatAnswerView(
    answer({
      selectedDocuments: [{
        fileId: 'file-1',
        versionId: 'file-1',
        reason: 'Relevant policy',
        confidence: 0.9,
      }],
      warnings: ['Page 2 was unavailable.'],
    }),
    'turn-1',
  )

  assert.equal(view.selectedDocuments[0]?.fileId, 'file-1')
  assert.deepEqual(view.warnings, ['Page 2 was unavailable.'])
})

test('does not link missing or ambiguous citations', () => {
  const view = toChatAnswerView(
    answer({
      answerBlocks: [{
        text: 'Answer',
        reasoning: '',
        citationIds: ['P1', 'P2'],
      }],
      citations: [
        citation('P1', 'first', 'chunk-1'),
        citation('P1', 'second', 'chunk-2'),
      ],
    }),
    'turn-1',
  )

  assert.deepEqual(view.blocks[0]?.citations, [])
  assert.deepEqual(view.blocks[0]?.unresolvedCitationIds, ['P1', 'P2'])
  assert.ok(view.warnings.some((warning) => warning.includes('Ambiguous PDF citation "P1"')))
  assert.ok(view.warnings.some((warning) => warning.includes('citation "P2"')))
})
