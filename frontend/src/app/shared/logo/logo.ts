import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-logo',
  imports: [RouterLink],
  template: `
    <a routerLink="/" class="logo" aria-label="MediFlow AI, accueil">
      <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 2h6v7h7v6h-7v7H9v-7H2V9h7z" fill="var(--primary)" stroke="var(--primary)" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>
      <span>MediFlow AI</span>
    </a>
  `,
  styles: `
    .logo { display: inline-flex; align-items: center; gap: .5rem; color: var(--ink);
            font-weight: 700; font-size: 1.05rem; letter-spacing: -.01em; }
    .logo:hover { text-decoration: none; }
  `,
})
export class Logo {}
