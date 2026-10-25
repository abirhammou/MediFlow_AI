import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService, apiErrorMessage, homeFor } from '../../core/auth/auth.service';
import { AuthLayout } from '../../shared/auth-layout/auth-layout';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink, AuthLayout, Icon],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private fb = inject(FormBuilder);
  private auth = inject(AuthService);
  private router = inject(Router);

  showPassword = signal(false);
  submitting = signal(false);
  error = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    identifier: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(6)]],
    remember: [false],
  });

  invalid(name: 'identifier' | 'password') {
    const c = this.form.controls[name];
    return c.invalid && (c.touched || c.dirty);
  }

  submit() {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    const { identifier, password, remember } = this.form.getRawValue();
    this.auth.login(identifier, password, remember).subscribe({
      next: user => this.router.navigateByUrl(homeFor(user)),
      error: err => {
        this.error.set(apiErrorMessage(err));
        this.submitting.set(false);
      },
    });
  }
}
