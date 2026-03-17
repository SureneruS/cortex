<script lang="ts">
  import Terminal from "./lib/Terminal.svelte";
</script>

<main>
  <Terminal />
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background: #0c1117;
    overflow: hidden;
  }

  main {
    width: 100vw;
    height: 100vh;
    display: flex;
  }
</style>
