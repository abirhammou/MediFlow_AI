import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

/** /api/portal: the signed-in patient's own data (camelCase). */

export interface PortalProfile {
  patientId: string;
  recordNumber: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  gender: 'MALE' | 'FEMALE' | 'OTHER';
  bloodType: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  insuranceProvider: string | null;
  insuranceNumber: string | null;
}

export interface PortalFollowUp {
  id: string;
  description: string;
  dueDate: string | null;
  status: 'TODO' | 'IN_PROGRESS' | 'DONE';
}

@Injectable({ providedIn: 'root' })
export class PortalService {
  private http = inject(HttpClient);

  me(): Observable<PortalProfile> {
    return this.http.get<PortalProfile>('/api/portal/me');
  }

  followUps(): Observable<PortalFollowUp[]> {
    return this.http.get<PortalFollowUp[]>('/api/portal/follow-ups');
  }
}
