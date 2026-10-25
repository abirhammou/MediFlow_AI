import { Component, OnDestroy, output, signal } from '@angular/core';

interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ERRORS: Record<string, string> = {
  'not-allowed': "Le micro est bloqué : autorisez-le dans le navigateur (icône à gauche de l'adresse).",
  'service-not-allowed': "Le micro est bloqué : autorisez-le dans le navigateur.",
  'no-speech': "Aucune voix détectée. Réessayez.",
  'audio-capture': "Aucun micro détecté.",
  network: "La reconnaissance vocale nécessite une connexion internet.",
};

/** Dicter une demande : le texte reconnu remplace le contenu du champ (il reste modifiable). */
@Component({
  selector: 'app-voice-button',
  template: `
    @if (supported) {
      <button type="button" class="mic" [class.on]="listening()" (click)="toggle()"
              [attr.aria-pressed]="listening()" [attr.title]="listening() ? 'Arrêter la dictée' : 'Dicter la demande'">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="9" y="2" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0" /><path d="M12 18v4" />
        </svg>
        {{ listening() ? 'Je vous écoute… (cliquez pour arrêter)' : 'Dicter' }}
      </button>
      @if (error()) { <small class="err">{{ error() }}</small> }
      <small class="hint">La dictée est traitée par le service de reconnaissance vocale de votre navigateur.</small>
    }
  `,
  styles: [
    `:host { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
     .mic { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border: 1px solid #ddd6fe; border-radius: 10px;
       background: #f5f3ff; color: #7c3aed; cursor: pointer; font: inherit; font-size: 13px; font-weight: 600; }
     .mic:hover { background: #ede9fe; }
     .mic.on { background: #fee2e2; border-color: #fecaca; color: #b91c1c; animation: pulse 1.2s infinite; }
     .err { color: #b91c1c; font-size: 12px; }
     .hint { color: #94a3b8; font-size: 11px; }
     @keyframes pulse { 50% { opacity: .65; } }`,
  ],
})
export class VoiceButton implements OnDestroy {
  /** Texte reconnu (mis à jour pendant que la personne parle). */
  readonly text = output<string>();

  readonly supported = recognitionCtor() !== null;
  readonly listening = signal(false);
  readonly error = signal('');
  private recognition: Recognition | null = null;

  toggle(): void {
    if (this.listening()) {
      this.recognition?.stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const recognition = new Ctor();
    recognition.lang = 'fr-FR';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = event => {
      const parts = Array.from(event.results).map(result => result[0].transcript);
      this.text.emit(parts.join(' ').trim());
    };
    recognition.onerror = event => this.error.set(ERRORS[event.error] ?? 'La dictée a échoué. Réessayez.');
    recognition.onend = () => this.listening.set(false);
    this.error.set('');
    this.recognition = recognition;
    this.listening.set(true);
    recognition.start();
  }

  ngOnDestroy(): void {
    this.recognition?.stop();
  }
}