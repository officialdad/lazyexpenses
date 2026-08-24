<script lang="ts">
  import { base } from '$app/paths';
  import { app, latestMonth } from '$lib/data';
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
         #66: an icon button, same cog as the BottomNav tab, so the two read as one feature. -->
    <a href="{base}/settings" class="iconbtn {bare ? 'ml-auto' : ''}" aria-label="Settings" title="Settings" style="color:var(--muted)">
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
</style>
