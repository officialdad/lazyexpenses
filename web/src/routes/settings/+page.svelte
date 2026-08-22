<script lang="ts">
  // Step 2-4 of #40 are all optional, so they have to be reachable after the first run.
  // Same component as the first-run flow — same four questions, different framing.
  import { onMount } from 'svelte';
  import Setup from '$lib/components/Setup.svelte';

  // #65: .env.example ships APP_PASSWORD=changeme@123 so a fresh `docker compose up` is
  // closed rather than open — but that value is printed in a public repo, so it is a
  // placeholder and not a password. The server answers a BOOLEAN (never the value, like
  // every secret in settings.public()) and this nags until it changes.
  //
  // ponytail: its own fetch rather than a field on the shared `cfg` store — one extra
  // cached GET against a route Setup is loading anyway, and it keeps this to one file.
  let stillDefault = $state(false);
  onMount(async () => {
    try {
      const res = await fetch('/api/settings');
      if (res.ok) stillDefault = !!((await res.json()) as { default_password?: boolean }).default_password;
    } catch {
      /* offline: the banner is a nag, not a gate */
    }
  });
</script>

<svelte:head><title>Settings</title></svelte:head>

{#if stillDefault}
  <div class="mx-auto max-w-xl px-4 pt-8">
    <p
      class="border p-3 text-sm"
      style="border-color:var(--over);color:var(--over)"
      role="alert"
    >
      <strong>Change your password.</strong> This app is still using the placeholder
      <code>changeme@123</code> that ships in <code>.env.example</code> — it is in a public repo,
      so it is not a secret. Set <code>APP_PASSWORD</code> in your <code>.env</code> to something
      only you know and restart.
    </p>
  </div>
{/if}
<Setup />
