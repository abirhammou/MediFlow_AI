import { describe, expect, it } from 'vitest';
import { UserProfile, homeFor } from '../../core/auth/auth.service';
import { slotsByDay } from '../appointments/appointments.model';

function user(overrides: Partial<UserProfile>): UserProfile {
  return {
    id: '1',
    email: 'x@y.z',
    first_name: 'A',
    last_name: 'B',
    role: 'PATIENT',
    is_active: true,
    patient_id: 'p1',
    created_at: '2026-10-01T08:00:00Z',
    last_login_at: null,
    ...overrides,
  };
}

describe('homeFor', () => {
  it('sends a temporary password to the password change first', () => {
    expect(homeFor(user({ must_change_password: true }))).toBe('/change-password');
  });

  it('sends patients to their portal and staff to the dashboard', () => {
    expect(homeFor(user({}))).toBe('/portal');
    expect(homeFor(user({ role: 'SECRETARY', patient_id: null }))).toBe('/dashboard');
  });
});

describe('slotsByDay', () => {
  it('groups the slots by local day, in order', () => {
    const slots = [
      { startAt: '2026-11-02T08:00:00Z', endAt: '2026-11-02T08:30:00Z' },
      { startAt: '2026-11-02T08:30:00Z', endAt: '2026-11-02T09:00:00Z' },
      { startAt: '2026-11-03T08:00:00Z', endAt: '2026-11-03T08:30:00Z' },
    ];
    const days = slotsByDay(slots);
    expect(days.map((d) => d.slots.length)).toEqual([2, 1]);
  });
});
