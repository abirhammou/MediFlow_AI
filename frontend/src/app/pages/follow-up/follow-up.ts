import { Component, inject, signal, computed } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../shared/icon/icon';

export interface Task {
  id: string;
  description: string;
  due_date: string;
  status: 'pending' | 'done' | 'cancelled';
  patient_name: string;
  appointment_date: string;
  appointment_reason: string;
}

export interface TaskStats {
  total: number;
  pending: number;
  done: number;
  cancelled: number;
}

export interface ReminderDraft {
  subject: string;
  body: string;
}

type StatusFilter = 'all' | 'pending' | 'done' | 'cancelled';

@Component({
  selector: 'app-follow-up',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './follow-up.html',
  styleUrl: './follow-up.scss',
})
export class FollowUp {
  private http = inject(HttpClient);
  private fb   = inject(FormBuilder);

  // ── State ────────────────────────────────────────────────────────────────
  tasks         = signal<Task[]>([]);
  stats         = signal<TaskStats>({ total: 0, pending: 0, done: 0, cancelled: 0 });
  loading       = signal(true);
  apiError      = signal<string | null>(null);
  statusFilter  = signal<StatusFilter>('all');

  showCreateModal  = signal(false);
  showEditModal    = signal(false);
  showDetailModal  = signal(false);
  detailTask       = signal<Task | null>(null);
  editingTask      = signal<Task | null>(null);
  submitting       = signal(false);

  reminderResult  = signal<ReminderDraft | null>(null);
  reminderLoading = signal(false);
  reminderError   = signal<string | null>(null);

  // ── Forms ─────────────────────────────────────────────────────────────────
  createForm = this.fb.nonNullable.group({
    description:        ['', [Validators.required, Validators.maxLength(1000)]],
    due_date:           ['', Validators.required],
    patient_name:       ['', [Validators.required, Validators.maxLength(200)]],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', [Validators.required, Validators.maxLength(500)]],
  });

  editForm = this.fb.nonNullable.group({
    description: ['', Validators.maxLength(1000)],
    due_date:    [''],
    status:      ['pending' as string],
  });

  reminderForm = this.fb.nonNullable.group({
    patient_name:       ['', Validators.required],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', Validators.required],
  });

  constructor() {
    this.loadAll();
  }

  // ── Data loading ──────────────────────────────────────────────────────────
  loadAll() {
    this.loading.set(true);
    this.apiError.set(null);

    const filter = this.statusFilter();
    const url = filter === 'all'
      ? '/api/follow-up/tasks'
      : `/api/follow-up/tasks?status=${filter}`;

    this.http.get<Task[]>(url).subscribe({
      next: tasks => { this.tasks.set(tasks); this.loading.set(false); },
      error: err  => {
        this.apiError.set(err.status === 0 ? 'Serveur injoignable.' : 'Erreur lors du chargement.');
        this.loading.set(false);
      },
    });

    this.http.get<TaskStats>('/api/follow-up/tasks/stats').subscribe({
      next: s => this.stats.set(s),
    });
  }

  setFilter(f: StatusFilter) {
    this.statusFilter.set(f);
    this.loadAll();
  }

  // ── Create ────────────────────────────────────────────────────────────────
  openCreate() {
    this.createForm.reset();
    this.showCreateModal.set(true);
  }

  submitCreate() {
    if (this.createForm.invalid) { this.createForm.markAllAsTouched(); return; }
    this.submitting.set(true);
    this.http.post<Task>('/api/follow-up/tasks', this.createForm.getRawValue()).subscribe({
      next: task => {
        this.tasks.update(t => [task, ...t]);
        this.stats.update(s => ({ ...s, total: s.total + 1, pending: s.pending + 1 }));
        this.showCreateModal.set(false);
        this.submitting.set(false);
      },
      error: () => this.submitting.set(false),
    });
  }

  // ── Detail ────────────────────────────────────────────────────────────────
  openDetail(task: Task) {
    this.detailTask.set(task);
    this.showDetailModal.set(true);
  }

  // ── Edit ──────────────────────────────────────────────────────────────────
  openEdit(task: Task) {
    this.editingTask.set(task);
    this.editForm.setValue({
      description: task.description,
      due_date:    task.due_date,
      status:      task.status,
    });
    this.showEditModal.set(true);
  }

  submitEdit() {
    const task = this.editingTask();
    if (!task) return;
    this.submitting.set(true);
    const v = this.editForm.getRawValue();
    const payload: Partial<{ description: string; due_date: string; status: string }> = {};
    if (v.description.trim()) payload.description = v.description.trim();
    if (v.due_date)            payload.due_date    = v.due_date;
    if (v.status)              payload.status      = v.status;

    this.http.patch<Task>(`/api/follow-up/tasks/${task.id}`, payload).subscribe({
      next: updated => {
        this.tasks.update(t => t.map(x => x.id === updated.id ? updated : x));
        if (this.detailTask()?.id === updated.id) this.detailTask.set(updated);
        this.showEditModal.set(false);
        this.submitting.set(false);
        this.loadStats();
      },
      error: () => this.submitting.set(false),
    });
  }

  // ── Delete ────────────────────────────────────────────────────────────────
  deleteTask(id: string) {
    if (!confirm('Supprimer définitivement cette tâche ?')) return;
    this.http.delete(`/api/follow-up/tasks/${id}`).subscribe({
      next: () => {
        const removed = this.tasks().find(t => t.id === id);
        this.tasks.update(t => t.filter(x => x.id !== id));
        if (removed) {
          this.stats.update(s => ({
            ...s,
            total: s.total - 1,
            [removed.status]: Math.max(0, (s as any)[removed.status] - 1),
          }));
        }
        if (this.detailTask()?.id === id) this.showDetailModal.set(false);
      },
    });
  }

  // ── LLM Reminder ──────────────────────────────────────────────────────────
  prefillReminder(task: Task) {
    this.reminderForm.setValue({
      patient_name:       task.patient_name,
      appointment_date:   task.appointment_date,
      appointment_reason: task.appointment_reason,
    });
    this.reminderResult.set(null);
    // scroll to reminder section
    setTimeout(() => document.getElementById('reminder-section')?.scrollIntoView({ behavior: 'smooth' }), 100);
  }

  generateReminder() {
    if (this.reminderForm.invalid) { this.reminderForm.markAllAsTouched(); return; }
    this.reminderLoading.set(true);
    this.reminderResult.set(null);
    this.reminderError.set(null);
    this.http.post<ReminderDraft>('/api/follow-up/reminders/generate', this.reminderForm.getRawValue()).subscribe({
      next: r  => { this.reminderResult.set(r); this.reminderLoading.set(false); },
      error: () => { this.reminderError.set('Erreur lors de la génération.'); this.reminderLoading.set(false); },
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  private loadStats() {
    this.http.get<TaskStats>('/api/follow-up/tasks/stats').subscribe({
      next: s => this.stats.set(s),
    });
  }

  readonly today = new Date().toISOString().slice(0, 10);

  badgeClass(status: string)  { return status; }
  statusLabel(s: string)      { return ({ pending: 'En attente', done: 'Terminé', cancelled: 'Annulé' } as any)[s] ?? s; }
  isInvalid(form: any, field: string) {
    const c = form.get(field);
    return c?.invalid && (c.touched || c.dirty);
  }
}
