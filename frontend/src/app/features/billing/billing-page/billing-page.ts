import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { formatDateTime } from '../../patients/birth-date';
import {
  INVOICE_STATUS_LABELS,
  Invoice,
  InvoiceStatus,
  PAYMENT_METHOD_LABELS,
  PaymentMethod,
  RevenueReport,
  UnpaidReport,
  formatTnd,
} from '../billing.model';
import { BillingService } from '../billing.service';
import { InvoiceDetail } from '../invoice-detail/invoice-detail';
import { InvoiceEditor } from '../invoice-editor/invoice-editor';

type Tab = 'invoices' | 'unpaid' | 'revenue';
const PAGE_SIZE = 15;

function isoDay(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/**
 * /billing (SECRETARY, ADMIN): invoices, payments, unpaid invoices and revenue.
 * ?invoice=<id> opens an invoice, ?patient=<id> starts a new one for that patient.
 */
@Component({
  selector: 'app-billing-page',
  imports: [Icon, RouterLink, InvoiceDetail, InvoiceEditor],
  templateUrl: './billing-page.html',
  styleUrl: '../billing.scss',
})
export class BillingPage {
  private billing = inject(BillingService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  protected readonly statusLabels = INVOICE_STATUS_LABELS;
  protected readonly statuses = Object.keys(INVOICE_STATUS_LABELS) as InvoiceStatus[];
  protected readonly methodLabels = PAYMENT_METHOD_LABELS;
  protected readonly methods = Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[];
  protected readonly formatTnd = formatTnd;
  protected readonly formatDateTime = formatDateTime;

  protected tab = signal<Tab>('invoices');
  protected error = signal<string | null>(null);

  // Invoices
  protected status = signal<InvoiceStatus | ''>('');
  protected number = signal('');
  protected page = signal(1);
  protected total = signal(0);
  protected invoices = signal<Invoice[]>([]);
  protected loading = signal(false);
  protected pages = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  protected selected = signal<Invoice | null>(null);
  protected editing = signal<Invoice | null | 'new'>(null);
  protected newFor = signal<string | null>(null);

  // Reports
  protected unpaid = signal<UnpaidReport | null>(null);
  protected revenue = signal<RevenueReport | null>(null);
  protected from = signal(isoDay(new Date(new Date().getFullYear(), new Date().getMonth(), 1)));
  protected to = signal(isoDay(new Date()));
  protected groupBy = signal<'day' | 'month'>('day');
  protected maxNet = computed(() => Math.max(1, ...(this.revenue()?.rows ?? []).map((r) => r.net)));

  constructor() {
    const params = this.route.snapshot.queryParamMap;
    const invoiceId = params.get('invoice');
    const patientId = params.get('patient');
    if (patientId) {
      this.newFor.set(patientId);
      this.editing.set('new');
    }
    if (invoiceId) this.open(invoiceId);
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.billing
      .list({ status: this.status(), number: this.number(), page: this.page(), size: PAGE_SIZE })
      .subscribe({
        next: (page) => {
          this.invoices.set(page.items);
          this.total.set(page.total);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(apiErrorMessage(err));
          this.loading.set(false);
        },
      });
  }

  protected filter(): void {
    this.page.set(1);
    this.load();
  }

  protected goTo(page: number): void {
    this.page.set(page);
    this.load();
  }

  protected setTab(tab: Tab): void {
    this.tab.set(tab);
    if (tab === 'unpaid') this.loadUnpaid();
    if (tab === 'revenue') this.loadRevenue();
  }

  protected open(id: string): void {
    this.billing.get(id).subscribe({
      next: (invoice) => this.selected.set(invoice),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected changed(invoice: Invoice): void {
    this.selected.set(invoice);
    this.invoices.update((list) => list.map((i) => (i.id === invoice.id ? { ...invoice, payments: [] } : i)));
    if (this.tab() === 'unpaid') this.loadUnpaid();
  }

  protected saved(invoice: Invoice): void {
    this.editing.set(null);
    this.newFor.set(null);
    this.selected.set(invoice);
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
    this.load();
  }

  protected loadUnpaid(): void {
    this.billing.unpaid().subscribe({
      next: (report) => this.unpaid.set(report),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected loadRevenue(): void {
    this.billing.revenue(this.from(), this.to(), this.groupBy()).subscribe({
      next: (report) => this.revenue.set(report),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }
}
