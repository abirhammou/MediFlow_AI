import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type ReportStatus = 'DRAFT' | 'FINAL' | 'ARCHIVED';

export interface ReportListItem {
  id: string;
  patient_id: string;
  doctor_id: string;
  appointment_id: string | null;
  title: string;
  status: ReportStatus;
  has_structured_content: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportOut extends Omit<ReportListItem, 'has_structured_content'> {
  raw_notes: string;
  structured_content: string | null;
  warnings: string[];
}

export interface ReportPage {
  items: ReportListItem[];
  total: number;
  page: number;
  size: number;
}

export interface ReportQuery {
  status?: ReportStatus | '';
  patient_id?: string;
  q?: string;
  page: number;
  size: number;
}

/** Admin : lecture de tous les comptes rendus + archivage (le reste est réservé au médecin). */
@Injectable({ providedIn: 'root' })
export class ReportsApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/reports'; // adapte avec ton environment.apiUrl / proxy

  list(query: ReportQuery): Observable<ReportPage> {
    let params = new HttpParams().set('page', query.page).set('size', query.size);
    if (query.status) params = params.set('status', query.status);
    if (query.patient_id?.trim()) params = params.set('patient_id', query.patient_id.trim());
    if (query.q?.trim()) params = params.set('q', query.q.trim());
    return this.http.get<ReportPage>(this.base, { params });
  }

  get(id: string): Observable<ReportOut> {
    return this.http.get<ReportOut>(`${this.base}/${id}`);
  }

  archive(id: string): Observable<ReportOut> {
    return this.http.post<ReportOut>(`${this.base}/${id}/archive`, {});
  }
}