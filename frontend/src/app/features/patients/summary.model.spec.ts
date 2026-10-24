import { HttpErrorResponse } from '@angular/common/http';
import { describe, expect, it } from 'vitest';
import { summaryErrorMessage } from './summary.model';

function httpError(status: number, detail?: string): HttpErrorResponse {
  return new HttpErrorResponse({ status, error: detail ? { detail } : null });
}

describe('summaryErrorMessage', () => {
  it('explains the AI errors in French', () => {
    expect(summaryErrorMessage(httpError(503))).toContain('momentanément indisponible');
    expect(summaryErrorMessage(httpError(429))).toContain('10 générations');
    expect(summaryErrorMessage(httpError(502))).toContain('Relancez la génération');
  });

  it('falls back to the API message', () => {
    expect(summaryErrorMessage(httpError(409, 'Seul un brouillon peut être validé.'))).toBe(
      'Seul un brouillon peut être validé.',
    );
  });
});
