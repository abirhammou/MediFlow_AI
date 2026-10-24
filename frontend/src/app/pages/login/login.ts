import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
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

  showPassword = signal(false);
  submitting = signal(false);

  form = this.fb.nonNullable.group({
    identifier: ['', [Validators.required]],
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
    // TODO: call AuthService.login(this.form.getRawValue()) then router.navigate(['/patient/dashboard'])
    console.log('login', this.form.getRawValue());
    setTimeout(() => this.submitting.set(false), 600);
  }
}
