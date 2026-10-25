import { Component, inject, signal, computed } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../shared/icon/icon';
import { AuthService, Role } from '../../core/auth/auth.service';
import { Reminders } from './reminders/reminders';
import { AiFeatures } from './ai-features/ai-features';

interface PatientOption {
  id: string;
  firstName: string;
  lastName: string;
  recordNumber: string;
}

export interface Task {
  id: string;
  description: string;
  due_date: string;
  status: 'pending' | 'done' | 'cancelled';
  patient_id: string;
  patient_name: string;
  patient_record_number: string;
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

// ── Permissions par rôle ────────────────────────────────────────────────────
interface RolePermissions {
  canCreate:         boolean;  // Créer une tâche
  canEdit:           boolean;  // Modifier description / échéance / statut
  canDelete:         boolean;  // Supprimer une tâche
  canGenerateReminder: boolean;// Accès au générateur LLM
  canSeeAllTasks:    boolean;  // Voir toutes les tâches (sinon filtre patient)
  label:             string;   // Nom du rôle affiché
  description:       string;   // Sous-titre de la page selon le rôle
}

const PERMISSIONS: Record<Role, RolePermissions> = {
  ADMIN: {
    canCreate: true, canEdit: true, canDelete: true,
    canGenerateReminder: true, canSeeAllTasks: true,
    label: 'Administrateur',
    description: 'Gestion complète des tâches de suivi de la clinique.',
  },
  ADMIN_STAFF: {
    canCreate: true, canEdit: true, canDelete: true,
    canGenerateReminder: true, canSeeAllTasks: true,
    label: 'Gestion administrative',
    description: 'Gestion complète des tâches de suivi administratif.',
  },
  SECRETARY: {
    canCreate: true, canEdit: true, canDelete: false,
    canGenerateReminder: true, canSeeAllTasks: true,
    label: 'Secrétariat',
    description: 'Création et suivi des tâches. Génération de rappels pour les rendez-vous confirmés.',
  },
  DOCTOR: {
    canCreate: false, canEdit: true, canDelete: false,
    canGenerateReminder: true, canSeeAllTasks: true,
    label: 'Médecin',
    description: 'Suivi des tâches patients. Génération de rappels à partir des rendez-vous confirmés.',
  },
  PATIENT: {
    canCreate: false, canEdit: false, canDelete: false,
    canGenerateReminder: false, canSeeAllTasks: false,
    label: 'Patient',
    description: 'Consulter vos rappels de suivi.',
  },
};

const DEFAULT_PERMISSIONS: RolePermissions = PERMISSIONS.PATIENT;

@Component({
  selector: 'app-follow-up',
  imports: [Icon, ReactiveFormsModule, Reminders, AiFeatures],
  templateUrl: './follow-up.html',
  styleUrl: './follow-up.scss',
})
export class FollowUp {
  private http = inject(HttpClient);
  private fb   = inject(FormBuilder);
  private auth = inject(AuthService);

  // ── Permissions du rôle courant ───────────────────────────────────────────
  readonly perms = computed<RolePermissions>(() => {
    const role = this.auth.user()?.role as Role | undefined;
    return role ? (PERMISSIONS[role] ?? DEFAULT_PERMISSIONS) : DEFAULT_PERMISSIONS;
  });

  readonly roleLabel = computed(() => this.perms().label);

  // ── State ─────────────────────────────────────────────────────────────────
  tasks        = signal<Task[]>([]);
  stats        = signal<TaskStats>({ total: 0, pending: 0, done: 0, cancelled: 0 });
  loading      = signal(true);
  apiError     = signal<string | null>(null);
  statusFilter = signal<StatusFilter>('all');

  showCreateModal = signal(false);
  showEditModal   = signal(false);
  showDetailModal = signal(false);
  detailTask      = signal<Task | null>(null);
  editingTask     = signal<Task | null>(null);
  submitting      = signal(false);

  reminderResult  = signal<ReminderDraft | null>(null);
  reminderLoading = signal(false);
  reminderError   = signal<string | null>(null);
  createForm = this.fb.nonNullable.group({
    description:        ['', [Validators.required, Validators.maxLength(1000)]],
    due_date:           ['', Validators.required],
    patient_id:         ['', Validators.required],
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

  // ── Patient select — chargement de tous les patients ──────────────────────
  allPatients     = signal<PatientOption[]>([]);
  patientsLoading = signal(false);
  selectedPatient = signal<PatientOption | null>(null);

  loadPatients() {
    if (this.allPatients().length > 0) return; // déjà chargé
    this.patientsLoading.set(true);
    this.http.get<{ items: PatientOption[] }>('/api/patients?size=100&page=1').subscribe({
      next: res => { this.allPatients.set(res.items); this.patientsLoading.set(false); },
      error: ()  => this.patientsLoading.set(false),
    });
  }

  onPatientChange(id: string) {
    const p = this.allPatients().find(x => x.id === id) ?? null;
    this.selectedPatient.set(p);
    this.createForm.patchValue({ patient_id: id });
  }

  // ── Tabs ──────────────────────────────────────────────────────────────────
  activeTab = signal<'tasks' | 'reminders' | 'summary' | 'noshow' | 'schedule' | 'adaptive' | 'lost' | 'weekly'>('tasks');

  constructor() { this.loadAll(); }

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

  setFilter(f: StatusFilter) { this.statusFilter.set(f); this.loadAll(); }

  // ── Create ────────────────────────────────────────────────────────────────
  openCreate() {
    if (!this.perms().canCreate) return;
    this.createForm.reset();
    this.selectedPatient.set(null);
    this.loadPatients();
    this.showCreateModal.set(true);
  }

  submitCreate() {
    if (!this.perms().canCreate || this.createForm.invalid) {
      this.createForm.markAllAsTouched(); return;
    }
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
    if (!this.perms().canEdit) return;
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
    if (!task || !this.perms().canEdit) return;
    this.submitting.set(true);
    const v = this.editForm.getRawValue();
    const payload: Record<string, string> = {};
    if (v.description.trim()) payload['description'] = v.description.trim();
    if (v.due_date)            payload['due_date']    = v.due_date;
    if (v.status)              payload['status']      = v.status;

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
    if (!this.perms().canDelete) return;
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
    if (!this.perms().canGenerateReminder) return;
    this.reminderForm.setValue({
      patient_name:       task.patient_name,
      appointment_date:   task.appointment_date,
      appointment_reason: task.appointment_reason,
    });
    this.reminderResult.set(null);
    setTimeout(() => document.getElementById('reminder-section')?.scrollIntoView({ behavior: 'smooth' }), 100);
  }

  generateReminder() {
    if (!this.perms().canGenerateReminder || this.reminderForm.invalid) {
      this.reminderForm.markAllAsTouched(); return;
    }
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

  statusLabel(s: string) {
    return ({ pending: 'En attente', done: 'Terminé', cancelled: 'Annulé' } as any)[s] ?? s;
  }

  isInvalid(form: any, field: string) {
    const c = form.get(field);
    return c?.invalid && (c.touched || c.dirty);
  }
}
