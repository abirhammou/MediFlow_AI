import { Component, ElementRef, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { Icon } from '../../../shared/icon/icon';
import {
  ChatAnswer,
  ChatSource,
  MAX_CHAT_HISTORY,
  SOURCE_KIND_LABELS,
  aiErrorMessage,
  citationParts,
} from '../history.model';
import { HistoryService } from '../history.service';

interface Message {
  question: string;
  answer?: ChatAnswer;
  error?: string;
}

/**
 * "Poser une question" drawer (DOCTOR / ADMIN): answers come only from the patient's
 * reports, notes and medical files, with their sources. Nothing is stored server side;
 * the conversation is lost when the page changes.
 */
@Component({
  selector: 'app-patient-chat',
  imports: [Icon],
  templateUrl: './patient-chat.html',
  styleUrl: './patient-chat.scss',
})
export class PatientChat {
  readonly patientId = input.required<string>();

  private history = inject(HistoryService);
  protected readonly kindLabels = SOURCE_KIND_LABELS;
  protected readonly citationParts = citationParts;

  protected messages = signal<Message[]>([]);
  protected question = signal('');
  protected asking = signal(false);
  private drawer = viewChild<ElementRef<HTMLDialogElement>>('drawer');
  private thread = viewChild<ElementRef<HTMLElement>>('thread');

  constructor() {
    // Another patient: a new conversation.
    effect(() => {
      this.patientId();
      untracked(() => this.messages.set([]));
    });
  }

  open(): void {
    this.drawer()?.nativeElement.showModal();
  }

  protected close(): void {
    this.drawer()?.nativeElement.close();
  }

  protected source(answer: ChatAnswer, id: string): ChatSource | undefined {
    return answer.sources.find((s) => s.id === id);
  }

  protected ask(): void {
    const question = this.question().trim();
    if (!question || this.asking()) return;
    const history = this.messages()
      .filter((m) => m.answer?.found)
      .slice(-MAX_CHAT_HISTORY)
      .map((m) => ({ question: m.question, answer: m.answer!.answer }));
    this.messages.update((list) => [...list, { question }]);
    this.question.set('');
    this.asking.set(true);
    this.scrollDown();
    this.history.ask(this.patientId(), question, history).subscribe({
      next: (answer) => this.settle({ question, answer }),
      error: (err) => this.settle({ question, error: aiErrorMessage(err) }),
    });
  }

  private settle(message: Message): void {
    this.asking.set(false);
    this.messages.update((list) => [...list.slice(0, -1), message]);
    this.scrollDown();
  }

  private scrollDown(): void {
    setTimeout(() => {
      const el = this.thread()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  protected onKey(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.ask();
    }
  }
}
