import { Component, ElementRef, effect, inject, viewChild } from '@angular/core';
import { ConfirmService } from './confirm.service';

@Component({
  selector: 'app-confirm-host',
  template: `
    <dialog
      #dialog
      (cancel)="$event.preventDefault(); confirm.answer(false)"
      aria-labelledby="confirm-title"
    >
      @if (confirm.pending(); as pending) {
        <h2 id="confirm-title">{{ pending.title }}</h2>
        <p>{{ pending.message }}</p>
        <div class="actions">
          <button type="button" class="btn btn-outline" (click)="confirm.answer(false)">
            {{ pending.cancelLabel ?? 'Annuler' }}
          </button>
          <button
            type="button"
            class="btn"
            [class.btn-primary]="!pending.danger"
            [class.btn-danger]="pending.danger"
            (click)="confirm.answer(true)"
          >
            {{ pending.confirmLabel ?? 'Confirmer' }}
          </button>
        </div>
      }
    </dialog>
  `,
  styles: `
    dialog {
      width: min(440px, calc(100vw - 2rem));
      padding: 1.5rem;
      border: 0;
      border-radius: var(--radius);
      box-shadow: 0 20px 50px rgba(15, 31, 61, 0.25);
      color: var(--ink);
    }
    dialog::backdrop {
      background: rgba(15, 31, 61, 0.45);
    }
    h2 {
      font-size: 1.1rem;
      font-weight: 700;
    }
    p {
      margin-top: 0.5rem;
      color: var(--muted);
      font-size: 0.9rem;
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
      margin-top: 1.5rem;
    }
    .btn-danger {
      background: var(--danger);
      color: #fff;
    }
    .btn-danger:hover {
      background: #b91c1c;
    }
  `,
})
export class ConfirmHost {
  protected confirm = inject(ConfirmService);
  private dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const dialog = this.dialog().nativeElement;
      if (this.confirm.pending() && !dialog.open) dialog.showModal();
      if (!this.confirm.pending() && dialog.open) dialog.close();
    });
  }
}
