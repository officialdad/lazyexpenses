<script lang="ts">
  // Step 2-4 of #40 are all optional, so they have to be reachable after the first run.
  // Same component as the first-run flow — same four questions, different framing.
  //
  // The #65 default-password banner used to live here with its own GET. It moved into
  // <Setup> (#74) because this route does not mount on an empty volume, so the warning
  // was missing from first-run setup — where it matters most. It reads cfg now, which
  // <Setup> already loads.
  import Setup from '$lib/components/Setup.svelte';
</script>

<svelte:head><title>Settings</title></svelte:head>

<Setup />
