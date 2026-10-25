import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../../shared/icon/icon';

export interface SavedReminder {
  id: string;
  patient_name: string;
  appointment_date: string;
  appointment_reason: string;
  subject: string;
  body: string;
  step: 'draft' | 'reviewed' | 'approved' | 'exported';
  created_at: string;
}

interface ReminderDraft {
  subject: string;
  body: string;
}

const STEPS = [
  { key: 'draft',    label: '1. Brouillon',  icon: 'zap'      },
  { key: 'reviewed', label: '2. Vérifié',    icon: 'eye'      },
  { key: 'approved', label: '3. Approuvé',   icon: 'shield'   },
  { key: 'exported', label: '4. Exporté',    icon: 'file'     },
] as const;

@Component({
  selector: 'app-reminders',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './reminders.html',
  styleUrl:    './reminders.scss',
})
export class Reminders {
  private http = inject(HttpClient);
  private fb   = inject(FormBuilder);

  readonly steps = STEPS;

  // ── State ─────────────────────────────────────────────────────────────────
  reminders      = signal<SavedReminder[]>([]);
  loading        = signal(true);
  apiError       = signal<string | null>(null);
  generating     = signal(false);
  genError       = signal<string | null>(null);
  draft          = signal<ReminderDraft | null>(null);
  saving         = signal(false);
  selected       = signal<SavedReminder | null>(null);
  showDetail     = signal(false);
  exportingId    = signal<string | null>(null);

  // ── Form génération ────────────────────────────────────────────────────────
  genForm = this.fb.nonNullable.group({
    patient_name:       ['', [Validators.required, Validators.maxLength(200)]],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', [Validators.required, Validators.maxLength(500)]],
  });

  constructor() { this.loadReminders(); }

  // ── Chargement ────────────────────────────────────────────────────────────
  loadReminders() {
    this.loading.set(true);
    this.http.get<SavedReminder[]>('/api/follow-up/reminders').subscribe({
      next: r  => { this.reminders.set(r); this.loading.set(false); },
      error: () => { this.loading.set(false); },
    });
  }

  // ── Génération LLM ────────────────────────────────────────────────────────
  generate() {
    if (this.genForm.invalid) { this.genForm.markAllAsTouched(); return; }
    this.generating.set(true);
    this.draft.set(null);
    this.genError.set(null);
    this.http.post<ReminderDraft>('/api/follow-up/reminders/generate', this.genForm.getRawValue()).subscribe({
      next: d  => { this.draft.set(d); this.generating.set(false); },
      error: () => { this.genError.set('Erreur lors de la génération Gemini.'); this.generating.set(false); },
    });
  }

  // ── Sauvegarde ────────────────────────────────────────────────────────────
  saveReminder() {
    const d = this.draft();
    if (!d) return;
    this.saving.set(true);
    const v = this.genForm.getRawValue();
    this.http.post<SavedReminder>('/api/follow-up/reminders', {
      patient_name:       v.patient_name,
      appointment_date:   v.appointment_date,
      appointment_reason: v.appointment_reason,
      subject:            d.subject,
      body:               d.body,
    }).subscribe({
      next: r => {
        this.reminders.update(list => [r, ...list]);
        this.draft.set(null);
        this.genForm.reset();
        this.saving.set(false);
      },
      error: () => this.saving.set(false),
    });
  }

  // ── Avancer l'étape ───────────────────────────────────────────────────────
  advanceStep(reminder: SavedReminder) {
    const order: SavedReminder['step'][] = ['draft', 'reviewed', 'approved', 'exported'];
    const idx = order.indexOf(reminder.step);
    if (idx >= order.length - 1) return;
    const next = order[idx + 1];
    this.http.patch<SavedReminder>(`/api/follow-up/reminders/${reminder.id}`, { step: next }).subscribe({
      next: updated => {
        this.reminders.update(list => list.map(r => r.id === updated.id ? updated : r));
        if (this.selected()?.id === updated.id) this.selected.set(updated);
      },
    });
  }

  canAdvance(step: SavedReminder['step']): boolean {
    return step !== 'exported';
  }

  nextStepLabel(step: SavedReminder['step']): string {
    const map: Record<string, string> = {
      draft:    'Marquer vérifié',
      reviewed: 'Approuver',
      approved: 'Marquer exporté',
    };
    return map[step] ?? '';
  }

  // ── Suppression ───────────────────────────────────────────────────────────
  deleteReminder(id: string) {
    if (!confirm('Supprimer ce rappel ?')) return;
    this.http.delete(`/api/follow-up/reminders/${id}`).subscribe({
      next: () => {
        this.reminders.update(list => list.filter(r => r.id !== id));
        if (this.selected()?.id === id) this.showDetail.set(false);
      },
    });
  }

  // ── Détail ────────────────────────────────────────────────────────────────
  openDetail(r: SavedReminder) { this.selected.set(r); this.showDetail.set(true); }

  // ── Export ────────────────────────────────────────────────────────────────
  exportPdf(id: string) {
    this.exportingId.set(id);
    window.open(`/api/follow-up/reminders/${id}/export/pdf`, '_blank');
    setTimeout(() => { this.exportingId.set(null); this.refreshOne(id); }, 1500);
  }

  exportDocx(id: string) {
    this.exportingId.set(id);
    window.open(`/api/follow-up/reminders/${id}/export/docx`, '_blank');
    setTimeout(() => { this.exportingId.set(null); this.refreshOne(id); }, 1500);
  }

  exportEmail(id: string) {
    this.exportingId.set(id);
    window.open(`/api/follow-up/reminders/${id}/export/email`, '_blank');
    setTimeout(() => { this.exportingId.set(null); this.refreshOne(id); }, 1500);
  }

  private refreshOne(id: string) {
    this.http.get<SavedReminder>(`/api/follow-up/reminders/${id}`).subscribe({
      next: updated => {
        this.reminders.update(list => list.map(r => r.id === updated.id ? updated : r));
        if (this.selected()?.id === id) this.selected.set(updated);
      },
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  stepIndex(step: SavedReminder['step']): number {
    return ['draft','reviewed','approved','exported'].indexOf(step);
  }

  stepColor(step: SavedReminder['step']): string {
    return { draft:'#f59e0b', reviewed:'#3b82f6', approved:'#22c55e', exported:'#8b5cf6' }[step] ?? '#94a3b8';
  }

  stepLabel(step: SavedReminder['step']): string {
    return { draft:'Brouillon', reviewed:'Vérifié', approved:'Approuvé', exported:'Exporté' }[step] ?? step;
  }

  isInvalid(field: string) {
    const c = this.genForm.get(field);
    return c?.invalid && (c.touched || c.dirty);
  }

  formatDate(iso: string): string {
    try { return new Date(iso).toLocaleDateString('fr-FR', { day:'2-digit', month:'short', year:'numeric' }); }
    catch { return iso; }
  }
}
