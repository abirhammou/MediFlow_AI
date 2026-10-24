import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Logo } from '../logo/logo';
import { Icon } from '../icon/icon';

@Component({
  selector: 'app-auth-layout',
  imports: [Logo, Icon, RouterLink],
  template: `
    <main class="auth">
      <section class="card">
        <header>
          <app-logo />
          <h1>{{ title() }}</h1>
          <p>{{ subtitle() }}</p>
        </header>
        <ng-content />
      </section>
      <a routerLink="/" class="back"><app-icon name="arrow-left" [size]="16" /> Retour à l'accueil</a>
    </main>
  `,
  styleUrl: './auth-layout.scss',
})
export class AuthLayout {
  title = input.required<string>();
  subtitle = input('');
}
