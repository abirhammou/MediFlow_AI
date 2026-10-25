import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { PatientSummary } from './summary.model';

// Relative URL: the dev proxy forwards /api, and authInterceptor only adds the token to /api/ calls.
function url(patientId: string, suffix = ''): string {
  return `/api/patients/${encodeURIComponent(patientId)}/summaries${suffix}`;
}

function summaryUrl(patientId: string, summaryId: string, suffix = ''): string {
  return url(patientId, `/${encodeURIComponent(summaryId)}${suffix}`);
}

@Injectable({ providedIn: 'root' })
export class SummaryService {
  private http = inject(HttpClient);

  /** New DRAFT written by the AI (can take several seconds). */
  generate(patientId: string): Observable<PatientSummary> {
    return this.http.post<PatientSummary>(url(patientId, '/generate'), null);
  }

  /** Every version, newest first (DOCTOR, ADMIN). */
  list(patientId: string): Observable<PatientSummary[]> {
    return this.http.get<PatientSummary[]>(url(patientId));
  }

  /** The VALIDATED summary; 404 when there is none. */
  current(patientId: string): Observable<PatientSummary> {
    return this.http.get<PatientSummary>(url(patientId, '/current'));
  }

  /** Edit the text of a DRAFT (409 otherwise). */
  update(patientId: string, summaryId: string, content: string): Observable<PatientSummary> {
    return this.http.patch<PatientSummary>(summaryUrl(patientId, summaryId), { content });
  }

  validate(patientId: string, summaryId: string): Observable<PatientSummary> {
    return this.http.post<PatientSummary>(summaryUrl(patientId, summaryId, '/validate'), null);
  }

  reject(patientId: string, summaryId: string, comment: string): Observable<PatientSummary> {
    return this.http.post<PatientSummary>(summaryUrl(patientId, summaryId, '/reject'), {
      comment,
    });
  }
}
