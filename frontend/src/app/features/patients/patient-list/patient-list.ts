import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable, toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Params, Router, RouterLink } from '@angular/router';
import { catchError, debounceTime, map, of, switchMap, tap } from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { ageLabel } from '../birth-date';
import { PatientPermissions } from '../patient-permissions';
import {
  BLOOD_TYPES,
  BloodType,
  CITIES,
  GENDERS,
  GENDER_LABELS,
  Gender,
  Page,
  PatientListItem,
  PatientQuery,
  SORT_KEYS,
  Sort,
  SortKey,
} from '../patient.model';
import { PatientService } from '../patient.service';

const PAGE_SIZE = 20;
const DEFAULT_SORT: Sort = 'lastName';

interface Column {
  label: string;
  key: SortKey;
  /** Sort applied on the first click; the second click reverses it. */
  first: Sort;
}

const SORTABLE_COLUMNS: Record<string, Column> = {
  recordNumber: { label: 'N° dossier', key: 'recordNumber', first: 'recordNumber' },
  lastName: { label: 'Nom', key: 'lastName', first: 'lastName' },
  // Youngest first = latest birth date first.
  age: { label: 'Âge', key: 'dateOfBirth', first: '-dateOfBirth' },
};

function oneOf<T extends string>(values: readonly T[], value: string | null): T | undefined {
  return values.find(item => item === value);
}

/** The URL query params are the list state: a reload or a shared link keeps it. */
function readQuery(params: ParamMap): PatientQuery {
  const page = Number(params.get('page'));
  const sort = params.get('sort');
  const validSort = sort !== null && SORT_KEYS.some(key => sort === key || sort === `-${key}`);
  return {
    q: params.get('q')?.trim() || undefined,
    gender: oneOf(GENDERS, params.get('gender')),
    bloodType: oneOf(BLOOD_TYPES, params.get('bloodType')),
    city: params.get('city')?.trim() || undefined,
    page: Number.isInteger(page) && page > 1 ? page : 1,
    size: PAGE_SIZE,
    sort: validSort ? (sort as Sort) : undefined,
  };
}

@Component({
  selector: 'app-patient-list',
  imports: [ReactiveFormsModule, RouterLink, NgTemplateOutlet, Icon],
  templateUrl: './patient-list.html',
  styleUrl: './patient-list.scss',
})
export class PatientList {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private patients = inject(PatientService);
  protected perms = inject(PatientPermissions);

  protected readonly genders = GENDERS;
  protected readonly genderLabels = GENDER_LABELS;
  protected readonly bloodTypes = BLOOD_TYPES;
  protected readonly cities = CITIES;
  protected readonly columns = SORTABLE_COLUMNS;
  protected readonly ageLabel = ageLabel;

  protected query = toSignal(this.route.queryParamMap.pipe(map(readQuery)), { requireSync: true });
  protected filters = inject(FormBuilder).nonNullable.group({
    q: [''],
    gender: [''],
    bloodType: [''],
    city: [''],
  });

  /** Filters this page just put in the URL: syncing them back could erase newer typing. */
  private appliedFilters = '';

  protected loading = signal(true);
  protected error = signal<string | null>(null);
  protected result = signal<Page<PatientListItem> | null>(null);
  protected pageCount = computed(() => {
    const result = this.result();
    return result ? Math.max(1, Math.ceil(result.total / result.size)) : 1;
  });
  protected hasFilters = computed(() => {
    const { q, gender, bloodType, city } = this.query();
    return Boolean(q || gender || bloodType || city);
  });

  constructor() {
    toObservable(this.query)
      .pipe(
        tap(query => {
          this.syncFilters(query);
          this.loading.set(true);
          this.error.set(null);
        }),
        switchMap(query =>
          this.patients.list(query).pipe(
            catchError(err => {
              this.error.set(apiErrorMessage(err));
              return of(null);
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe(page => {
        this.loading.set(false);
        if (page) this.result.set(page);
      });

    this.filters.valueChanges
      .pipe(debounceTime(300), takeUntilDestroyed())
      .subscribe(() => this.applyFilters());
  }

  /** Back/forward navigation changes the URL: show its values in the inputs. */
  private syncFilters(query: PatientQuery): void {
    const values = {
      q: query.q ?? '',
      gender: query.gender ?? '',
      bloodType: query.bloodType ?? '',
      city: query.city ?? '',
    };
    const fromUrl = JSON.stringify(values);
    if (fromUrl === this.appliedFilters) return;
    const current = this.filters.getRawValue();
    const typed = { ...current, q: current.q.trim(), city: current.city.trim() };
    if (JSON.stringify(typed) !== fromUrl) this.filters.setValue(values, { emitEvent: false });
  }

  private applyFilters(): void {
    const { q, gender, bloodType, city } = this.filters.getRawValue();
    const next = {
      q: q.trim() || null,
      gender: (gender as Gender) || null,
      bloodType: (bloodType as BloodType) || null,
      city: city.trim() || null,
    };
    const query = this.query();
    const unchanged =
      next.q === (query.q ?? null) &&
      next.gender === (query.gender ?? null) &&
      next.bloodType === (query.bloodType ?? null) &&
      next.city === (query.city ?? null);
    if (unchanged) return;
    this.appliedFilters = JSON.stringify({
      q: next.q ?? '',
      gender: next.gender ?? '',
      bloodType: next.bloodType ?? '',
      city: next.city ?? '',
    });
    this.navigate({ ...next, page: null });
  }

  private navigate(changes: Params): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: changes,
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected resetFilters(): void {
    this.appliedFilters = '';
    this.filters.setValue({ q: '', gender: '', bloodType: '', city: '' }, { emitEvent: false });
    this.navigate({ q: null, gender: null, bloodType: null, city: null, page: null });
  }

  protected currentSort(): Sort {
    return this.query().sort ?? DEFAULT_SORT;
  }

  protected sortState(column: Column): 'first' | 'reversed' | null {
    const sort = this.currentSort();
    if (sort.replace(/^-/, '') !== column.key) return null;
    return sort === column.first ? 'first' : 'reversed';
  }

  protected sortBy(column: Column): void {
    const next: Sort =
      this.currentSort() === column.first ? (reverse(column.first) as Sort) : column.first;
    this.navigate({ sort: next === DEFAULT_SORT ? null : next, page: null });
  }

  protected ariaSort(column: Column): 'ascending' | 'descending' | 'none' {
    if (this.sortState(column) === null) return 'none';
    return this.currentSort().startsWith('-') ? 'descending' : 'ascending';
  }

  protected goToPage(page: number): void {
    this.navigate({ page: page > 1 ? page : null });
  }

  protected open(patient: PatientListItem): void {
    this.router.navigate(['/patients', patient.id]);
  }
}

function reverse(sort: Sort): string {
  return sort.startsWith('-') ? sort.slice(1) : `-${sort}`;
}
