import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import { ToastService } from '../../shared/toast/toast.service';
import { Appointment, dayLabel, hourLabel } from './appointments.model';
import { AppointmentsService } from './appointments.service';

/** Appointment requests made from the patient portal, for the secretary to confirm or decline. */
@Component({
  selector: 'app-pending-appointments',
  imports: [Icon, RouterLink],
  template: `
    <section class="card pending" aria-labelledby="pending-title">
      <h2 id="pending-title"><app-icon name="calendar" [size]="18" /> Demandes de rendez-vous à confirmer</h2>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }
      @if (items() === null) {
        <p class="muted">Chargement…</p>
      } @else if (items()!.length === 0) {
        <p class="muted">Aucune demande en attente.</p>
      } @else {
        <ul>
          @for (a of items(); track a.id) {
            <li>
              <div class="main">
                <strong>{{ dayLabel(a.startAt) }} à {{ hourLabel(a.startAt) }}</strong> · Dr {{ a.doctorName }}
                <span class="muted">· <a [routerLink]="['/patients', a.patientId]">{{ a.patientName }}</a> {{ a.recordNumber }}{{ a.reason ? ' · ' + a.reason : '' }}</span>
              </div>
              <div class="actions">
                <button type="button" class="btn btn-primary btn-sm" [disabled]="busy() === a.id" (click)="confirm(a)">Confirmer</button>
                <button type="button" class="btn btn-outline btn-sm" [disabled]="busy() === a.id" (click)="decline(a)">Refuser</button>
              </div>
            </li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    :host { display: block; margin-bottom: 1rem; }
    .pending { padding: 1.25rem 1.5rem; }
    h2 { display: flex; align-items: center; gap: .5rem; font-size: 1rem; font-weight: 700; margin-bottom: .75rem; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap;
      padding: .65rem 0; border-bottom: 1px solid var(--border); font-size: .88rem; &:last-child { border-bottom: 0; } }
    .actions { display: flex; gap: .5rem; }
  `,
})
export class PendingAppointments {
  private api = inject(AppointmentsService);
  private toasts = inject(ToastService);
  protected readonly dayLabel = dayLabel;
  protected readonly hourLabel = hourLabel;
  protected items = signal<Appointment[] | null>(null);
  protected busy = signal<string | null>(null);
  protected error = signal<string | null>(null);

  constructor() {
    this.load();
  }

  private load(): void {
    this.api.list({ status: 'PENDING', upcoming: true, size: 100 }).subscribe({
      next: (page) => this.items.set(page.items),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  private act(appointment: Appointment, request: ReturnType<AppointmentsService['confirm']>, message: string): void {
    this.busy.set(appointment.id);
    request.subscribe({
      next: () => {
        this.busy.set(null);
        this.toasts.show(message);
        this.load();
      },
      error: (err) => {
        this.busy.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
        this.load();
      },
    });
  }

  protected confirm(appointment: Appointment): void {
    this.act(appointment, this.api.confirm(appointment.id), 'Rendez-vous confirmé.');
  }

  protected decline(appointment: Appointment): void {
    this.act(appointment, this.api.cancel(appointment.id, 'Créneau refusé par le secrétariat'), 'Demande refusée.');
  }
}
