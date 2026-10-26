import { Component, computed, input } from '@angular/core';
import { AppointmentStatus, STATUS_LABELS, StatusCounts } from './appointments.api';

export interface DayCount {
  day: string; // YYYY-MM-DD (heure de la clinique)
  label: string; // « 25 »
  count: number;
  today: boolean;
}

export interface StatsData {
  counts: StatusCounts;
  perDay: DayCount[];
}

const COLORS: Record<AppointmentStatus, string> = {
  PENDING: '#f59e0b',
  CONFIRMED: '#22c55e',
  COMPLETED: '#3b82f6',
  CANCELLED: '#ef4444',
  NO_SHOW: '#94a3b8',
};
const ORDER: AppointmentStatus[] = ['PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW'];
const RADIUS = 40;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Chiffres clés et graphiques de l'espace admin. */
@Component({
  selector: 'app-appointment-stats',
  template: `
    @if (stats(); as s) {
      <div class="kpis">
        <div class="kpi"><small>Total</small><strong>{{ total() }}</strong></div>
        @for (k of kpis(); track k.status) {
          <div class="kpi" [style.border-left-color]="k.color">
            <small>{{ k.label }}</small><strong>{{ k.count }}</strong>
          </div>
        }
        <div class="kpi rate"><small>Taux d'annulation</small><strong>{{ cancelRate() }}</strong></div>
        <div class="kpi rate"><small>Taux d'absence</small><strong>{{ noShowRate() }}</strong></div>
      </div>

      <div class="charts">
        <section class="chart-card">
          <h3>Répartition par statut</h3>
          @if (total() === 0) {
            <p class="empty">Aucune donnée.</p>
          } @else {
            <div class="donut-row">
              <svg viewBox="0 0 100 100" class="donut" role="img" aria-label="Répartition des rendez-vous par statut">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#f1f5f9" stroke-width="14" />
                @for (seg of segments(); track seg.status) {
                  <circle cx="50" cy="50" r="40" fill="none" [attr.stroke]="seg.color" stroke-width="14"
                          [attr.stroke-dasharray]="seg.dash" [attr.stroke-dashoffset]="seg.offset"
                          transform="rotate(-90 50 50)" />
                }
                <text x="50" y="49" text-anchor="middle" class="donut-total">{{ total() }}</text>
                <text x="50" y="62" text-anchor="middle" class="donut-sub">rendez-vous</text>
              </svg>
              <ul class="legend">
                @for (seg of segments(); track seg.status) {
                  <li><i [style.background]="seg.color"></i>{{ seg.label }}<b>{{ seg.count }}</b></li>
                }
              </ul>
            </div>
          }
        </section>

        <section class="chart-card">
          <h3>Rendez-vous par jour <small>(hors annulés)</small></h3>
          <svg viewBox="0 0 300 130" class="bars" role="img" aria-label="Rendez-vous par jour">
            @for (d of bars(); track d.day) {
              <g>
                <title>{{ d.day }} : {{ d.count }}</title>
                <rect [attr.x]="d.x" [attr.y]="d.y" width="14" [attr.height]="d.h" rx="3"
                      [attr.fill]="d.today ? '#7c3aed' : '#c4b5fd'" />
                @if (d.count > 0) { <text [attr.x]="d.x + 7" [attr.y]="d.y - 3" text-anchor="middle" class="bar-val">{{ d.count }}</text> }
                <text [attr.x]="d.x + 7" y="124" text-anchor="middle" class="bar-day" [class.now]="d.today">{{ d.label }}</text>
              </g>
            }
          </svg>
          <p class="foot">14 jours autour d'aujourd'hui (en violet foncé).</p>
        </section>
      </div>
    }
  `,
  styles: [
    `:host { display: block; }
     .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
     .kpi { background: #fff; border: 1px solid #e5e7eb; border-left: 4px solid #cbd5e1; border-radius: 12px; padding: 12px 14px; }
     .kpi small { display: block; color: #64748b; font-size: 12px; }
     .kpi strong { font-size: 24px; line-height: 1.3; color: #0f172a; }
     .kpi.rate { border-left-color: #7c3aed; }
     .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
     .chart-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px; }
     .chart-card h3 { margin: 0 0 12px; font-size: 15px; color: #0f172a; }
     .chart-card h3 small { font-weight: 400; color: #94a3b8; }
     .donut-row { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
     .donut { width: 150px; height: 150px; }
     .donut-total { font-size: 18px; font-weight: 700; fill: #0f172a; }
     .donut-sub { font-size: 7px; fill: #64748b; }
     .legend { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; flex: 1; min-width: 150px; font-size: 13px; }
     .legend li { display: flex; align-items: center; gap: 8px; }
     .legend i { width: 10px; height: 10px; border-radius: 50%; }
     .legend b { margin-left: auto; }
     .bars { width: 100%; height: auto; }
     .bar-val { font-size: 9px; fill: #475569; }
     .bar-day { font-size: 8px; fill: #94a3b8; }
     .bar-day.now { fill: #7c3aed; font-weight: 700; }
     .foot { margin: 6px 0 0; font-size: 12px; color: #94a3b8; }
     .empty { color: #64748b; font-size: 13px; }`,
  ],
})
export class AppointmentStats {
  readonly stats = input<StatsData | null>(null);

  readonly total = computed(() => {
    const s = this.stats();
    return s ? ORDER.reduce((sum, k) => sum + s.counts[k], 0) : 0;
  });

  readonly kpis = computed(() => {
    const s = this.stats();
    return s ? ORDER.map(k => ({ status: k, label: STATUS_LABELS[k], count: s.counts[k], color: COLORS[k] })) : [];
  });

  readonly cancelRate = computed(() => this.percent(this.stats()?.counts.CANCELLED ?? 0, this.total()));
  readonly noShowRate = computed(() => {
    const c = this.stats()?.counts;
    return c ? this.percent(c.NO_SHOW, c.COMPLETED + c.NO_SHOW) : '—';
  });

  readonly segments = computed(() => {
    const s = this.stats();
    const total = this.total();
    if (!s || total === 0) return [];
    let used = 0;
    return ORDER.filter(k => s.counts[k] > 0).map(k => {
      const length = (s.counts[k] / total) * CIRCUMFERENCE;
      const seg = {
        status: k,
        label: STATUS_LABELS[k],
        count: s.counts[k],
        color: COLORS[k],
        dash: `${length} ${CIRCUMFERENCE - length}`,
        offset: -used,
      };
      used += length;
      return seg;
    });
  });

  readonly bars = computed(() => {
    const days = this.stats()?.perDay ?? [];
    const max = Math.max(1, ...days.map(d => d.count));
    const height = 90;
    return days.map((d, i) => {
      const h = Math.round((d.count / max) * height);
      return { ...d, x: 8 + i * 20.5, y: 108 - h, h };
    });
  });

  private percent(part: number, whole: number): string {
    return whole > 0 ? `${Math.round((part / whole) * 100)} %` : '—';
  }
}