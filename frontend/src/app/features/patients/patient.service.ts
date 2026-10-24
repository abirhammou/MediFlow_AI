import { HttpClient, HttpParameterCodec, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  DeletedPatientItem,
  Page,
  Patient,
  PatientListItem,
  PatientPayload,
  PatientQuery,
} from './patient.model';

/**
 * Angular's default codec leaves '+' unencoded and the server reads it as a
 * space: the "A+" blood type would arrive as "A ".
 */
const STRICT_CODEC: HttpParameterCodec = {
  encodeKey: encodeURIComponent,
  encodeValue: encodeURIComponent,
  decodeKey: decodeURIComponent,
  decodeValue: decodeURIComponent,
};

// Relative URL: the dev proxy forwards /api, and authInterceptor only adds the token to /api/ calls.
const API = '/api/patients';

function params(values: object): HttpParams {
  let result = new HttpParams({ encoder: STRICT_CODEC });
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== null && value !== '')
      result = result.set(key, String(value));
  }
  return result;
}

function url(id: string, suffix = ''): string {
  return `${API}/${encodeURIComponent(id)}${suffix}`;
}

@Injectable({ providedIn: 'root' })
export class PatientService {
  private http = inject(HttpClient);

  list(query: PatientQuery): Observable<Page<PatientListItem>> {
    return this.http.get<Page<PatientListItem>>(API, { params: params(query) });
  }

  get(id: string): Observable<Patient> {
    return this.http.get<Patient>(url(id));
  }

  create(payload: PatientPayload): Observable<Patient> {
    return this.http.post<Patient>(API, payload);
  }

  /** PATCH: only the fields sent change; `null` clears an optional field. */
  update(id: string, changes: Partial<PatientPayload>): Observable<Patient> {
    return this.http.patch<Patient>(url(id), changes);
  }

  /** Soft delete. */
  remove(id: string): Observable<void> {
    return this.http.delete<void>(url(id));
  }

  listDeleted(page: number, size: number): Observable<Page<DeletedPatientItem>> {
    return this.http.get<Page<DeletedPatientItem>>(`${API}/deleted`, {
      params: params({ page, size }),
    });
  }

  restore(id: string): Observable<Patient> {
    return this.http.post<Patient>(url(id, '/restore'), null);
  }

  findDuplicates(
    firstName: string,
    lastName: string,
    dateOfBirth: string,
  ): Observable<PatientListItem[]> {
    return this.http.get<PatientListItem[]>(`${API}/duplicates`, {
      params: params({ firstName, lastName, dateOfBirth }),
    });
  }
}
