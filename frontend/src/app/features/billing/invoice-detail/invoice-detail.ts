import { Component, ElementRef, computed, effect, inject, input, output, signal, untracked, viewChild } from '@angular/core';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { formatDateTime } from '../../patients/birth-date';
import { saveBlob } from '../../patients/patient-file.model';
import {
  INVOICE_STATUS_LABELS,
  Invoice,
  PAYMENT_METHOD_LABELS,
  Payment,
  PaymentMethod,
  formatTnd,
  parseTnd,
  tndInput,
} from '../billing.model';
import { BillingService } from '../billing.service';

/**
 * One invoice: lines, totals, payments and receipts. With `canManage` (SECRETARY / ADMIN):
 * edit the draft, issue, record a payment, refund, cancel. Read-only otherwise (patient).
 */
@Component({
  selector: 'app-invoice-detail',
  imports: [Icon],
  templateUrl: './invoice-detail.html',
  styleUrl: '../billing.scss',
})
export class InvoiceDetail {
  readonly invoice = input.required<Invoice>();
  readonly canManage = input(false);
  readonly changed = output<Invoice>();
  readonly edit = output<Invoice>();

  private billing = inject(BillingService);
  private toasts = inject(ToastService);

  protected readonly statusLabels = INVOICE_STATUS_LABELS;
  protected readonly methodLabels = PAYMENT_METHOD_LABELS;
  protected readonly methods = Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[];
  protected readonly formatTnd = formatTnd;
  protected readonly formatDateTime = formatDateTime;

  protected busy = signal(false);
  protected error = signal<string | null>(null);
  protected payable = computed(() => ['ISSUED', 'PARTIAL'].includes(this.invoice().status));
  protected cancellable = computed(
    () => ['DRAFT', 'ISSUED'].includes(this.invoice().status) && this.invoice().paidAmount === 0,
  );

  // Payment form
  protected amount = signal('');
  protected method = signal<PaymentMethod>('CASH');
  protected payNote = signal('');
  protected amountValue = computed(() => parseTnd(this.amount()));

  // Dialogs
  protected refunding = signal<Payment | null>(null);
  protected refundAmount = signal('');
  protected reason = signal('');
  private refundDialog = viewChild<ElementRef<HTMLDialogElement>>('refundDialog');
  private cancelDialog = viewChild<ElementRef<HTMLDialogElement>>('cancelDialog');

  constructor() {
    effect(() => {
      const balance = this.invoice().balance;
      untracked(() => this.amount.set(balance > 0 ? tndInput(balance) : ''));
    });
  }

  private act(request: ReturnType<BillingService['issue']>, success: string, after?: () => void): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (invoice) => {
        this.busy.set(false);
        after?.();
        this.toasts.show(success);
        this.changed.emit(invoice);
      },
      error: (err) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(err));
      },
    });
  }

  protected issue(): void {
    this.act(this.billing.issue(this.invoice().id), 'Facture émise.');
  }

  protected pay(): void {
    const amount = this.amountValue();
    if (!amount) return;
    this.act(
      this.billing.pay(this.invoice().id, amount, this.method(), this.payNote().trim() || null),
      `Paiement de ${formatTnd(amount)} enregistré.`,
      () => this.payNote.set(''),
    );
  }

  protected openRefund(payment: Payment): void {
    this.refunding.set(payment);
    this.refundAmount.set(tndInput(payment.refundable));
    this.reason.set('');
    this.refundDialog()?.nativeElement.showModal();
  }

  protected refund(): void {
    const payment = this.refunding();
    const amount = parseTnd(this.refundAmount());
    if (!payment || !amount) return;
    this.refundDialog()?.nativeElement.close();
    this.act(
      this.billing.refund(payment.id, amount, this.reason().trim() || null),
      `Remboursement de ${formatTnd(amount)} enregistré.`,
    );
  }

  protected openCancel(): void {
    this.reason.set('');
    this.cancelDialog()?.nativeElement.showModal();
  }

  protected cancel(): void {
    const reason = this.reason().trim();
    if (!reason) return;
    this.cancelDialog()?.nativeElement.close();
    this.act(this.billing.cancel(this.invoice().id, reason), 'Facture annulée.');
  }

  protected closeDialogs(): void {
    this.refundDialog()?.nativeElement.close();
    this.cancelDialog()?.nativeElement.close();
  }

  protected invoicePdf(): void {
    const invoice = this.invoice();
    this.billing.invoicePdf(invoice.id).subscribe({
      next: (blob) => saveBlob(blob, `facture-${invoice.number}.pdf`),
      error: (err) => this.toasts.show(apiErrorMessage(err), 'error'),
    });
  }

  protected receiptPdf(payment: Payment): void {
    this.billing.receiptPdf(payment.id).subscribe({
      next: (blob) => saveBlob(blob, `recu-${payment.receiptNumber}.pdf`),
      error: (err) => this.toasts.show(apiErrorMessage(err), 'error'),
    });
  }
}
