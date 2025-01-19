<script lang="ts">
  export let message: string = 'Generating Schedule...';
  export let error: string | null = null;
  
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  
  // Timer functionality using Svelte store for better reactivity
  import { writable } from 'svelte/store';
  const elapsedTime = writable('0:00');
  let startTime: number;
  let timerInterval: ReturnType<typeof setInterval>;
  let rafId: number;

  function updateTimer() {
    if (!startTime) return;
    
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    elapsedTime.set(`${minutes}:${seconds.toString().padStart(2, '0')}`);
    
    // Request next frame for smooth updates
    rafId = requestAnimationFrame(updateTimer);
  }
  
  onMount(() => {
    startTime = Date.now();
    // Start the animation frame loop
    rafId = requestAnimationFrame(updateTimer);
  });

  onDestroy(() => {
    if (rafId) cancelAnimationFrame(rafId);
  });
</script>

<div class="overlay">
  <div class="content">
    <div class="timer">⏱️ {$elapsedTime}</div>
    <div class="gif-container">
      <img src="{base}/waiting.gif" alt="Loading animation" class="thinking-gif" />
    </div>
    <h2 class="message">{message}</h2>
    {#if error}
      <div class="error-message">
        {error}
      </div>
    {/if}
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
    backdrop-filter: blur(5px);
  }

  .content {
    background: #2a2a2a;
    padding: 3rem;
    border-radius: 16px;
    text-align: center;
    max-width: 90%;
    max-height: 90vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from {
      transform: translateY(-20px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .timer {
    font-size: 1.5rem;
    color: #3498db;
    font-weight: bold;
    font-family: monospace;
    animation: pulse 1s infinite;
  }

  @keyframes pulse {
    0% {
      opacity: 1;
    }
    50% {
      opacity: 0.7;
    }
    100% {
      opacity: 1;
    }
  }

  .gif-container {
    width: 400px;
    height: 400px;
    margin: 2rem auto;
    border-radius: 12px;
    overflow: hidden;
    background: #1a1a1a;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
  }

  .thinking-gif {
    width: 100%;
    height: 100%;
    object-fit: contain;
    padding: 1rem;
  }

  .message {
    color: white;
    margin: 0;
    font-size: 1.5rem;
    animation: fadeIn 0.5s ease-out;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .error-message {
    color: #ff4444;
    margin: 1rem 0;
    padding: 0.5rem;
    background: #ffebee;
    border-radius: 4px;
    animation: shake 0.5s ease-in-out;
  }

  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-5px); }
    75% { transform: translateX(5px); }
  }
</style> 