<script lang="ts">
  import SchedulerConsole from './SchedulerConsole.svelte';
  
  export let message: string = 'Generating Schedule...';
  export let logs: string[] = [];
  export let error: string | null = null;
</script>

<div class="overlay">
  <div class="content">
    <div class="spinner"></div>
    <h2>{message}</h2>
    {#if error}
      <div class="error-message">
        {error}
      </div>
    {/if}
    <div class="console-container">
      <h3>Generation Progress</h3>
      <SchedulerConsole {logs} />
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
  }

  .content {
    background: #2a2a2a;
    padding: 2rem;
    border-radius: 8px;
    text-align: center;
    max-width: 90%;
    max-height: 90vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  h2, h3 {
    color: white;
    margin: 0;
  }

  .console-container {
    text-align: left;
  }

  .spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .error-message {
    color: #ff4444;
    margin: 1rem 0;
    padding: 0.5rem;
    background: #ffebee;
    border-radius: 4px;
  }
</style> 