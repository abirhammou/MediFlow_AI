import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, forkJoin, map, of, tap } from 'rxjs';

export interface PatientOption {
  id: string;
  name: string;
  recordNumber: string;
}

export interface DoctorOption {
  id: string;
  name: string;
}

interface PatientDto {
  id: string;
  firstName: string;
  lastName: string;
  recordNumber: string;
}

/** Noms des patients et des médecins (les rendez-vous ne contiennent que des identifiants). */
@Injectable({ providedIn: 'root' })
export class DirectoryService {
  private readonly http = inject(HttpClient);

  readonly patientNames = signal<Record<string, string>>({});
  readonly doctorNames = signal<Record<string, string>>({});

  private fullName(p: { firstName: string; lastName: string }): string {
    return `${p.firstName} ${p.lastName}`.trim();
  }

  searchPatients(q: string): Observable<PatientOption[]> {
    let params = new HttpParams().set('size', 8).set('sort', 'lastName');
    if (q.trim()) params = params.set('q', q.trim());
    return this.http.get<{ items: PatientDto[] }>('/api/patients', { params }).pipe(
      map(page => page.items.map(p => ({ id: p.id, name: this.fullName(p), recordNumber: p.recordNumber }))),
      tap(options => this.remember(options)),
      catchError(() => of([] as PatientOption[])),
    );
  }

  /** Charge les noms manquants (un appel par patient inconnu, 10 au plus par page de rendez-vous). */
  resolvePatients(ids: string[]): void {
    const known = this.patientNames();
    const missing = [...new Set(ids)].filter(id => id && !(id in known));
    if (!missing.length) return;
    forkJoin(
      missing.map(id =>
        this.http.get<PatientDto>(`/api/patients/${encodeURIComponent(id)}`).pipe(catchError(() => of(null))),
      ),
    ).subscribe(patients => {
      const found: Record<string, string> = {};
      patients.forEach((p, i) => {
        if (p) found[missing[i]] = this.fullName(p);
      });
      this.patientNames.update(names => ({ ...names, ...found }));
    });
  }

  /** Médecins via /api/users (réservé à l'admin) : sans droit, on retourne une liste vide. */
  loadDoctors(): Observable<DoctorOption[]> {
    return this.http
      .get<{ items: { id: string; first_name: string; last_name: string; is_active: boolean }[] }>(
        '/api/users',
        { params: new HttpParams().set('role', 'DOCTOR').set('size', 100) },
      )
      .pipe(
        map(page =>
          page.items
            .filter(u => u.is_active)
            .map(u => ({ id: u.id, name: `Dr ${u.first_name} ${u.last_name}`.trim() })),
        ),
        tap(doctors =>
          this.doctorNames.set(Object.fromEntries(doctors.map(d => [d.id, d.name]))),
        ),
        catchError(() => of([] as DoctorOption[])),
      );
  }

  patientName(id: string): string {
    return this.patientNames()[id] ?? `Patient …${id.slice(-5)}`;
  }

  doctorName(id: string): string {
    return this.doctorNames()[id] ?? `Médecin …${id.slice(-5)}`;
  }

  private remember(options: PatientOption[]): void {
    this.patientNames.update(names => ({
      ...names,
      ...Object.fromEntries(options.map(o => [o.id, o.name])),
    }));
  }
}