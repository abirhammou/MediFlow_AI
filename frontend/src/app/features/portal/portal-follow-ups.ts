import { Component, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import { formatDateTime } from '../patients/birth-date';
import { PortalFollowUp, PortalService } from './portal.service';

const STATUS_LABELS: Record<PortalFollowUp['status'], string> = {
  TODO: 'Prévu',
  IN_PROGRESS: 'En cours',
  DONE: 'Fait',
};

/** /portal/follow-ups: the follow-up actions planned for me. */
@Component({
  selector: 'app-portal-follow-ups',
  imports: [Icon],
  template: `
    <div class="portal">
      <header class="page-head">
        <h1>Mon suivi</h1>
        <p class="muted">Les actions de suivi prévues par la clinique pour vous.</p>
      </header>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }
      <section class="card card-pad">
        <h2><app-icon name="bell" [size]="18" /> Suivi</h2>
        @if (items() === null) {
          <p class="muted">Chargement…</p>
        } @else if (items()!.length === 0) {
          <div class="empty"><strong>Aucune action de suivi</strong></div>
        } @else {
          <ul class="list">
            @for (t of items(); track t.id) {
              <li>
                <div class="main">
                  <strong>{{ t.description }}</strong>
                  @if (t.dueDate) { <span class="meta">Échéance : {{ formatDateTime(t.dueDate) }}</span> }
                </div>
                <span class="chip" [attr.data-status]="t.status">{{ statusLabels[t.status] }}</span>
              </li>
            }
          </ul>
        }
      </section>
    </div>
  `,
  styleUrl: './portal.scss',
})
export class PortalFollowUps {
  protected readonly statusLabels = STATUS_LABELS;
  protected readonly formatDateTime = formatDateTime;
  protected items = signal<PortalFollowUp[] | null>(null);
  protected error = signal<string | null>(null);

  constructor() {
    inject(PortalService)
      .followUps()
      .subscribe({
        next: (items) => this.items.set(items),
        error: (err) => {
          this.items.set([]);
          this.error.set(apiErrorMessage(err));
        },
      });
  }
}
