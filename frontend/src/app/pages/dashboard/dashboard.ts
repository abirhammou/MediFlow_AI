import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { AuthService, ROLE_LABELS, Role, apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';

interface DashboardKpi {
  key: string;
  label: string;
  value: number | Record<string, number>;
}

interface DashboardAlert {
  key: string;
  message?: string;
  start_at?: string;
  status?: string;
  reason?: string | null;
}

interface DashboardSummary {
  role: Role;
  full_name: string;
  kpis: DashboardKpi[];
  alerts: DashboardAlert[];
}

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'En attente',
  CONFIRMED: 'Confirmé',
  CANCELLED: 'Annulé',
  COMPLETED: 'Terminé',
  NO_SHOW: 'Absent',
};

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'full', timeStyle: 'short' });

@Component({
  selector: 'app-dashboard',
  imports: [Icon],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard {
  protected auth = inject(AuthService);
  private http = inject(HttpClient);

  summary = signal<DashboardSummary | null>(null);
  error = signal<string | null>(null);

  constructor() {
    if (!this.auth.user()) this.auth.loadProfile().subscribe({ error: () => {} });
    this.http.get<DashboardSummary>('/api/dashboard/summary').subscribe({
      next: summary => this.summary.set(summary),
      error: err => this.error.set(apiErrorMessage(err)),
    });
  }

  roleLabel(role: Role | string): string {
    return ROLE_LABELS[role as Role] ?? role;
  }

  statusLabel(status: string | undefined): string {
    return status ? (STATUS_LABELS[status] ?? status) : '';
  }

  formatDate(value: string | undefined): string {
    return value ? DATE_FORMAT.format(new Date(value)) : '';
  }

  isBreakdown(value: DashboardKpi['value']): value is Record<string, number> {
    return typeof value === 'object' && value !== null;
  }

  breakdown(value: Record<string, number>): { label: string; count: number }[] {
    return Object.entries(value).map(([role, count]) => ({ label: this.roleLabel(role), count }));
  }
}
