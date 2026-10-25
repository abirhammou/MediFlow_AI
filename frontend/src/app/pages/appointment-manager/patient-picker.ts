import { Component, OnDestroy, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DirectoryService, PatientOption } from './directory.service';

/** Choisir un patient par son nom (au lieu de coller un identifiant). */
@Component({
  selector: 'app-patient-picker',
  imports: [FormsModule, RouterLink],
  template: `
    @if (selected(); as s) {
      <div class="picked">
        <span><strong>{{ s.name }}</strong> <small>· dossier {{ s.recordNumber }}</small></span>
        <button type="button" class="link" (click)="clear()">Changer</button>
      </div>
    } @else {
      <input type="search" [ngModel]="query()" (ngModelChange)="onType($event)" placeholder="Rechercher un patient par nom…" autocomplete="off" />
      @if (open()) {
        <ul class="results">
          @for (o of options(); track o.id) {
            <li><button type="button" (click)="pick(o)">{{ o.name }} <small>{{ o.recordNumber }}</small></button></li>
          } @empty {
            <li class="none">Aucun patient trouvé.</li>
          }
        </ul>
      }
    }
    @if (allowCreate()) {
      <a class="new" routerLink="/patients/new">+ Nouveau patient</a>
    }
  `,
  styles: [
    `:host { display: block; position: relative; }
     input { width: 100%; padding: 10px 14px; border: 1px solid #e5e7eb; border-radius: 10px; font: inherit; font-size: 14px; }
     input:focus { outline: none; border-color: #7c3aed; }
     .results { position: absolute; z-index: 20; left: 0; right: 0; margin: 4px 0 0; padding: 4px; list-style: none;
       background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 8px 24px rgba(15,23,42,.12); }
     .results button { width: 100%; text-align: left; padding: 8px 10px; border: 0; background: none; border-radius: 8px; cursor: pointer; font: inherit; font-size: 13px; }
     .results button:hover { background: #f5f3ff; }
     small { color: #94a3b8; }
     .none { padding: 8px 10px; color: #64748b; font-size: 13px; }
     .picked { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 10px; font-size: 14px; }
     .link { border: 0; background: none; color: #7c3aed; cursor: pointer; font: inherit; font-size: 13px; font-weight: 600; }
     .new { display: inline-block; margin-top: 6px; font-size: 12px; font-weight: 600; color: #7c3aed; }`,
  ],
})
export class PatientPicker implements OnDestroy {
  private readonly directory = inject(DirectoryService);

  readonly picked = output<PatientOption | null>();
  readonly allowCreate = input(false);

  readonly query = signal('');
  readonly options = signal<PatientOption[]>([]);
  readonly open = signal(false);
  readonly selected = signal<PatientOption | null>(null);
  private timer: ReturnType<typeof setTimeout> | undefined;

  onType(value: string): void {
    this.query.set(value);
    clearTimeout(this.timer);
    if (!value.trim()) {
      this.open.set(false);
      return;
    }
    this.timer = setTimeout(() => {
      this.directory.searchPatients(value).subscribe(options => {
        this.options.set(options);
        this.open.set(true);
      });
    }, 250);
  }

  pick(option: PatientOption): void {
    this.selected.set(option);
    this.open.set(false);
    this.picked.emit(option);
  }

  clear(): void {
    this.selected.set(null);
    this.query.set('');
    this.options.set([]);
    this.picked.emit(null);
  }

  ngOnDestroy(): void {
    clearTimeout(this.timer);
  }
}