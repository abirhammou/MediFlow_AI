import { Component, inject, signal, input, OnChanges, SimpleChanges } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { Icon } from '../../../shared/icon/icon';

interface PatientOption { id: string; firstName: string; lastName: string; recordNumber: string; }

// Response types
interface PatientHistorySummary { patient_name: string; summary: string; task_count: number; last_activity?: string; }
interface NoShowPrediction      { patient_name: string; probability: string; justification: string; recommendation: string; }
interface ScheduledCall         { task_id: string; patient_name: string; suggested_day: string; time_slot: string; reason: string; }
interface ScheduleResponse      { calls: ScheduledCall[]; }
interface AdaptiveReminderDraft { subject: string; body: string; tone_used: string; tone_reason: string; }
interface LostPatientMessage    { patient_name: string; days_inactive: number; last_reason?: string; message: string; }
interface LostPatientsResponse  { patients: LostPatientMessage[]; }
interface WeeklyReport          { week_start: string; week_end: string; activity_summary: string; at_risk_patients: string; trends: string; recommendations: string; }

type FeatureKey = 'summary' | 'noshow' | 'schedule' | 'adaptive' | 'lost' | 'weekly';

@Component({
  selector: 'app-ai-features',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './ai-features.html',
  styleUrl:    './ai-features.scss',
})
export class AiFeatures implements OnChanges {
  private http = inject(HttpClient);
  private fb   = inject(FormBuilder);

  // Input depuis le parent — synchronise l'onglet actif
  activeFeature = input<string>('summary');

  ngOnChanges(changes: SimpleChanges) {
    if (changes['activeFeature']) {
      this.loadPatients();
    }
  }

  // ── Patients ──────────────────────────────────────────────────────────────
  allPatients     = signal<PatientOption[]>([]);
  patientsLoading = signal(false);

  loadPatients() {
    this.patientsLoading.set(true);
    this.http.get<{ items: PatientOption[] }>('/api/patients?size=100&page=1').subscribe({
      next: r => { this.allPatients.set(r.items); this.patientsLoading.set(false); },
      error: () => this.patientsLoading.set(false),
    });
  }

  // ── Active tab — piloté par le parent ────────────────────────────────────
  // (activeFeature est maintenant un @input())

  // ── 1. Résumé patient ─────────────────────────────────────────────────────
  summaryLoading = signal(false);
  summaryResult  = signal<PatientHistorySummary | null>(null);
  summaryError   = signal<string | null>(null);

  summaryForm = this.fb.nonNullable.group({ patient_id: ['', Validators.required] });

  onSummaryPatient(id: string) {
    const p = this.allPatients().find(x => x.id === id);
    this.summaryForm.patchValue({ patient_id: id });
    if (p) this._summaryPatientName = `${p.firstName} ${p.lastName}`;
  }
  _summaryPatientName = '';

  runSummary() {
    if (this.summaryForm.invalid) return;
    this.summaryLoading.set(true); this.summaryResult.set(null); this.summaryError.set(null);
    this.http.post<PatientHistorySummary>('/api/follow-up/ai/patient-summary', {
      patient_id: this.summaryForm.value.patient_id, patient_name: this._summaryPatientName,
    }).subscribe({
      next: r  => { this.summaryResult.set(r); this.summaryLoading.set(false); },
      error: (err) => {
        const msg = err?.error?.detail ?? 'Erreur Gemini.';
        this.summaryError.set(err?.status === 429 ? '⏳ Quota Gemini dépassé — réessayez dans 1 minute.' : msg);
        this.summaryLoading.set(false);
      },
    });
  }

  // ── 2. No-show ────────────────────────────────────────────────────────────
  noshowLoading = signal(false);
  noshowResult  = signal<NoShowPrediction | null>(null);
  noshowError   = signal<string | null>(null);

  noshowForm = this.fb.nonNullable.group({
    patient_id:        ['', Validators.required],
    next_appointment:  ['', Validators.required],
    next_reason:       ['', Validators.required],
  });
  _noshowPatientName = '';

  onNoshowPatient(id: string) {
    const p = this.allPatients().find(x => x.id === id);
    this.noshowForm.patchValue({ patient_id: id });
    if (p) this._noshowPatientName = `${p.firstName} ${p.lastName}`;
  }

  runNoshow() {
    if (this.noshowForm.invalid) return;
    this.noshowLoading.set(true); this.noshowResult.set(null); this.noshowError.set(null);
    const v = this.noshowForm.getRawValue();
    this.http.post<NoShowPrediction>('/api/follow-up/ai/no-show', {
      patient_id: v.patient_id, patient_name: this._noshowPatientName,
      next_appointment: v.next_appointment, next_reason: v.next_reason,
    }).subscribe({
      next: r  => { this.noshowResult.set(r); this.noshowLoading.set(false); },
      error: (err) => { this.noshowError.set(this._geminiError(err)); this.noshowLoading.set(false); },
    });
  }

  noshowColor(p: string) { return { HIGH: '#dc2626', MEDIUM: '#d97706', LOW: '#16a34a' }[p] ?? '#64748b'; }
  noshowBg(p: string)    { return { HIGH: '#fee2e2', MEDIUM: '#fef9c3', LOW: '#dcfce7' }[p] ?? '#f1f5f9'; }
  noshowLabel(p: string) { return { HIGH: 'Risque élevé', MEDIUM: 'Risque modéré', LOW: 'Risque faible' }[p] ?? p; }

  // ── 3. Planification ──────────────────────────────────────────────────────
  scheduleLoading = signal(false);
  scheduleResult  = signal<ScheduledCall[]>([]);
  scheduleError   = signal<string | null>(null);

  scheduleForm = this.fb.nonNullable.group({
    start_date: ['', Validators.required],
    end_date:   ['', Validators.required],
  });

  runSchedule() {
    if (this.scheduleForm.invalid) return;
    this.scheduleLoading.set(true); this.scheduleResult.set([]); this.scheduleError.set(null);
    this.http.post<ScheduleResponse>('/api/follow-up/ai/schedule', this.scheduleForm.getRawValue()).subscribe({
      next: r  => { this.scheduleResult.set(r.calls); this.scheduleLoading.set(false); },
      error: (err) => { this.scheduleError.set(this._geminiError(err)); this.scheduleLoading.set(false); },
    });
  }

  slotColor(slot: string) {
    return { matin: '#fef9c3', 'après-midi': '#dbeafe', soir: '#ede9fe' }[slot.toLowerCase()] ?? '#f1f5f9';
  }

  // ── 4. Ton adaptatif ──────────────────────────────────────────────────────
  adaptiveLoading = signal(false);
  adaptiveResult  = signal<AdaptiveReminderDraft | null>(null);
  adaptiveError   = signal<string | null>(null);

  adaptiveForm = this.fb.nonNullable.group({
    patient_id:         ['', Validators.required],
    appointment_date:   ['', Validators.required],
    appointment_reason: ['', Validators.required],
  });
  _adaptivePatientName = '';

  onAdaptivePatient(id: string) {
    const p = this.allPatients().find(x => x.id === id);
    this.adaptiveForm.patchValue({ patient_id: id });
    if (p) this._adaptivePatientName = `${p.firstName} ${p.lastName}`;
  }

  runAdaptive() {
    if (this.adaptiveForm.invalid) return;
    this.adaptiveLoading.set(true); this.adaptiveResult.set(null); this.adaptiveError.set(null);
    const v = this.adaptiveForm.getRawValue();
    this.http.post<AdaptiveReminderDraft>('/api/follow-up/ai/adaptive-reminder', {
      patient_id: v.patient_id, patient_name: this._adaptivePatientName,
      appointment_date: v.appointment_date, appointment_reason: v.appointment_reason,
    }).subscribe({
      next: r  => { this.adaptiveResult.set(r); this.adaptiveLoading.set(false); },
      error: (err) => { this.adaptiveError.set(this._geminiError(err)); this.adaptiveLoading.set(false); },
    });
  }

  toneColor(t: string) {
    return { formel: '#3b82f6', chaleureux: '#10b981', urgent: '#ef4444' }[t?.toLowerCase()] ?? '#64748b';
  }

  // ── 5. Patients perdus de vue ─────────────────────────────────────────────
  lostLoading    = signal(false);
  lostResult     = signal<LostPatientMessage[]>([]);
  lostError      = signal<string | null>(null);
  inactivityDays = signal(30);

  runLost() {
    this.lostLoading.set(true); this.lostResult.set([]); this.lostError.set(null);
    this.http.post<LostPatientsResponse>(`/api/follow-up/ai/lost-patients?inactivity_days=${this.inactivityDays()}`, {}).subscribe({
      next: r  => { this.lostResult.set(r.patients); this.lostLoading.set(false); },
      error: (err) => { this.lostError.set(this._geminiError(err)); this.lostLoading.set(false); },
    });
  }

  // ── 6. Rapport hebdomadaire ───────────────────────────────────────────────
  weeklyLoading = signal(false);
  weeklyResult  = signal<WeeklyReport | null>(null);
  weeklyError   = signal<string | null>(null);

  weeklyForm = this.fb.nonNullable.group({
    week_start: ['', Validators.required],
    week_end:   ['', Validators.required],
  });

  runWeekly() {
    if (this.weeklyForm.invalid) return;
    this.weeklyLoading.set(true); this.weeklyResult.set(null); this.weeklyError.set(null);
    this.http.post<WeeklyReport>('/api/follow-up/ai/weekly-report', this.weeklyForm.getRawValue()).subscribe({
      next: r  => { this.weeklyResult.set(r); this.weeklyLoading.set(false); },
      error: (err) => { this.weeklyError.set(this._geminiError(err)); this.weeklyLoading.set(false); },
    });
  }

  exportWeeklyPdf() {
    const r = this.weeklyResult();
    if (!r) return;
    const content = `Rapport hebdomadaire ${r.week_start} – ${r.week_end}\n\n`
      + `ACTIVITÉ\n${r.activity_summary}\n\n`
      + `PATIENTS À RISQUE\n${r.at_risk_patients}\n\n`
      + `TENDANCES\n${r.trends}\n\n`
      + `RECOMMANDATIONS\n${r.recommendations}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `rapport_${r.week_start}.txt`; a.click();
    URL.revokeObjectURL(url);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  private _geminiError(err: any): string {
    if (err?.status === 429) return '⏳ Quota Gemini dépassé — attendez 1 minute et réessayez.';
    if (err?.status === 504) return '⏱️ Gemini n\'a pas répondu à temps — réessayez.';
    if (err?.status === 503) return '🔧 Service Gemini indisponible — réessayez plus tard.';
    return err?.error?.detail ?? 'Erreur lors de la génération Gemini.';
  }
}
