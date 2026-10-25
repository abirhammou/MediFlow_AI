import { Injectable, Signal, computed, inject } from '@angular/core';
import { AuthService, Role } from '../../core/auth/auth.service';
import { ReportListItem } from '../../pages/report-writer/reports.api';
import { BILLING_ROLES } from '../billing/billing.model';
import { FileCategory } from './patient-file.model';

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

/** Same matrix as backend/app/modules/reports/router.py (PATIENT reads in its own portal). */
export const REPORT_ROLES = {
  read: ['SECRETARY', 'DOCTOR', 'ADMIN'],
  write: ['DOCTOR'],
} as const satisfies Record<string, readonly Role[]>;

/** Same matrix as HISTORY_ROLES in backend/app/modules/patient_history/router.py. */
export const HISTORY_ROLES = {
  use: ['DOCTOR', 'ADMIN'],
  review: ['DOCTOR'],
} as const satisfies Record<string, readonly Role[]>;

/** Same matrix as FILE_ROLES in backend/app/modules/patient_files/service.py. */
export const FILE_ROLES = {
  ADMINISTRATIVE: { read: ['SECRETARY', 'ADMIN', 'PATIENT'], write: ['SECRETARY', 'ADMIN'] },
  MEDICAL: { read: ['DOCTOR', 'SECRETARY', 'ADMIN', 'PATIENT'], write: ['SECRETARY', 'ADMIN'] },
} as const satisfies Record<FileCategory, { read: readonly Role[]; write: readonly Role[] }>;

export function fileCategoriesFor(role: Role | undefined, action: 'read' | 'write'): FileCategory[] {
  return (Object.keys(FILE_ROLES) as FileCategory[]).filter(
    (category) => role !== undefined && (FILE_ROLES[category][action] as readonly Role[]).includes(role),
  );
}

/** Only the author edits or finalizes a report, and only while it is a DRAFT (reports/service.py). */
export function canEditReport(
  role: Role | undefined,
  report: Pick<ReportListItem, 'is_mine' | 'status'>,
): boolean {
  return role === 'DOCTOR' && report.is_mine && report.status === 'DRAFT';
}

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
  readonly canReadReports = this.has(REPORT_ROLES.read);
  readonly canWriteReports = this.has(REPORT_ROLES.write);
  readonly canManageBilling = this.has(BILLING_ROLES.manage);
  readonly canUseMedicalAi = this.has(HISTORY_ROLES.use);
  readonly canReviewMedicalAi = this.has(HISTORY_ROLES.review);
  readonly readableFileCategories = computed(() => fileCategoriesFor(this.auth.user()?.role, 'read'));
  readonly writableFileCategories = computed(() => fileCategoriesFor(this.auth.user()?.role, 'write'));

  canEditReport(report: Pick<ReportListItem, 'is_mine' | 'status'>): boolean {
    return canEditReport(this.auth.user()?.role, report);
  }
}
