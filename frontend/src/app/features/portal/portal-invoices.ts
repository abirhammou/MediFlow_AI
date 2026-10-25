import { Component, computed, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import { INVOICE_STATUS_LABELS, Invoice, formatTnd } from '../billing/billing.model';
import { BillingService } from '../billing/billing.service';
import { InvoiceDetail } from '../billing/invoice-detail/invoice-detail';
import { formatDateTime } from '../patients/birth-date';

/** /portal/invoices: my invoices and receipts (read-only, PDFs). */
@Component({
  selector: 'app-portal-invoices',
  imports: [Icon, InvoiceDetail],
  template: `
    <div class="portal">
      <header class="page-head">
        <h1>Mes factures</h1>
        <p class="muted">Factures et reçus de la clinique. Le règlement se fait au secrétariat.</p>
      </header>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }
      @if (due() > 0) { <p><strong>Reste à payer : {{ formatTnd(due()) }}</strong></p> }
      <div class="split" [class.has-side]="selected()">
        <section class="card card-pad">
          <h2><app-icon name="file-text" [size]="18" /> Factures</h2>
          @if (invoices().length === 0) {
            <div class="empty"><strong>Aucune facture</strong></div>
          } @else {
            <ul class="list clickable">
              @for (i of invoices(); track i.id) {
                <li [class.selected]="selected()?.id === i.id" tabindex="0" (click)="open(i)" (keydown.enter)="open(i)">
                  <div class="main">
                    <strong>{{ i.number }}</strong>
                    <span class="meta">{{ formatDateTime(i.issuedAt ?? i.createdAt) }}</span>
                  </div>
                  <span class="amount">{{ formatTnd(i.patientShare) }}</span>
                  <span class="chip" [attr.data-status]="i.status">{{ statusLabels[i.status] }}</span>
                </li>
              }
            </ul>
          }
        </section>
        @if (selected(); as s) {
          <section class="card card-pad"><app-invoice-detail [invoice]="s" [canManage]="false" /></section>
        }
      </div>
    </div>
  `,
  styleUrl: './portal.scss',
})
export class PortalInvoices {
  private billing = inject(BillingService);
  protected readonly statusLabels = INVOICE_STATUS_LABELS;
  protected readonly formatTnd = formatTnd;
  protected readonly formatDateTime = formatDateTime;
  protected invoices = signal<Invoice[]>([]);
  protected selected = signal<Invoice | null>(null);
  protected error = signal<string | null>(null);
  protected due = computed(() => this.invoices().reduce((sum, i) => sum + i.balance, 0));

  constructor() {
    // The API only returns the patient's own issued invoices, whatever the parameters.
    this.billing.list({ page: 1, size: 100 }).subscribe({
      next: (page) => this.invoices.set(page.items),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected open(invoice: Invoice): void {
    this.billing.get(invoice.id).subscribe({
      next: (full) => this.selected.set(full),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }
}
