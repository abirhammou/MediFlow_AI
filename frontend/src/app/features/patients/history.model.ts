import { HttpErrorResponse } from '@angular/common/http';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { SummaryStatus } from './summary.model';

/** Shapes of /api/patients/{id}/history-summaries and /chat (camelCase). */

export type HistoryScope = 'TIMELINE' | 'REPORT';
export type SourceKind = 'REPORT' | 'FILE' | 'NOTES';

export interface ChatSource {
  id: string; // "S1"
  kind: SourceKind;
  refId: string | null;
  label: string;
}

export interface HistorySummary {
  id: string;
  patientId: string;
  scope: HistoryScope;
  reportId: string | null;
  content: string;
  status: SummaryStatus;
  llmModel: string | null;
  promptVersion: string | null;
  /** What the model read when the summary was generated. */
  sources: ChatSource[];
  /** A source was added, removed or changed since. */
  isOutdated: boolean;
  generatedBy: string | null;
  generatedByName: string | null;
  reviewedBy: string | null;
  reviewedByName: string | null;
  reviewedAt: string | null;
  reviewComment: string | null;
  createdAt: string;
}

export interface ChatTurn {
  question: string;
  answer: string;
}

export interface ChatAnswer {
  found: boolean;
  answer: string;
  sources: ChatSource[];
  llmModel: string | null;
}

export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  REPORT: 'Compte rendu',
  FILE: 'Document',
  NOTES: 'Notes',
};

/** The backend keeps at most 6 previous turns. */
export const MAX_CHAT_HISTORY = 6;

/** Errors of the AI calls in plain French; anything else falls back to the API message. */
export function aiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    switch (error.status) {
      case 503:
        return 'Le service IA est momentanément indisponible. Réessayez dans quelques minutes.';
      case 429:
        return "Limite d'utilisation de l'IA atteinte pour cette heure. Réessayez plus tard.";
      case 502:
        return "L'IA a renvoyé une réponse inutilisable. Relancez la demande.";
    }
  }
  return apiErrorMessage(error);
}

/** Splits an answer into text and [Sx] citation chips. */
export function citationParts(text: string): { text: string; source?: string }[] {
  const parts: { text: string; source?: string }[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[(S\d+)\]/g)) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    parts.push({ text: match[1], source: match[1] });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
