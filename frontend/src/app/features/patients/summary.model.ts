import { HttpErrorResponse } from '@angular/common/http';
import { apiErrorMessage } from '../../core/auth/auth.service';

/** Shapes of the /api/patients/{id}/summaries JSON (camelCase). */

export type SummaryStatus = 'DRAFT' | 'VALIDATED' | 'REJECTED' | 'SUPERSEDED';

export const SUMMARY_STATUS_LABELS: Record<SummaryStatus, string> = {
  DRAFT: 'Brouillon',
  VALIDATED: 'Validé',
  REJECTED: 'Rejeté',
  SUPERSEDED: 'Remplacé',
};

export interface PatientSummary {
  id: string;
  patientId: string;
  content: string;
  status: SummaryStatus;
  /** Model actually used, e.g. 'gemini/gemini-3.8-flash' (the fallback when the primary failed). */
  llmModel: string | null;
  promptVersion: string | null;
  /** Exactly what the model received (no name, CIN, phone, email or insurance number). */
  sourceSnapshot: Record<string, unknown> | null;
  /** The patient record changed after generation. */
  isOutdated: boolean;
  generatedBy: string | null;
  generatedByName: string | null;
  reviewedBy: string | null;
  reviewedByName: string | null;
  reviewedAt: string | null;
  reviewComment: string | null;
  createdAt: string;
}

/** Errors of the AI calls in plain French; anything else falls back to the API message. */
export function summaryErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    switch (error.status) {
      case 503:
        return 'Le service IA est momentanément indisponible. Réessayez dans quelques minutes.';
      case 429:
        return 'Limite atteinte : 10 générations de résumé par heure. Réessayez plus tard.';
      case 502:
        return "L'IA a renvoyé une réponse inutilisable. Relancez la génération.";
    }
  }
  return apiErrorMessage(error);
}
