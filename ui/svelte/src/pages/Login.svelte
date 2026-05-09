<script>
  import { createEventDispatcher } from 'svelte';
  import { auth } from '../lib/stores.js';
  import { apiLogin } from '../lib/api.js';

  const dispatch = createEventDispatcher();

  let username = '';
  let password = '';
  let error    = '';
  let loading  = false;

  async function submit() {
    error   = '';
    loading = true;
    try {
      const data = await apiLogin(username, password);
      auth.login(data.access_token, { username });
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  function onKey(e) { if (e.key === 'Enter') submit(); }
</script>

<div class="auth-wrap">
  <div class="card">
    <div class="logo">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2">
        <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
      </svg>
    </div>
    <h1>Plant Alarm System</h1>
    <p class="sub">Industrial sensor anomaly detection</p>

    <form on:submit|preventDefault={submit}>
      <label>
        Username
        <input bind:value={username} on:keydown={onKey} placeholder="operator01" autocomplete="username" />
      </label>
      <label>
        Password
        <input type="password" bind:value={password} on:keydown={onKey} autocomplete="current-password" />
      </label>

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" class="btn-primary" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>

    <p class="switch">
      No account?
      <button class="link-btn" on:click={() => dispatch('switch')}>Register</button>
    </p>
  </div>
</div>

<style>
  .auth-wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 100%);
    padding: 20px;
  }
  .card {
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.10);
    padding: 40px 36px;
    width: 100%;
    max-width: 380px;
    text-align: center;
  }
  .logo { margin-bottom: 12px; }
  h1 {
    font-size: 1.4rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 6px;
  }
  .sub {
    font-size: 0.8rem;
    color: #64748b;
    margin: 0 0 28px;
  }
  form { text-align: left; }
  label {
    display: block;
    font-size: 0.82rem;
    font-weight: 600;
    color: #374151;
    margin-bottom: 14px;
  }
  input {
    display: block;
    width: 100%;
    margin-top: 5px;
    padding: 10px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.9rem;
    box-sizing: border-box;
    transition: border-color 0.15s;
  }
  input:focus { outline: none; border-color: #0f766e; box-shadow: 0 0 0 3px rgba(15,118,110,0.12); }
  .btn-primary {
    width: 100%;
    padding: 11px;
    background: #0f766e;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    margin-top: 6px;
    transition: background 0.15s;
  }
  .btn-primary:hover:not(:disabled) { background: #0d6460; }
  .btn-primary:disabled { opacity: 0.6; cursor: wait; }
  .error { color: #dc2626; font-size: 0.82rem; margin: -4px 0 8px; }
  .switch { font-size: 0.82rem; color: #6b7280; margin-top: 20px; }
  .link-btn {
    background: none;
    border: none;
    color: #0f766e;
    cursor: pointer;
    font-weight: 600;
    text-decoration: underline;
    font-size: inherit;
  }
</style>
