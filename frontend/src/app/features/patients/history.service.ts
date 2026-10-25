import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ChatAnswer, ChatTurn, HistoryScope, HistorySummary } from './history.model';

function url(patientId: string, suffix = ''): string {
  return `/api/patients/${encodeURIComponent(patientId)}${suffix}`;
}

function summaryUrl(patientId: string, summaryId: string, suffix = ''): string {
  return url(patientId, `/history-summaries/${encodeURIComponent(summaryId)}${suffix}`);
}

@Injectable({ providedIn: 'root' })
export class HistoryService {
  private http = inject(HttpClient);

  /** New DRAFT: the whole history, or one report (can take several seconds). */
  generate(patientId: string, scope: HistoryScope, reportId?: string | null): Observable<HistorySummary> {
    return this.http.post<HistorySummary>(url(patientId, '/history-summaries/generate'), {
      scope,
      reportId: reportId ?? null,
    });
  }

  /** Every version of a scope (and report), newest first. */
  list(patientId: string, scope: HistoryScope, reportId?: string | null): Observable<HistorySummary[]> {
    let params = new HttpParams().set('scope', scope);
    if (reportId) params = params.set('reportId', reportId);
    return this.http.get<HistorySummary[]>(url(patientId, '/history-summaries'), { params });
  }

  update(patientId: string, summaryId: string, content: string): Observable<HistorySummary> {
    return this.http.patch<HistorySummary>(summaryUrl(patientId, summaryId), { content });
  }

  validate(patientId: string, summaryId: string): Observable<HistorySummary> {
    return this.http.post<HistorySummary>(summaryUrl(patientId, summaryId, '/validate'), null);
  }

  reject(patientId: string, summaryId: string, comment: string): Observable<HistorySummary> {
    return this.http.post<HistorySummary>(summaryUrl(patientId, summaryId, '/reject'), { comment });
  }

  /** Answer grounded in the patient record only; nothing is stored. */
  ask(patientId: string, question: string, history: ChatTurn[]): Observable<ChatAnswer> {
    return this.http.post<ChatAnswer>(url(patientId, '/chat'), { question, history });
  }
}
