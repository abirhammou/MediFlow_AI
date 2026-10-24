import { Component, inject, signal } from '@angular/core';
import {
  AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';
import { AuthService, apiErrorMessage } from '../../core/auth/auth.service';
import { AuthLayout } from '../../shared/auth-layout/auth-layout';
import { Icon } from '../../shared/icon/icon';

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const pwd = group.get('password')?.value;
  const confirm = group.get('confirmPassword')?.value;
  return pwd && confirm && pwd !== confirm ? { mismatch: true } : null;
}

type Field = 'firstName' | 'lastName' | 'email' | 'password' | 'confirmPassword' | 'terms';

@Component({
  selector: 'app-signup',
  imports: [ReactiveFormsModule, RouterLink, AuthLayout, Icon],
  templateUrl: './signup.html',
  styleUrl: './signup.scss',
})
export class Signup {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  showPassword = signal(false);
  showConfirm = signal(false);
  submitting = signal(false);
  error = signal<string | null>(null);

  form = this.fb.nonNullable.group(
    {
      firstName: ['', [Validators.required, Validators.maxLength(80)]],
      lastName: ['', [Validators.required, Validators.maxLength(80)]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(8)]],
      confirmPassword: ['', [Validators.required]],
      terms: [false, [Validators.requiredTrue]],
    },
    { validators: passwordsMatch },
  );

  invalid(name: Field) {
    const c = this.form.controls[name];
    return c.invalid && (c.touched || c.dirty);
  }

  get mismatch() {
    return this.form.hasError('mismatch') && this.form.controls.confirmPassword.touched;
  }

  submit() {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    const { firstName, lastName, email, password } = this.form.getRawValue();
    // Self-registration creates an active PATIENT account: sign in right away.
    this.auth
      .register({ email, password, first_name: firstName.trim(), last_name: lastName.trim() })
      .pipe(switchMap(() => this.auth.login(email, password, false)))
      .subscribe({
        next: () => this.router.navigate(['/dashboard']),
        error: err => {
          this.error.set(apiErrorMessage(err));
          this.submitting.set(false);
        },
      });
  }
}
