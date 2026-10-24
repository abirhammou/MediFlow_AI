import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ConfirmHost } from './shared/confirm-dialog/confirm-host';
import { ToastHost } from './shared/toast/toast-host';

@Component({
  imports: [RouterOutlet, ToastHost, ConfirmHost],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly title = signal('frontend');
}
