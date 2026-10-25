import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { INVOICE_STATUS_LABELS, Invoice, formatTnd } from '../../billing/billing.model';
import { BillingService } from '../../billing/billing.service';
import { formatDateTime } from '../birth-date';

/** "Factures" card of the patient page (SECRETARY / ADMIN): latest invoices and what is due. */
@Component({
  selector: 'app-patient-invoices',
  imports: [Icon, RouterLink],
  template: `
    <section class="card invoices" aria-labelledby="invoices-title">
      <header class="head">
        <h2 id="invoices-title"><app-icon name="file-text" [size]="18" /> Factures</h2>
        <a class="btn btn-primary btn-sm" routerLink="/billing" [queryParams]="{ patient: patientId() }">
          <app-icon name="plus" [size]="16" /> Nouvelle facture
        </a>
      </header>
      @if (loading()) {
        <p class="muted">Chargement des factures…</p>
      } @else if (error()) {
        <div class="alert" role="alert">{{ error() }}</div>
      } @else if (invoices().length === 0) {
        <div class="empty"><strong>Aucune facture</strong></div>
      } @else {
        @if (due() > 0) { <p class="due">Reste à payer : <strong>{{ formatTnd(due()) }}</strong></p> }
        <ul>
          @for (i of invoices(); track i.id) {
            <li>
              <a [routerLink]="['/billing']" [queryParams]="{ invoice: i.id }">{{ i.number }}</a>
              <span class="chip" [attr.data-status]="i.status">{{ statusLabels[i.status] }}</span>
              <span class="muted">{{ formatDateTime(i.issuedAt ?? i.createdAt) }}</span>
              <span class="amount">{{ formatTnd(i.patientShare) }}@if (i.balance > 0) { · reste {{ formatTnd(i.balance) }} }</span>
            </li>
          }
        </ul>
        @if (total() > invoices().length) { <p class="muted">Les {{ invoices().length }} plus récentes sont affichées.</p> }
      }
    </section>
  `,
  styles: `
    :host { display: block; margin-bottom: 1rem; }
    .invoices { padding: 1.25rem 1.5rem; }
    .head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: .75rem;
      h2 { display: flex; align-items: center; gap: .5rem; font-size: 1rem; font-weight: 700; } }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; padding: .55rem 0;
      border-bottom: 1px solid var(--border); font-size: .88rem; &:last-child { border-bottom: 0; }
      a { font-weight: 700; } }
    .amount { margin-left: auto; font-variant-numeric: tabular-nums; }
    .due { margin-bottom: .5rem; font-size: .9rem; color: #c2410c; }
    .empty { padding: 1.25rem; text-align: center; color: var(--muted); border: 1px dashed var(--border);
      border-radius: var(--radius-sm); strong { color: var(--ink); } }
    .chip { padding: .1rem .55rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
      &[data-status='DRAFT'] { background: #fffbeb; color: #92400e; }
      &[data-status='ISSUED'] { background: #eff6ff; color: #1d4ed8; }
      &[data-status='PARTIAL'] { background: #fff7ed; color: #c2410c; }
      &[data-status='PAID'] { background: #f0fdf4; color: #15803d; }
      &[data-status='CANCELLED'] { background: #f1f5f9; color: #475569; } }
  `,
})
export class PatientInvoicesCard {
  readonly patientId = input.required<string>();
  private billing = inject(BillingService);

  protected readonly statusLabels = INVOICE_STATUS_LABELS;
  protected readonly formatTnd = formatTnd;
  protected readonly formatDateTime = formatDateTime;
  protected loading = signal(true);
  protected error = signal<string | null>(null);
  protected invoices = signal<Invoice[]>([]);
  protected total = signal(0);
  protected due = computed(() => this.invoices().reduce((sum, i) => sum + i.balance, 0));

  constructor() {
    effect(() => {
      const patientId = this.patientId();
      untracked(() =>
        this.billing.list({ patientId, page: 1, size: 10 }).subscribe({
          next: (page) => {
            this.invoices.set(page.items);
            this.total.set(page.total);
            this.loading.set(false);
          },
          error: (err) => {
            this.error.set(apiErrorMessage(err));
            this.loading.set(false);
          },
        }),
      );
    });
  }
}
