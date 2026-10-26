import { Component, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../../shared/icon/icon';
import { AuthService } from '../../../core/auth/auth.service';

export interface SavedReminder {
  id: string;
  patient_name: string;
  appointment_date: string;
  appointment_reason: string;
  subject: string;
  body: string;
  step: string;
  created_at: string;
}

interface PriorityLevel { label: string; color: string; bg: string; icon: string; }
interface PrioritizedReminder extends SavedReminder {
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  justification: string;
  daysUntil: number;
  isOverdue: boolean;
  isToday: boolean;
}

interface CalendarDay {
  date: Date;
  dateStr: string;
  reminders: SavedReminder[];
  isToday: boolean;
  isPast: boolean;
}

const PRIORITY_META: Record<string, PriorityLevel> = {
  HIGH:   { label: 'Urgent',  color: '#dc2626', bg: '#fef2f2', icon: '🔴' },
  MEDIUM: { label: 'Modéré',  color: '#d97706', bg: '#fef9c3', icon: '🟡' },
  LOW:    { label: 'Faible',  color: '#16a34a', bg: '#dcfce7', icon: '🟢' },
};

@Component({
  selector: 'app-patient-view',
  imports: [Icon],
  templateUrl: './patient-view.html',
  styleUrl:    './patient-view.scss',
})
export class PatientView implements OnInit, OnDestroy {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  reminders          = signal<SavedReminder[]>([]);
  loading            = signal(true);
  prioritized        = signal<PrioritizedReminder[]>([]);
  priorityLoading    = signal(false);
  calendarDays       = signal<CalendarDay[]>([]);
  notifications      = signal<PrioritizedReminder[]>([]);
  showNotif          = signal(false);
  selectedDay        = signal<CalendarDay | null>(null);
  currentMonth       = signal(new Date());

  private _notifTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.loadReminders();
    // Vérifie les notifications toutes les minutes
    this._notifTimer = setInterval(() => this._checkNotifications(), 60_000);
  }

  ngOnDestroy() {
    if (this._notifTimer) clearInterval(this._notifTimer);
  }

  // ── Chargement des rappels ────────────────────────────────────────────────
  loadReminders() {
    this.loading.set(true);
    this.http.get<SavedReminder[]>('/api/follow-up/reminders').subscribe({
      next: r => {
        this.reminders.set(r);
        this.loading.set(false);
        this._buildCalendar();
        this._autoPrioritize();
        this._checkNotifications();
      },
      error: () => this.loading.set(false),
    });
  }

  // ── Priorité automatique côté client ─────────────────────────────────────
  private _autoPrioritize() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const result: PrioritizedReminder[] = this.reminders().map(r => {
      const apptDate = new Date(r.appointment_date);
      apptDate.setHours(0, 0, 0, 0);
      const diff = Math.round((apptDate.getTime() - today.getTime()) / 86_400_000);
      const isOverdue = diff < 0;
      const isToday   = diff === 0;

      let priority: 'HIGH' | 'MEDIUM' | 'LOW';
      let justification: string;

      if (isOverdue) {
        priority = 'HIGH';
        justification = `Rappel en retard de ${Math.abs(diff)} jour(s).`;
      } else if (isToday) {
        priority = 'HIGH';
        justification = 'Rendez-vous aujourd\'hui — rappel urgent.';
      } else if (diff <= 3) {
        priority = 'HIGH';
        justification = `Rendez-vous dans ${diff} jour(s) — urgence élevée.`;
      } else if (diff <= 7) {
        priority = 'MEDIUM';
        justification = `Rendez-vous dans ${diff} jour(s) — priorité modérée.`;
      } else {
        priority = 'LOW';
        justification = `Rendez-vous dans ${diff} jour(s) — priorité faible.`;
      }

      return { ...r, priority, justification, daysUntil: diff, isOverdue, isToday };
    });

    // Trier : urgents en premier, puis par date
    result.sort((a, b) => {
      const order = { HIGH: 0, MEDIUM: 1, LOW: 2 };
      if (order[a.priority] !== order[b.priority]) return order[a.priority] - order[b.priority];
      return new Date(a.appointment_date).getTime() - new Date(b.appointment_date).getTime();
    });

    this.prioritized.set(result);
  }

  // ── Calendrier ────────────────────────────────────────────────────────────
  private _buildCalendar() {
    const month = this.currentMonth();
    const year  = month.getFullYear();
    const mon   = month.getMonth();
    const today = new Date(); today.setHours(0,0,0,0);

    // Premier lundi de la grille
    const firstDay = new Date(year, mon, 1);
    const startOffset = (firstDay.getDay() + 6) % 7; // lundi=0
    const gridStart = new Date(firstDay);
    gridStart.setDate(gridStart.getDate() - startOffset);

    const days: CalendarDay[] = [];
    const reminders = this.reminders();

    for (let i = 0; i < 42; i++) {
      const d = new Date(gridStart);
      d.setDate(d.getDate() + i);
      d.setHours(0,0,0,0);
      const dateStr = d.toISOString().slice(0, 10);
      const dayReminders = reminders.filter(r => r.appointment_date === dateStr);
      days.push({
        date: d, dateStr,
        reminders: dayReminders,
        isToday: d.getTime() === today.getTime(),
        isPast:  d.getTime() < today.getTime(),
      });
    }
    this.calendarDays.set(days);
  }

  prevMonth() {
    const m = new Date(this.currentMonth());
    m.setMonth(m.getMonth() - 1);
    this.currentMonth.set(m);
    this._buildCalendar();
  }

  nextMonth() {
    const m = new Date(this.currentMonth());
    m.setMonth(m.getMonth() + 1);
    this.currentMonth.set(m);
    this._buildCalendar();
  }

  monthLabel(): string {
    return this.currentMonth().toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  }

  weekDays = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

  isCurrentMonth(d: CalendarDay): boolean {
    return d.date.getMonth() === this.currentMonth().getMonth();
  }

  // ── Notifications ─────────────────────────────────────────────────────────
  private _checkNotifications() {
    const urgent = this.prioritized().filter(r => r.priority === 'HIGH');
    this.notifications.set(urgent);
    if (urgent.length > 0) this.showNotif.set(true);
  }

  dismissNotif() { this.showNotif.set(false); }

  notifCount(): number { return this.notifications().length; }

  // ── Export d'un rappel ────────────────────────────────────────────────────
  exportPdf(id: string)  { window.open(`/api/follow-up/reminders/${id}/export/pdf`,  '_blank'); }
  exportDocx(id: string) { window.open(`/api/follow-up/reminders/${id}/export/docx`, '_blank'); }
  exportEmail(id: string){ window.open(`/api/follow-up/reminders/${id}/export/email`, '_blank'); }

  // ── Helpers ───────────────────────────────────────────────────────────────
  priorityMeta(p: string): PriorityLevel { return PRIORITY_META[p] ?? PRIORITY_META['LOW']; }

  formatDate(iso: string): string {
    try { return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return iso; }
  }

  stepLabel(s: string): string {
    return ({ draft: 'Brouillon', reviewed: 'Vérifié', approved: 'Approuvé', exported: 'Exporté' } as any)[s] ?? s;
  }

  stepColor(s: string): string {
    return ({ draft: '#f59e0b', reviewed: '#3b82f6', approved: '#22c55e', exported: '#8b5cf6' } as any)[s] ?? '#94a3b8';
  }
}
