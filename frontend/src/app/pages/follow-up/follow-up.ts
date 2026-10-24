import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../shared/icon/icon';

interface Task {
  id: string;
  description: string;
  due_date: string;
  status: 'pending' | 'done' | 'cancelled';
  patient_name: string;
  appointment_date: string;
  appointment_reason: string;
}

interface ReminderDraft {
  subject: string;
  body: string;
}

@Component({
  selector: 'app-follow-up',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './follow-up.html',
  styleUrl: './follow-up.scss',
})
export class FollowUp {
  private http = inject(HttpClient);
  private fb = inject(FormBuilder);

  tasks = signal<Task[]>([]);
  loading = signal(true);
  showCreateModal = signal(false);
  showEditModal = signal(false);
  editingTask = signal<Task | null>(null);
  reminderResult = signal<ReminderDraft | null>(null);
  reminderLoading = signal(false);

  createForm = this.fb.nonNullable.group({
    description:        ['', [Validators.required, Validators.maxLength(1000)]],
    due_date:           ['', Validators.required],
    patient_name:       ['', Validators.required],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', Validators.required],
  });

  editForm = this.fb.nonNullable.group({
    description: [''],
    due_date:    [''],
    status:      ['pending'],
  });

  reminderForm = this.fb.nonNullable.group({
    patient_name:       ['', Validators.required],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', Validators.required],
  });

  constructor() { this.loadTasks(); }

  loadTasks() {
    this.loading.set(true);
    this.http.get<Task[]>('/api/follow-up/tasks').subscribe({
      next: tasks => { this.tasks.set(tasks); this.loading.set(false); },
      error: ()    => { this.loading.set(false); },
    });
  }

  openCreate() {
    this.createForm.reset();
    this.showCreateModal.set(true);
  }

  submitCreate() {
    if (this.createForm.invalid) { this.createForm.markAllAsTouched(); return; }
    this.http.post<Task>('/api/follow-up/tasks', this.createForm.getRawValue()).subscribe({
      next: task => {
        this.tasks.update(t => [task, ...t]);
        this.showCreateModal.set(false);
      },
    });
  }

  openEdit(task: Task) {
    this.editingTask.set(task);
    this.editForm.patchValue({ description: task.description, due_date: task.due_date, status: task.status });
    this.showEditModal.set(true);
  }

  submitEdit() {
    const task = this.editingTask();
    if (!task) return;
    const values = this.editForm.getRawValue();
    const payload: Record<string, string> = {};
    if (values.description) payload['description'] = values.description;
    if (values.due_date)    payload['due_date']    = values.due_date;
    if (values.status)      payload['status']      = values.status;
    this.http.put<Task>(`/api/follow-up/tasks/${task.id}`, payload).subscribe({
      next: updated => {
        this.tasks.update(t => t.map(x => x.id === updated.id ? updated : x));
        this.showEditModal.set(false);
      },
    });
  }

  deleteTask(id: string) {
    if (!confirm('Supprimer cette tâche ?')) return;
    this.http.delete(`/api/follow-up/tasks/${id}`).subscribe({
      next: () => this.tasks.update(t => t.filter(x => x.id !== id)),
    });
  }

  generateReminder() {
    if (this.reminderForm.invalid) { this.reminderForm.markAllAsTouched(); return; }
    this.reminderLoading.set(true);
    this.reminderResult.set(null);
    this.http.post<ReminderDraft>('/api/follow-up/reminders/generate', this.reminderForm.getRawValue()).subscribe({
      next: result => { this.reminderResult.set(result); this.reminderLoading.set(false); },
      error: ()    => { this.reminderLoading.set(false); },
    });
  }

  badgeClass(status: string) {
    return status === 'done' ? 'done' : status === 'cancelled' ? 'cancelled' : 'pending';
  }

  statusLabel(status: string) {
    return { pending: 'En attente', done: 'Terminé', cancelled: 'Annulé' }[status] ?? status;
  }
}
