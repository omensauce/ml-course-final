<script>
  import { auth, isAuthenticated, currentPage } from './lib/stores.js';
  import Navbar   from './components/Navbar.svelte';
  import Login    from './pages/Login.svelte';
  import Register from './pages/Register.svelte';
  import Dashboard from './pages/Dashboard.svelte';
  import History  from './pages/History.svelte';
  import Predict  from './pages/Predict.svelte';
  import Forecast from './pages/Forecast.svelte';

  let showRegister = false;
</script>

{#if !$isAuthenticated}

  {#if showRegister}
    <Register on:switch={() => showRegister = false} />
  {:else}
    <Login on:switch={() => showRegister = true} />
  {/if}

{:else}

  <Navbar />

  <main>
    {#if $currentPage === 'dashboard'}
      <Dashboard />
    {:else if $currentPage === 'history'}
      <History />
    {:else if $currentPage === 'predict'}
      <Predict />
    {:else if $currentPage === 'forecast'}
      <Forecast />
    {/if}
  </main>

{/if}

<style>
  :global(*, *::before, *::after) { box-sizing: border-box; }

  :global(body) {
    margin: 0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #f1f5f9;
    color: #1e293b;
    -webkit-font-smoothing: antialiased;
  }

  main { min-height: calc(100vh - 54px); }
</style>
