import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

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
  page: number;
  page_size: number;
}

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
    return this.http.get<AppointmentPage>(this.base, { params });
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
