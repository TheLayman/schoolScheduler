<script lang="ts">
  export let message: string;
  export let onClose: () => void;
</script>

<div class="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
  <div class="bg-white p-8 rounded-lg shadow-lg max-w-md w-full">
    <div class="flex flex-col items-center space-y-4">
      <div class="text-red-500 text-5xl">⚠️</div>
      
      <h2 class="text-xl font-semibold text-center">Schedule Generation Failed</h2>
      
      <div class="text-gray-600 text-center">
        {message}
      </div>

      <button 
        on:click={onClose}
        class="mt-4 bg-blue-500 text-white px-6 py-2 rounded-lg hover:bg-blue-600"
      >
        Close
      </button>
    </div>
  </div>
</div> 