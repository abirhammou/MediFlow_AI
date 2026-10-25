import { Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { Subject, debounceTime, distinctUntilChanged, switchMap } from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { PatientListItem } from '../../patients/patient.model';
import { PatientService } from '../../patients/patient.service';
import { Invoice, formatTnd, parseTnd, tndInput } from '../billing.model';
import { BillingService } from '../billing.service';

interface LineForm {
  label: string;
  quantity: number;
  price: string; // "45,500"
}

const EMPTY_LINE: LineForm = { label: '', quantity: 1, price: '' };

/** Create a DRAFT invoice, or edit the lines of an existing DRAFT. */
@Component({
  selector: 'app-invoice-editor',
  imports: [Icon],
  templateUrl: './invoice-editor.html',
  styleUrl: '../billing.scss',
})
export class InvoiceEditor {
  /** DRAFT to edit; null to create one. */
  readonly invoice = input<Invoice | null>(null);
  /** Preselected patient (from the patient card). */
  readonly patientId = input<string | null>(null);
  readonly saved = output<Invoice>();
  readonly cancelled = output<void>();

  private billing = inject(BillingService);
  private patients = inject(PatientService);
  protected readonly formatTnd = formatTnd;

  protected patient = signal<{ id: string; label: string } | null>(null);
  protected search = signal('');
  protected matches = signal<PatientListItem[]>([]);
  private searches = new Subject<string>();

  protected lines = signal<LineForm[]>([{ ...EMPTY_LINE }]);
  protected insurance = signal('');
  protected note = signal('');
  protected saving = signal(false);
  protected error = signal<string | null>(null);

  protected amounts = computed(() => this.lines().map((l) => (parseTnd(l.price) ?? 0) * (l.quantity || 0)));
  protected total = computed(() => this.amounts().reduce((sum, a) => sum + a, 0));
  protected insuranceShare = computed(() => parseTnd(this.insurance() || '0') ?? -1);
  protected patientShare = computed(() => this.total() - Math.max(this.insuranceShare(), 0));
  protected invalid = computed(() => {
    if (!this.patient()) return 'Choisissez un patient.';
    if (this.lines().some((l) => !l.label.trim() || parseTnd(l.price) === null || !(l.quantity >= 1)))
      return 'Chaque ligne doit avoir un libellé, une quantité et un prix (ex. 45,500).';
    if (this.insuranceShare() < 0) return 'Part assurance invalide (ex. 31,500).';
    if (this.insuranceShare() > this.total()) return 'La part assurance dépasse le total.';
    return null;
  });

  constructor() {
    this.searches
      .pipe(
        debounceTime(250),
        distinctUntilChanged(),
        switchMap((q) => this.patients.list({ q, size: 8, sort: 'lastName' })),
      )
      .subscribe({ next: (page) => this.matches.set(page.items), error: () => this.matches.set([]) });

    effect(() => {
      const invoice = this.invoice();
      const patientId = this.patientId();
      untracked(() => {
        if (invoice) {
          this.patient.set({ id: invoice.patientId, label: `${invoice.patientName ?? ''} · ${invoice.recordNumber ?? ''}` });
          this.lines.set(invoice.lines.map((l) => ({ label: l.label, quantity: l.quantity, price: tndInput(l.unitPrice) })));
          this.insurance.set(invoice.insuranceShare ? tndInput(invoice.insuranceShare) : '');
          this.note.set(invoice.note ?? '');
        } else if (patientId) {
          this.patients.get(patientId).subscribe((p) =>
            this.patient.set({ id: p.id, label: `${p.firstName} ${p.lastName} · ${p.recordNumber}` }),
          );
        }
      });
    });
  }

  protected onSearch(value: string): void {
    this.search.set(value);
    if (value.trim().length >= 2) this.searches.next(value.trim());
    else this.matches.set([]);
  }

  protected choose(p: PatientListItem): void {
    this.patient.set({ id: p.id, label: `${p.firstName} ${p.lastName} · ${p.recordNumber}` });
    this.matches.set([]);
    this.search.set('');
  }

  protected setLine(index: number, change: Partial<LineForm>): void {
    this.lines.update((lines) => lines.map((line, i) => (i === index ? { ...line, ...change } : line)));
  }

  protected addLine(): void {
    this.lines.update((lines) => [...lines, { ...EMPTY_LINE }]);
  }

  protected removeLine(index: number): void {
    this.lines.update((lines) => (lines.length > 1 ? lines.filter((_, i) => i !== index) : lines));
  }

  protected save(): void {
    const patient = this.patient();
    if (this.invalid() || !patient || this.saving()) return;
    const body = {
      lines: this.lines().map((l) => ({ label: l.label.trim(), quantity: l.quantity, unitPrice: parseTnd(l.price)! })),
      insuranceShare: Math.max(this.insuranceShare(), 0),
      note: this.note().trim() || null,
    };
    const existing = this.invoice();
    const request = existing
      ? this.billing.update(existing.id, body)
      : this.billing.create({ ...body, patientId: patient.id });
    this.saving.set(true);
    this.error.set(null);
    request.subscribe({
      next: (invoice) => {
        this.saving.set(false);
        this.saved.emit(invoice);
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(err));
      },
    });
  }
}
