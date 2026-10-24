import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  text: string;
  kind: 'success' | 'error';
}

const DURATION_MS = 4000;

/** Short messages shown at the bottom of the screen (rendered by <app-toast-host>). */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  readonly toasts = signal<Toast[]>([]);

  show(text: string, kind: Toast['kind'] = 'success'): void {
    const toast = { id: this.nextId++, text, kind };
    this.toasts.update(toasts => [...toasts, toast]);
    setTimeout(() => this.dismiss(toast.id), DURATION_MS);
  }

  dismiss(id: number): void {
    this.toasts.update(toasts => toasts.filter(toast => toast.id !== id));
  }
}
