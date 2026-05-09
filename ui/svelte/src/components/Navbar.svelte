<script>
  import { auth, currentPage } from '../lib/stores.js';

  function nav(page) { currentPage.set(page); }
</script>

<nav>
  <div class="brand">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
    </svg>
    <span>Plant Alarm</span>
  </div>

  <div class="links">
    {#each [['dashboard','Dashboard'],['history','History'],['predict','Predict'],['forecast','Forecast']] as [p, label]}
      <button class:active={$currentPage === p} on:click={() => nav(p)}>{label}</button>
    {/each}
  </div>

  <div class="user-row">
    <span class="username">{$auth.user?.username ?? ''}</span>
    <button class="btn-logout" on:click={() => auth.logout()}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
      </svg>
      Logout
    </button>
  </div>
</nav>

<style>
  nav {
    display: flex;
    align-items: center;
    background: #0f172a;
    color: #f1f5f9;
    padding: 0 20px;
    height: 54px;
    gap: 0;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 700;
    font-size: 0.95rem;
    color: #34d399;
    white-space: nowrap;
    margin-right: 32px;
  }

  .links {
    display: flex;
    gap: 2px;
    flex: 1;
  }

  .links button {
    background: transparent;
    border: none;
    color: #94a3b8;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.88rem;
    font-weight: 500;
    transition: background 0.15s, color 0.15s;
  }
  .links button:hover { background: #1e293b; color: #f1f5f9; }
  .links button.active { background: #0f766e; color: #fff; }

  .user-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .username {
    font-size: 0.82rem;
    color: #64748b;
  }

  .btn-logout {
    display: flex;
    align-items: center;
    gap: 5px;
    background: transparent;
    border: 1px solid #334155;
    color: #94a3b8;
    padding: 5px 11px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.15s;
  }
  .btn-logout:hover { background: #1e293b; color: #f87171; border-color: #f87171; }
</style>
