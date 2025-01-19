<script lang="ts">
  export let logs: string[] = [];
  let consoleDiv: HTMLDivElement;

  // Auto-scroll to bottom when new logs arrive
  $: if (consoleDiv && logs.length) {
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
  }

  // Format log message with appropriate color
  function getLogClass(log: string): string {
    if (log.includes('❌')) return 'error';
    if (log.includes('⚠️')) return 'warning';
    if (log.includes('✅')) return 'success';
    if (log.includes('📋')) return 'suggestion';
    if (log.includes('🔍')) return 'analysis';
    if (log.startsWith('   -')) return 'detail';
    if (log.startsWith('  -')) return 'detail';
    return '';
  }
</script>

<div class="console" bind:this={consoleDiv}>
  {#each logs as log}
    <div class="log-line {getLogClass(log)}">
      <span class="timestamp">{new Date().toLocaleTimeString()}</span>
      <span class="message">{log}</span>
    </div>
  {/each}
</div>

<style>
  .console {
    background: #1e1e1e;
    color: #fff;
    font-family: monospace;
    padding: 1rem;
    height: 300px;
    overflow-y: auto;
    border-radius: 4px;
    margin: 1rem;
  }

  .log-line {
    padding: 2px 0;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .timestamp {
    color: #666;
    margin-right: 8px;
  }

  .message {
    color: #fff;
  }

  .error .message {
    color: #ff4444;
  }

  .warning .message {
    color: #ffbb33;
  }

  .success .message {
    color: #00C851;
  }

  .info .message {
    color: #33b5e5;
  }

  .analysis .message {
    color: #9c27b0;
    font-weight: bold;
  }

  .suggestion .message {
    color: #2196f3;
    font-weight: bold;
  }

  .detail .message {
    padding-left: 20px;
    color: #78909c;
  }

  /* Add some spacing between sections */
  .analysis {
    margin-top: 10px;
  }

  .suggestion {
    margin-top: 8px;
  }
</style> 