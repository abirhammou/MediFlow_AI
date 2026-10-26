import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Appointment, AppointmentPage, AppointmentStatus, Doctor, Slot } from './appointments.model';

const BASE = '/api/booking';

@Injectable({ providedIn: 'root' })
export class AppointmentsService {
  private http = inject(HttpClient);

  doctors(): Observable<Doctor[]> {
    return this.http.get<Doctor[]>(`${BASE}/doctors`);
  }

  /** Free slots of a doctor (default: the next 14 days). */
  slots(doctorId: string, from?: string, to?: string): Observable<Slot[]> {
    let params = new HttpParams().set('doctorId', doctorId);
    if (from) params = params.set('from', from);
    if (to) params = params.set('to', to);
    return this.http.get<Slot[]>(`${BASE}/slots`, { params });
  }

  /** PATIENT: their own; staff: filters. */
  list(query: { status?: AppointmentStatus; upcoming?: boolean; patientId?: string; page?: number; size?: number }): Observable<AppointmentPage> {
    let params = new HttpParams().set('page', query.page ?? 1).set('size', query.size ?? 50);
    if (query.status) params = params.set('status', query.status);
    if (query.upcoming) params = params.set('upcoming', true);
    if (query.patientId) params = params.set('patientId', query.patientId);
    return this.http.get<AppointmentPage>(BASE, { params });
  }

  /** PATIENT: a PENDING request for their own record; staff: pass `patientId`. */
  book(doctorId: string, startAt: string, reason: string | null, patientId?: string): Observable<Appointment> {
    return this.http.post<Appointment>(BASE, { doctorId, startAt, reason, ...(patientId ? { patientId } : {}) });
  }

  confirm(id: string): Observable<Appointment> {
    return this.http.post<Appointment>(`${BASE}/${encodeURIComponent(id)}/confirm`, null);
  }

  cancel(id: string, reason: string): Observable<Appointment> {
    return this.http.post<Appointment>(`${BASE}/${encodeURIComponent(id)}/cancel`, { reason });
  }
}
