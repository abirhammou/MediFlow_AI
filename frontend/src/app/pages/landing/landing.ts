import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Logo } from '../../shared/logo/logo';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-landing',
  imports: [RouterLink, Logo, Icon],
  templateUrl: './landing.html',
  styleUrl: './landing.scss',
})
export class Landing {
  year = new Date().getFullYear();

  nav = [
    { label: 'Accueil', href: '#accueil' },
    { label: 'Services', href: '#services' },
    { label: 'Contact', href: '#contact' },
  ];

  highlights = [
    { icon: 'calendar', title: 'Prise de rendez-vous', text: 'En quelques clics' },
    { icon: 'activity', title: 'Suivi médical', text: 'Toujours à jour' },
    { icon: 'shield', title: 'Conseils personnalisés', text: "Grâce à l'IA" },
    { icon: 'zap', title: 'Accès rapide', text: 'À vos documents' },
  ];

  services = [
    { icon: 'user', title: 'Consultations', text: 'Prenez rendez-vous avec les meilleurs spécialistes.' },
    { icon: 'file', title: 'Dossiers médicaux', text: 'Accédez à votre historique de santé.' },
    { icon: 'heart', title: 'Suivi personnalisé', text: 'Des recommandations adaptées à votre profil.' },
    { icon: 'chat', title: 'Assistance IA', text: 'Des réponses fiables à vos questions santé.' },
  ];
}
