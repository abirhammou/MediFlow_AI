import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, forkJoin, map, of } from 'rxjs';

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

export interface ReportCreate {
  patient_id: string;
  appointment_id?: string | null;
  title: string;
  raw_notes: string;
}

export interface ReportUpdate {
  title?: string;
  raw_notes?: string;
  structured_content?: string;
}

export interface ReportStats {
  draft: number;
  final: number;
  archived: number;
  recent: ReportListItem[]; // 100 derniers brouillons/finalisés, pour le graphique d'activité
}

/** Admin : lecture de tous les comptes rendus + archivage (le reste est réservé au médecin). */
@Injectable({ providedIn: 'root' })
export class ReportsApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/reports';

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

  // ── Actions du médecin ──
  create(body: ReportCreate): Observable<ReportOut> {
    return this.http.post<ReportOut>(this.base, body);
  }

  update(id: string, body: ReportUpdate): Observable<ReportOut> {
    return this.http.patch<ReportOut>(`${this.base}/${id}`, body);
  }

  generate(id: string): Observable<ReportOut> {
    return this.http.post<ReportOut>(`${this.base}/${id}/generate`, {});
  }

  finalize(id: string, confirmWarnings = false): Observable<ReportOut> {
    return this.http.post<ReportOut>(`${this.base}/${id}/finalize`, { confirm_warnings: confirmWarnings });
  }

  archive(id: string): Observable<ReportOut> {
    return this.http.post<ReportOut>(`${this.base}/${id}/archive`, {});
  }

  /** Pas d'endpoint de stats côté backend : on lit les `total` de pages d'un seul élément. */
  stats(): Observable<ReportStats> {
    const one = (status: ReportStatus) => this.list({ status, page: 1, size: 1 }).pipe(map((p) => p.total));
    return forkJoin({
      draft: one('DRAFT'),
      final: one('FINAL'),
      archived: one('ARCHIVED'),
      recent: this.list({ page: 1, size: 100 }).pipe(map((p) => p.items)),
    });
  }

  /**
   * Noms des médecins via /api/users (réservé à l'admin). Si l'endpoint est absent ou refuse l'accès,
   * on retourne {} et l'interface retombe sur les identifiants.
   */
  doctors(): Observable<Record<string, string>> {
    return this.http.get<unknown>('/api/users').pipe(
      map((res) => {
        const list = (Array.isArray(res) ? res : ((res as { items?: unknown[] })?.items ?? [])) as Record<string, unknown>[];
        const names: Record<string, string> = {};
        for (const u of list) {
          const id = String(u['id'] ?? u['_id'] ?? '');
          const name = [u['first_name'], u['last_name']].filter(Boolean).join(' ');
          if (id && name) names[id] = u['role'] === 'DOCTOR' ? `Dr ${name}` : name;
        }
        return names;
      }),
      catchError(() => of({} as Record<string, string>)),
    );
  }
}