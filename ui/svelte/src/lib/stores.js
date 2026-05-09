import { writable, derived } from 'svelte/store';

// ── Auth ──────────────────────────────────────────────────────────────────────
function createAuthStore() {
  const initialToken = localStorage.getItem('pa_token');
  const initialUser  = (() => {
    try { return JSON.parse(localStorage.getItem('pa_user') || 'null'); } catch { return null; }
  })();

  const { subscribe, set } = writable({ token: initialToken, user: initialUser });

  return {
    subscribe,
    login(token, user) {
      localStorage.setItem('pa_token', token);
      localStorage.setItem('pa_user', JSON.stringify(user));
      set({ token, user });
    },
    logout() {
      localStorage.removeItem('pa_token');
      localStorage.removeItem('pa_user');
      set({ token: null, user: null });
    },
  };
}

export const auth            = createAuthStore();
export const isAuthenticated = derived(auth, $a => !!$a.token);

// ── Navigation ────────────────────────────────────────────────────────────────
export const currentPage = writable('dashboard');

// ── Live sensor + inference state ─────────────────────────────────────────────
export const liveSensor      = writable(null);   // latest /sensors/live response
export const riskHistory     = writable([]);     // [{ts, y, alarm}] for the risk chart
export const isAutoInferring = writable(false);
export const lastAutoResult  = writable(null);
