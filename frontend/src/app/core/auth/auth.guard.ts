import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService, Role, UserProfile } from './auth.service';

/** Pages that need a signed-in user. */
export const authGuard: CanActivateFn = () =>
  inject(AuthService).isLoggedIn() || inject(Router).createUrlTree(['/login']);

/** Login and signup: a signed-in user goes straight to the dashboard. */
export const guestGuard: CanActivateFn = () =>
  !inject(AuthService).isLoggedIn() || inject(Router).createUrlTree(['/dashboard']);

/**
 * The authenticated shell: a clinic-created patient account on its temporary password
 * goes to /change-password first (the API refuses everything else meanwhile).
 */
export const passwordChangeGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const check = (user: UserProfile) => !user.must_change_password || router.createUrlTree(['/change-password']);
  const user = auth.user();
  if (user) return check(user);
  return auth.loadProfile().pipe(
    map(check),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};

/**
 * Pages limited to some roles (the API enforces them too). After a reload the
 * profile is not known yet: it is loaded first.
 */
export const roleGuard =
  (roles: readonly Role[]): CanActivateFn =>
  () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    const allowed = (user: UserProfile) =>
      roles.includes(user.role) || router.createUrlTree(['/dashboard']);

    const user = auth.user();
    if (user) return allowed(user);
    return auth.loadProfile().pipe(
      map(allowed),
      catchError(() => of(router.createUrlTree(['/login']))),
    );
  };
