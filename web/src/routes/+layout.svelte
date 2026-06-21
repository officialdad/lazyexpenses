<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>

<svelte:head>
  <meta name="theme-color" content="#000000" />
</svelte:head>

{@render children()}
