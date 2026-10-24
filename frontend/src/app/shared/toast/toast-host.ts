import { Component, inject } from '@angular/core';
import { Icon } from '../icon/icon';
import { ToastService } from './toast.service';

@Component({
  selector: 'app-toast-host',
  imports: [Icon],
  template: `
    <div class="toasts" role="status" aria-live="polite">
      @for (toast of toasts.toasts(); track toast.id) {
        <div class="toast" [class.error]="toast.kind === 'error'">
          <span>{{ toast.text }}</span>
          <button type="button" (click)="toasts.dismiss(toast.id)" aria-label="Fermer">
            <app-icon name="x" [size]="16" />
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .toasts {
      position: fixed;
      left: 50%;
      bottom: 1.5rem;
      transform: translateX(-50%);
      z-index: 1000;
      display: grid;
      gap: 0.5rem;
      width: min(440px, calc(100vw - 2rem));
    }
    .toast {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.75rem 1rem;
      border-radius: var(--radius-sm);
      background: var(--ink);
      color: #fff;
      font-size: 0.875rem;
      box-shadow: var(--shadow-md);
    }
    .toast.error {
      background: #991b1b;
    }
    button {
      display: grid;
      place-items: center;
      padding: 0.25rem;
      border: 0;
      border-radius: 6px;
      background: none;
      color: inherit;
      cursor: pointer;
      opacity: 0.8;
    }
    button:hover {
      opacity: 1;
      background: rgba(255, 255, 255, 0.12);
    }
  `,
})
export class ToastHost {
  protected toasts = inject(ToastService);
}
