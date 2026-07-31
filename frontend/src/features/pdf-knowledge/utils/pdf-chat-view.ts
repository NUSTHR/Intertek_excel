import type {
  PdfAnswerBlockView,
  PdfChatAnswer,
  PdfChatAnswerView,
  PdfChatTurn,
  PdfChatTurnView,
  PdfCitation,
} from '../types.ts'
import {
  normalizePdfDisplayText,
  optionalTrimmedText,
  pdfCitationLocationLabel,
  pdfCitationMatchLabel,
} from './pdf-citation-presentation.ts'

export function toChatTurnView(turn: PdfChatTurn): PdfChatTurnView {
  return toAnsweredChatTurn(
    turn.answer,
    turn.turnId,
    turn.sessionId,
    turn.question,
    turn.createdAt,
  )
}

export function toAnsweredChatTurn(
  answer: PdfChatAnswer,
  turnId: string,
  sessionId: string,
  question = answer.question,
  createdAt = answer.createdAt,
): PdfChatTurnView {
  return {
    turnId,
    sessionId,
    question,
    createdAt,
    status: 'complete',
    answer: toChatAnswerView(answer, turnId),
  }
}

export function toPendingChatTurn(
  turnId: string,
  sessionId: string,
  question: string,
): PdfChatTurnView {
  return {
    turnId,
    sessionId,
    question,
    createdAt: new Date().toISOString(),
    status: 'pending',
  }
}

export function toFailedChatTurn(
  turnId: string,
  sessionId: string,
  question: string,
  errorMessage: string,
): PdfChatTurnView {
  return {
    turnId,
    sessionId,
    question,
    createdAt: new Date().toISOString(),
    status: 'failed',
    errorMessage,
  }
}

export function toChatAnswerView(
  answer: PdfChatAnswer,
  turnId: string,
): PdfChatAnswerView {
  const citationCounts = new Map<string, number>()
  for (const citation of answer.citations) {
    citationCounts.set(
      citation.citationId,
      (citationCounts.get(citation.citationId) ?? 0) + 1,
    )
  }
  const ambiguousCitationIds = new Set(
    Array.from(citationCounts.entries())
      .filter(([, count]) => count > 1)
      .map(([citationId]) => citationId),
  )
  const citations = answer.citations
    .filter((citation) => !ambiguousCitationIds.has(citation.citationId))
    .map((citation, index) => toSourceCitation(citation, turnId, index))
  const citationsById = new Map(
    citations.map((citation) => [citation.citationId, citation]),
  )
  const blocks = answer.answerBlocks.map<PdfAnswerBlockView>((block, blockIndex) => {
    const blockCitations: PdfCitation[] = []
    const unresolvedCitationIds: string[] = []
    const seenCitationIds = new Set<string>()
    for (const citationId of block.citationIds) {
      if (seenCitationIds.has(citationId)) {
        continue
      }
      seenCitationIds.add(citationId)
      const citation = citationsById.get(citationId)
      if (citation) {
        blockCitations.push(citation)
      } else {
        unresolvedCitationIds.push(citationId)
      }
    }
    return {
      id: `${turnId}-block-${blockIndex}`,
      text: block.text.trim() || 'No answer text was generated.',
      reasoning: block.reasoning.trim(),
      citations: blockCitations,
      unresolvedCitationIds,
    }
  })
  const citationWarnings = Array.from(ambiguousCitationIds)
    .sort()
    .map((citationId) => `Ambiguous PDF citation "${citationId}" was not linked.`)
  const unresolvedCitationIds = Array.from(
    new Set(blocks.flatMap((block) => block.unresolvedCitationIds)),
  )
  const unresolvedWarnings = unresolvedCitationIds
    .filter((citationId) => !ambiguousCitationIds.has(citationId))
    .sort()
    .map((citationId) => `PDF citation "${citationId}" could not be resolved.`)
  return {
    blocks,
    citations,
    selectedDocuments: answer.selectedDocuments,
    warnings: [...answer.warnings, ...citationWarnings, ...unresolvedWarnings],
    insufficientEvidence: answer.insufficientEvidence,
  }
}

function toSourceCitation(
  citation: PdfChatAnswer['citations'][number],
  turnId: string,
  index: number,
): PdfCitation {
  const pageLabel = optionalTrimmedText(citation.pageLabel)
  return {
    key: `${turnId}:${citation.citationId}`,
    turnId,
    citationId: citation.citationId,
    evidenceId: citation.evidenceId,
    fileId: citation.fileId,
    chunkId: citation.chunkId,
    chunkIndex: citation.chunkIndex,
    pageLabel,
    title: normalizePdfDisplayText(citation.title),
    quote: normalizePdfDisplayText(citation.quote),
    sourceLabel: citation.citationId,
    fileName: citation.fileName,
    fileKind: 'pdf',
    matchLabel: pdfCitationMatchLabel(pageLabel, citation.chunkIndex),
    excerpt: normalizePdfDisplayText(citation.quote),
    location: pdfCitationLocationLabel(pageLabel, citation.chunkIndex),
    // This preserves the established card colors only. It is not an evidence rank.
    visualTone: index === 0 ? 'primary' : 'supporting',
  }
}
