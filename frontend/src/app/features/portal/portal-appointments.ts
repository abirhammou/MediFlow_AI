import { Component, computed, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../shared/icon/icon';
import { ToastService } from '../../shared/toast/toast.service';
import {
  APPOINTMENT_STATUS_LABELS,
  Appointment,
  Doctor,
  Slot,
  dayLabel,
  hourLabel,
  slotsByDay,
} from '../appointments/appointments.model';
import { AppointmentsService } from '../appointments/appointments.service';

/** /portal/appointments: my appointments, and a booking request from the free slots. */
@Component({
  selector: 'app-portal-appointments',
  imports: [Icon],
  template: `
    <div class="portal">
      <header class="page-head">
        <h1>Mes rendez-vous</h1>
        <p class="muted">Vos demandes sont confirmées par le secrétariat.</p>
      </header>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }

      <section class="card card-pad">
        <h2><app-icon name="plus" [size]="18" /> Demander un rendez-vous</h2>
        <div class="booking">
          <label class="field">
            <span>Médecin</span>
            <select class="input" [value]="doctorId()" (change)="pickDoctor($any($event.target).value)">
              <option value="">Choisissez un médecin…</option>
              @for (d of doctors(); track d.id) {
                <option [value]="d.id">Dr {{ d.name }}{{ d.specialty ? ' · ' + d.specialty : '' }}</option>
              }
            </select>
          </label>
          @if (doctorId()) {
            @if (loadingSlots()) {
              <p class="muted">Recherche des créneaux libres…</p>
            } @else if (days().length === 0) {
              <div class="empty"><strong>Aucun créneau libre</strong><span>dans les 14 prochains jours. Appelez le secrétariat.</span></div>
            } @else {
              <div class="days">
                @for (d of days(); track d.day) {
                  <div class="day">
                    <h3>{{ d.day }}</h3>
                    <div class="slots">
                      @for (s of d.slots; track s.startAt) {
                        <button type="button" class="slot" [class.picked]="picked()?.startAt === s.startAt"
                                [attr.aria-pressed]="picked()?.startAt === s.startAt" (click)="picked.set(s)">{{ hourLabel(s.startAt) }}</button>
                      }
                    </div>
                  </div>
                }
              </div>
            }
          }
          @if (picked(); as s) {
            <label class="field">
              <span>Motif (facultatif)</span>
              <input class="input" maxlength="255" placeholder="Consultation de suivi…" [value]="reason()" (input)="reason.set($any($event.target).value)" />
            </label>
            <div class="actions">
              <button type="button" class="btn btn-primary btn-sm" [disabled]="booking()" (click)="book(s)">
                {{ booking() ? 'Envoi…' : 'Demander le ' + dayLabel(s.startAt) + ' à ' + hourLabel(s.startAt) }}
              </button>
            </div>
          }
        </div>
      </section>

      <section class="card card-pad">
        <h2><app-icon name="calendar" [size]="18" /> À venir</h2>
        @if (upcoming().length === 0) {
          <div class="empty"><strong>Aucun rendez-vous à venir</strong></div>
        } @else {
          <ul class="list">
            @for (a of upcoming(); track a.id) {
              <li>
                <div class="main">
                  <strong>{{ dayLabel(a.startAt) }} à {{ hourLabel(a.startAt) }}</strong>
                  <span class="meta">Dr {{ a.doctorName }}{{ a.specialty ? ' · ' + a.specialty : '' }}{{ a.reason ? ' · ' + a.reason : '' }}</span>
                </div>
                <div class="actions">
                  <span class="chip" [attr.data-status]="a.status">{{ statusLabels[a.status] }}</span>
                  @if (a.status === 'PENDING' || a.status === 'CONFIRMED') {
                    <button type="button" class="btn btn-outline btn-sm" (click)="cancel(a)">Annuler</button>
                  }
                </div>
              </li>
            }
          </ul>
        }
      </section>

      @if (past().length) {
        <section class="card card-pad">
          <h2>Historique</h2>
          <ul class="list">
            @for (a of past(); track a.id) {
              <li>
                <div class="main">
                  <span>{{ dayLabel(a.startAt) }} à {{ hourLabel(a.startAt) }} · Dr {{ a.doctorName }}</span>
                  @if (a.cancelReason) { <span class="meta">Annulé : {{ a.cancelReason }}</span> }
                </div>
                <span class="chip" [attr.data-status]="a.status">{{ statusLabels[a.status] }}</span>
              </li>
            }
          </ul>
        </section>
      }
    </div>
  `,
  styleUrl: './portal.scss',
})
export class PortalAppointments {
  private api = inject(AppointmentsService);
  private confirm = inject(ConfirmService);
  private toasts = inject(ToastService);

  protected readonly statusLabels = APPOINTMENT_STATUS_LABELS;
  protected readonly dayLabel = dayLabel;
  protected readonly hourLabel = hourLabel;

  protected error = signal<string | null>(null);
  protected appointments = signal<Appointment[]>([]);
  protected upcoming = computed(() =>
    this.appointments()
      .filter((a) => new Date(a.endAt) >= new Date() && a.status !== 'CANCELLED')
      .sort((x, y) => x.startAt.localeCompare(y.startAt)),
  );
  protected past = computed(() => this.appointments().filter((a) => !this.upcoming().includes(a)));

  protected doctors = signal<Doctor[]>([]);
  protected doctorId = signal('');
  protected slots = signal<Slot[]>([]);
  protected days = computed(() => slotsByDay(this.slots()));
  protected loadingSlots = signal(false);
  protected picked = signal<Slot | null>(null);
  protected reason = signal('');
  protected booking = signal(false);

  constructor() {
    this.load();
    this.api.doctors().subscribe({ next: (d) => this.doctors.set(d), error: (err) => this.error.set(apiErrorMessage(err)) });
  }

  private load(): void {
    this.api.list({ size: 100 }).subscribe({
      next: (page) => this.appointments.set(page.items),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected pickDoctor(id: string): void {
    this.doctorId.set(id);
    this.picked.set(null);
    this.slots.set([]);
    if (!id) return;
    this.loadingSlots.set(true);
    this.api.slots(id).subscribe({
      next: (slots) => {
        this.slots.set(slots);
        this.loadingSlots.set(false);
      },
      error: (err) => {
        this.loadingSlots.set(false);
        this.error.set(apiErrorMessage(err));
      },
    });
  }

  protected book(slot: Slot): void {
    if (this.booking()) return;
    this.booking.set(true);
    this.error.set(null);
    this.api.book(this.doctorId(), slot.startAt, this.reason().trim() || null).subscribe({
      next: () => {
        this.booking.set(false);
        this.toasts.show('Demande envoyée : le secrétariat va la confirmer.');
        this.reason.set('');
        this.pickDoctor(this.doctorId());
        this.load();
      },
      error: (err) => {
        this.booking.set(false);
        this.error.set(apiErrorMessage(err));
        this.pickDoctor(this.doctorId()); // the slot may have just been taken
      },
    });
  }

  protected async cancel(appointment: Appointment): Promise<void> {
    const confirmed = await this.confirm.ask({
      title: 'Annuler ce rendez-vous ?',
      message: `Rendez-vous du ${dayLabel(appointment.startAt)} à ${hourLabel(appointment.startAt)} avec Dr ${appointment.doctorName}.`,
      confirmLabel: 'Annuler le rendez-vous',
      danger: true,
    });
    if (!confirmed) return;
    this.api.cancel(appointment.id, 'Annulé par le patient').subscribe({
      next: () => {
        this.toasts.show('Rendez-vous annulé.');
        this.load();
      },
      error: (err) => this.toasts.show(apiErrorMessage(err), 'error'),
    });
  }
}
