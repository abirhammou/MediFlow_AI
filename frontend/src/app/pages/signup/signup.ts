import { Component, inject, signal } from '@angular/core';
import {
  AbstractControl, FormBuilder, ReactiveFormsModule, ValidationErrors, Validators,
} from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AuthLayout } from '../../shared/auth-layout/auth-layout';
import { Icon } from '../../shared/icon/icon';

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const pwd = group.get('password')?.value;
  const confirm = group.get('confirmPassword')?.value;
  return pwd && confirm && pwd !== confirm ? { mismatch: true } : null;
}

type Field = 'fullName' | 'email' | 'password' | 'confirmPassword' | 'terms';

@Component({
  selector: 'app-signup',
  imports: [ReactiveFormsModule, RouterLink, AuthLayout, Icon],
  templateUrl: './signup.html',
  styleUrl: './signup.scss',
})
export class Signup {
  private fb = inject(FormBuilder);

  showPassword = signal(false);
  showConfirm = signal(false);
  submitting = signal(false);

  form = this.fb.nonNullable.group(
    {
      fullName: ['', [Validators.required, Validators.minLength(3)]],
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
    // TODO: call AuthService.register(...) then navigate to /login or the dashboard
    const { confirmPassword, ...payload } = this.form.getRawValue();
    console.log('signup', payload);
    setTimeout(() => this.submitting.set(false), 600);
  }
}
