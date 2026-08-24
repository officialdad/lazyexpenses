<script lang="ts">
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { app, latestMonth } from '$lib/data';
  import { ensureSettings, markSetupSeen, nagSetup } from '$lib/setupnag.svelte';
  import { search, MAGNIFY } from '$lib/search.svelte';
  import SyncStatus from '$lib/components/SyncStatus.svelte';
  import Icon from './Icon.svelte';

  // #94: the first-run setup state renders this shell with no data behind it — app is
  // empty until the first statement lands. `bare` drops everything that reads `app`
  // (sections, month/range, SyncStatus, Search) and keeps brand + the settings cog.
  let { bare = false } = $props();

  const sections = [
    { id: 'overview', label: 'Overview' },
    { id: 'trends', label: 'Trends' },
    { id: 'cuts', label: 'Cuts' },
    { id: 'fees', label: 'Fees' },
  ];

  let active = $state('overview');

  // #96: the cog nags while nothing that would let mail or a locked PDF through is set.
  // ensureSettings() is shared with BottomNav — both navs are mounted at every width, and
  // sharing it is what keeps this one GET of /api/settings instead of two.
  onMount(ensureSettings);
  // Reaching /settings dismisses the nag, by URL as much as by clicking the cog. BottomNav
  // runs the same line against the same flag, so which of them mounts first is irrelevant.
  $effect(() => {
    if (page.url.pathname === base + '/settings') markSetupSeen();
  });
  // CALL IT. `nagSetup` left unread is a truthy function object, and pulses at a fully
  // configured user forever — see the note on nagSetup itself.
  const nag = $derived(nagSetup());

  // #86: the shell now renders TopBar on every route, including /settings, where none of
  // these sections exist. Swallowing the click there left every link dead — so preventDefault
  // only when there is something to scroll to, and let the href (/#id) route home otherwise.
  function go(e: MouseEvent, id: string) {
    const el = typeof document !== 'undefined' ? document.getElementById(id) : null;
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    active = id;
  }

  $effect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    // rootMargin: top-anchored band — a section activates when its top enters
    // the upper 30% of the viewport (0px top, -70% bottom shrinks the root).
    // This means #overview (at scrollTop≈0) is immediately intersecting on load.
    const obs = new IntersectionObserver(
      (entries) => {
        for (const en of entries) if (en.isIntersecting) active = en.target.id;
      },
      { rootMargin: '0px 0px -70% 0px' }
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    }
    // Force Overview active when scrolled to the very top (e.g. after manual
    // scroll-up that leaves no section top within the observer band).
    function onScroll() {
      if (window.scrollY < 10) active = 'overview';
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      obs.disconnect();
      window.removeEventListener('scroll', onScroll);
    };
  });
</script>

<!-- #94: `sticky top-0 z-20` lives on the layout wrapper, not here — this element is
     the wrapper's whole content, so sticking to it gave zero scroll range. The opaque
     background and border-b stay: a transparent sticky header shows scrolled content
     through itself. -->
<header class="border-b" style="background:var(--bg);border-color:var(--divider)">
  <div class="max-w-7xl mx-auto px-6 h-14 flex items-center gap-6">
    <span class="font-extrabold tracking-tight text-lg" style="color:var(--accent)">lazyexpenses</span>
    {#if !bare}
      <nav class="flex gap-5 text-[13px] uppercase tracking-wide font-bold">
        {#each sections as s}
          <a
            href={base + '/#' + s.id}
            onclick={(e) => go(e, s.id)}
            aria-current={active === s.id ? 'page' : undefined}
            style="color:{active === s.id ? 'var(--accent)' : 'var(--muted)'}"
          >{s.label}</a>
        {/each}
      </nav>
      <button type="button" onclick={() => (search.open = true)} aria-label="Search transactions"
        class="iconbtn ml-auto" style="color:var(--muted)">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d={MAGNIFY} /></svg>
      </button>
      <span class="text-[13px] uppercase tracking-wide font-bold" style="color:var(--muted)">
        {latestMonth()} · {app.range}
      </span>
    {/if}
    <!-- #40: the four setup steps are all optional, so they need a way back.
         #66: an icon button, same cog as the BottomNav tab, so the two read as one feature.
         #96: the ring hangs off THIS anchor, never off anything inside the icon. On a
         genuine first run app.json does not exist, so app.icons is empty and Icon renders
         its square-outline fallback (#64) — a ring anchored to the glyph would decorate a
         blank square differently from a cog. The anchor's box is 28px either way. -->
    <a href="{base}/settings" class="iconbtn {bare ? 'ml-auto' : ''} {nag ? 'nag' : ''}"
      aria-label={nag ? 'Settings — finish setup' : 'Settings'}
      title={nag ? 'Finish setup' : 'Settings'} style="color:var(--muted)">
      <Icon name="cog-outline" size={20} />
    </a>
    {#if !bare}<SyncStatus />{/if}
  </div>
</header>

<style>
  .iconbtn {
    display: inline-flex;
    padding: 0.25rem;
  }
  .iconbtn:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }

  /* #96: the ring is drawn on the anchor box, so it is the same ring whether the cog glyph
     or Icon's square-outline fallback sits inside it. 34px scaled to 1.35 is 46px against a
     56px header and a 24px gutter, so it cannot widen the page. */
  .nag {
    position: relative;
  }
  .nag::after {
    content: '';
    position: absolute;
    inset: -3px;
    border-radius: 9999px;
    border: 2px solid var(--accent);
    pointer-events: none;
    animation: nagpulse 2.4s ease-out infinite;
  }
  @keyframes nagpulse {
    0% {
      transform: scale(0.85);
      opacity: 0.9;
    }
    70%,
    100% {
      transform: scale(1.35);
      opacity: 0;
    }
  }
  /* The floor the rest of the project holds. No animation, but the state must still be
     visible, so the ring collapses to a static dot rather than vanishing. */
  @media (prefers-reduced-motion: reduce) {
    .nag::after {
      inset: auto -1px auto auto;
      top: -1px;
      width: 8px;
      height: 8px;
      border: 0;
      background: var(--accent);
      animation: none;
    }
  }
</style>
