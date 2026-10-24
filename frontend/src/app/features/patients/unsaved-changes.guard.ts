import { inject } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';

export interface HasUnsavedChanges {
  hasUnsavedChanges(): boolean;
}

/** Asks before leaving a form with unsaved changes (reloads are handled by `beforeunload`). */
export const unsavedChangesGuard: CanDeactivateFn<HasUnsavedChanges> = component =>
  !component.hasUnsavedChanges() ||
  inject(ConfirmService).ask({
    title: 'Quitter sans enregistrer ?',
    message: 'Les modifications non enregistrées seront perdues.',
    confirmLabel: 'Quitter la page',
    cancelLabel: 'Rester',
    danger: true,
  });
