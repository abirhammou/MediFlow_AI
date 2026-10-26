import { HttpClient } from '@angular/common/http';
import { Component, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
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

// Médecin affiché dans la sidebar
interface DoctorCard {
  id: string;
  name: string;
  initials: string;
  specialty: string;
  available: boolean;
}

// Note de suivi
interface FollowupNote {
  id: string;
  patient_name: string;
  description: string;
  due_date: string;
  status: 'pending' | 'done' | 'cancelled';
}

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'En attente', CONFIRMED: 'Confirmé',
  CANCELLED: 'Annulé', COMPLETED: 'Terminé', NO_SHOW: 'Absent',
};

const STATUS_COLORS: Record<string, string> = {
  PENDING: '#f59e0b', CONFIRMED: '#22c55e',
  CANCELLED: '#ef4444', COMPLETED: '#3b82f6', NO_SHOW: '#8b5cf6',
};

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', { dateStyle: 'full', timeStyle: 'short' });

// KPI metadata : icône, couleur, lien de navigation
const KPI_META: Record<string, { icon: string; color: string; bg: string; route?: string }> = {
  patients:           { icon: 'users',      color: '#3b82f6', bg: '#eff6ff',  route: '/patient-records' },
  appointments_today: { icon: 'calendar',   color: '#8b5cf6', bg: '#faf5ff',  route: '/appointment-manager' },
  confirmed_today:    { icon: 'shield',     color: '#22c55e', bg: '#f0fdf4',  route: '/appointment-manager' },
  pending_appts:      { icon: 'bell',       color: '#f59e0b', bg: '#fefce8',  route: '/appointment-manager' },
  followup_pending:   { icon: 'activity',   color: '#ef4444', bg: '#fef2f2',  route: '/follow-up' },
  followup_done:      { icon: 'zap',        color: '#10b981', bg: '#ecfdf5',  route: '/follow-up' },
  total_users:        { icon: 'user',       color: '#6366f1', bg: '#eef2ff' },
  upcoming_appointments: { icon: 'calendar', color: '#3b82f6', bg: '#eff6ff', route: '/appointment-manager' },
};

@Component({
  selector: 'app-dashboard',
  imports: [Icon, DatePipe, RouterLink],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard implements OnInit, OnDestroy {
  protected auth = inject(AuthService);
  private http   = inject(HttpClient);

  summary    = signal<DashboardSummary | null>(null);
  error      = signal<string | null>(null);
  loading    = signal(true);
  now        = signal(new Date());
  greeting   = signal('');
  doctors    = signal<DoctorCard[]>([]);
  followupNotes = signal<FollowupNote[]>([]);

  private _timer: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    // Horloge temps réel
    this._timer = setInterval(() => this.now.set(new Date()), 1000);
    this._setGreeting();

    if (!this.auth.user()) this.auth.loadProfile().subscribe({ error: () => {} });
    this.http.get<DashboardSummary>('/api/dashboard/summary').subscribe({
      next: s  => { this.summary.set(s); this.loading.set(false); },
      error: e => { this.error.set(apiErrorMessage(e)); this.loading.set(false); },
    });

    // Charger les médecins
    this.http.get<{ items: { id: string; first_name: string; last_name: string; is_active: boolean }[] }>(
      '/api/users?role=DOCTOR&size=20'
    ).subscribe({
      next: res => {
        this.doctors.set(res.items.filter(u => u.is_active).map((u, i) => ({
          id: u.id,
          name: `Dr ${u.first_name} ${u.last_name}`,
          initials: (u.first_name[0] ?? '') + (u.last_name[0] ?? ''),
          specialty: ['Cardiologie', 'Médecine générale', 'Pédiatrie', 'Chirurgie', 'Neurologie'][i % 5],
          available: i % 3 !== 1,
        })));
      },
      error: () => {}
    });

    // Charger les notes de suivi récentes
    this.http.get<FollowupNote[]>('/api/follow-up/tasks?status=pending').subscribe({
      next: notes => this.followupNotes.set(notes.slice(0, 5)),
      error: () => {}
    });
  }

  ngOnDestroy() {
    if (this._timer) clearInterval(this._timer);
  }

  private _setGreeting() {
    const h = new Date().getHours();
    this.greeting.set(h < 12 ? 'Bonjour' : h < 18 ? 'Bon après-midi' : 'Bonsoir');
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  roleLabel(role: Role | string): string { return ROLE_LABELS[role as Role] ?? role; }
  statusLabel(s: string | undefined)     { return s ? (STATUS_LABELS[s] ?? s) : ''; }
  statusColor(s: string | undefined)     { return s ? (STATUS_COLORS[s] ?? '#64748b') : '#64748b'; }
  formatDate(v: string | undefined)      { return v ? DATE_FORMAT.format(new Date(v)) : ''; }
  formatTime(v: string | undefined)      { return v ? new Intl.DateTimeFormat('fr-FR', { timeStyle: 'short' }).format(new Date(v)) : ''; }

  isBreakdown(v: DashboardKpi['value']): v is Record<string, number> {
    return typeof v === 'object' && v !== null;
  }

  breakdown(v: Record<string, number>): { label: string; count: number; color: string }[] {
    return Object.entries(v).map(([k, count]) => ({
      label: this.roleLabel(k),
      count,
      color: STATUS_COLORS[k] ?? '#64748b',
    }));
  }

  /** KPIs simples (valeur numérique) — exclut breakdowns et appt_breakdown */
  simpleKpis(kpis: DashboardKpi[]): DashboardKpi[] {
    return kpis.filter(k =>
      !this.isBreakdown(k.value) &&
      k.key !== 'appt_breakdown' &&
      k.key !== 'total_users'
    );
  }

  breakdownKpis(kpis: DashboardKpi[]): DashboardKpi[] {
    return kpis.filter(k => this.isBreakdown(k.value));
  }

  kpiMeta(key: string) { return KPI_META[key] ?? { icon: 'activity', color: '#64748b', bg: '#f1f5f9' }; }

  timeOfDay(): string {
    const h = this.now().getHours();
    if (h < 6)  return '🌙';
    if (h < 12) return '🌅';
    if (h < 18) return '☀️';
    return '🌆';
  }

  /** Taux de complétion des tâches followup */
  followupRate(kpis: DashboardKpi[]): number {
    const pending = +(kpis.find(k => k.key === 'followup_pending')?.value ?? 0);
    const done    = +(kpis.find(k => k.key === 'followup_done')?.value ?? 0);
    const total   = pending + done;
    return total > 0 ? Math.round((done / total) * 100) : 0;
  }
}
