/** Shapes of /api/appointments (camelCase). */

export type AppointmentStatus = 'PENDING' | 'CONFIRMED' | 'CANCELLED' | 'COMPLETED' | 'NO_SHOW';

export const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, string> = {
  PENDING: 'En attente de confirmation',
  CONFIRMED: 'Confirmé',
  CANCELLED: 'Annulé',
  COMPLETED: 'Terminé',
  NO_SHOW: 'Absent',
};

export interface Doctor {
  id: string;
  name: string;
  specialty: string | null;
  officeRoom: string | null;
  availabilities: { dayOfWeek: number; startTime: string; endTime: string; slotMinutes: number }[];
}

export interface Slot {
  startAt: string;
  endAt: string;
}

export interface Appointment {
  id: string;
  patientId: string;
  patientName: string | null;
  recordNumber: string | null;
  doctorId: string;
  doctorName: string | null;
  specialty: string | null;
  startAt: string;
  endAt: string;
  reason: string | null;
  status: AppointmentStatus;
  cancelReason: string | null;
  createdAt: string;
}

export interface AppointmentPage {
  items: Appointment[];
  total: number;
  page: number;
  size: number;
}

const DAY = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
const HOUR = new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit' });

/** "lundi 3 novembre" */
export function dayLabel(iso: string): string {
  return DAY.format(new Date(iso));
}

/** "09:30" */
export function hourLabel(iso: string): string {
  return HOUR.format(new Date(iso));
}

/** Slots grouped by local day, in order. */
export function slotsByDay(slots: Slot[]): { day: string; slots: Slot[] }[] {
  const days = new Map<string, Slot[]>();
  for (const slot of slots) {
    const key = dayLabel(slot.startAt);
    days.set(key, [...(days.get(key) ?? []), slot]);
  }
  return [...days].map(([day, list]) => ({ day, slots: list }));
}
