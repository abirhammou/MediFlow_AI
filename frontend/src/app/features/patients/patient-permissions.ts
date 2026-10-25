import { Injectable, Signal, computed, inject } from '@angular/core';
import { AuthService, Role } from '../../core/auth/auth.service';

/** Same matrix as PATIENT_ROLES in backend/app/modules/patients/router.py. */
export const PATIENT_ROLES = {
  read: ['SECRETARY', 'DOCTOR', 'ADMIN'],
  write: ['SECRETARY', 'ADMIN'],
  restore: ['ADMIN'],
} as const satisfies Record<string, readonly Role[]>;

/** Same matrix as SUMMARY_ROLES in backend/app/modules/patients/summary_router.py. */
export const SUMMARY_ROLES = {
  generate: ['DOCTOR', 'ADMIN'],
  history: ['DOCTOR', 'ADMIN'],
  current: ['SECRETARY', 'DOCTOR', 'ADMIN'],
  review: ['DOCTOR'],
} as const satisfies Record<string, readonly Role[]>;

/** Hides the actions a role cannot use; the API enforces them anyway. */
@Injectable({ providedIn: 'root' })
export class PatientPermissions {
  private auth = inject(AuthService);

  private has(roles: readonly Role[]): Signal<boolean> {
    return computed(() => {
      const role = this.auth.user()?.role;
      return role !== undefined && roles.includes(role);
    });
  }

  readonly canWrite = this.has(PATIENT_ROLES.write);
  readonly canRestore = this.has(PATIENT_ROLES.restore);
  readonly canGenerateSummary = this.has(SUMMARY_ROLES.generate);
  readonly canSeeSummaryHistory = this.has(SUMMARY_ROLES.history);
  readonly canReviewSummary = this.has(SUMMARY_ROLES.review);
}
