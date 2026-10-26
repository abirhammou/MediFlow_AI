import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin, map } from 'rxjs';

export type AppointmentStatus = 'PENDING' | 'CONFIRMED' | 'CANCELLED' | 'COMPLETED' | 'NO_SHOW';

export const STATUS_LABELS: Record<AppointmentStatus, string> = {
  PENDING: 'En attente',
  CONFIRMED: 'Confirmé',
  CANCELLED: 'Annulé',
  COMPLETED: 'Terminé',
  NO_SHOW: 'Absent',
};

export interface Appointment {
  id: string;
  patient_id: string;
  doctor_id: string;
  start_at: string;
  end_at: string;
  reason: string | null;
  status: AppointmentStatus;
  cancel_reason: string | null;
}

export interface AppointmentPage {
  items: Appointment[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppointmentQuery {
  status?: AppointmentStatus | '';
  patient_id?: string;
  doctor_id?: string;
  date_from?: string; // ISO 8601
  date_to?: string; // ISO 8601, exclu
  page: number;
  page_size: number;
}

export type StatusCounts = Record<AppointmentStatus, number>;

export interface AppointmentCreate {
  patient_id: string;
  doctor_id: string;
  start_at: string;
  end_at?: string | null;
  reason?: string | null;
  request_id?: string | null;
}

export interface Slot {
  doctor_id: string;
  doctor_name: string;
  start_at: string;
  end_at: string;
}

export interface ParseResult {
  request_id: string;
  parsed: { preferred_date: string | null; day_part: string | null; specialty: string | null; reason: string | null };
  available_slots: Slot[];
}

@Injectable({ providedIn: 'root' })
export class AppointmentsApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/appointments';

  list(q: AppointmentQuery): Observable<AppointmentPage> {
    let params = new HttpParams().set('page', q.page).set('page_size', q.page_size);
    if (q.status) params = params.set('status', q.status);
    if (q.patient_id?.trim()) params = params.set('patient_id', q.patient_id.trim());
    if (q.doctor_id?.trim()) params = params.set('doctor_id', q.doctor_id.trim());
    if (q.date_from) params = params.set('date_from', q.date_from);
    if (q.date_to) params = params.set('date_to', q.date_to);
    return this.http.get<AppointmentPage>(this.base, { params });
  }

  /** Pas d'endpoint de statistiques : on lit le `total` d'une page d'un seul élément par statut. */
  counts(): Observable<StatusCounts> {
    const statuses = Object.keys(STATUS_LABELS) as AppointmentStatus[];
    const one = (status: AppointmentStatus) =>
      this.list({ status, page: 1, page_size: 1 }).pipe(map(p => p.total));
    return forkJoin(statuses.map(one)).pipe(
      map(totals => Object.fromEntries(statuses.map((s, i) => [s, totals[i]])) as StatusCounts),
    );
  }

  /** Rendez-vous d'une période (100 maximum), pour le graphique par jour. */
  window(date_from: string, date_to: string): Observable<Appointment[]> {
    return this.list({ date_from, date_to, page: 1, page_size: 100 }).pipe(map(p => p.items));
  }

  create(body: AppointmentCreate): Observable<Appointment> {
    return this.http.post<Appointment>(this.base, body);
  }

  update(id: string, body: { status?: AppointmentStatus; start_at?: string; end_at?: string; reason?: string }): Observable<Appointment> {
    return this.http.put<Appointment>(`${this.base}/${id}`, body);
  }

  cancel(id: string, cancel_reason: string | null): Observable<Appointment> {
    return this.http.post<Appointment>(`${this.base}/${id}/cancel`, { cancel_reason });
  }

  parseRequest(message: string, patient_id?: string): Observable<ParseResult> {
    return this.http.post<ParseResult>(`${this.base}/parse-request`, { message, patient_id: patient_id || null });
  }
}