<script lang="ts">
  // First-run setup and Settings (#40) — the same four steps either way, because they
  // are the same four questions. `first` only changes the framing: on an empty volume
  // this IS the app, afterwards it is a page you came back to.
  //
  // Deliberately no <Icon>: icons ship inside app.json, which does not exist yet on the
  // volume this screen exists for. Numbers render everywhere.
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { app, loadAppData } from '$lib/data';
  import { cats } from '$lib/cats.svelte';
  import { push, togglePush } from '$lib/push.svelte';
  import {
    cfg, isLocked, loadSettings, saveSettings, testMail, testReminder, upload, reconLine,
    startBackfill, backfillStatus, backfillLine, type Backfill
  } from '$lib/setup.svelte';

  let { first = false }: { first?: boolean } = $props();

  onMount(() => {
    loadSettings();
    // A backfill outlives this page: it runs on the server for minutes. If one is
    // already going, pick its progress back up rather than showing a fresh button.
    backfillStatus().then((b) => { if (b?.running) { bfBusy = true; poll(b); } });
  });

  const APP_PW_URL = 'https://myaccount.google.com/apppasswords';
  const pretty = (b: string) => (b === 'sc' ? 'Standard Chartered' : b.toUpperCase());
  const say = (ok: boolean, m: string) => ({ ok, m });

  // ---------------------------------------------------------------- 1. upload
  let bank = $state('');
  let files = $state<FileList | null>(null);
  let busy = $state(false);
  let uploaded = $state<{ ok: boolean; m: string } | null>(null);
  // The file that came back locked, kept so "Save and retry" can re-post the same bytes
  // instead of asking for it again. save_pdf names by content hash, so a retry is a
  // reparse of one file and not a second statement.
  let retry = $state<{ bank: string; file: File } | null>(null);
  let done = $state(0);

  async function send(e: SubmitEvent) {
    e.preventDefault();
    const file = files?.[0];
    if (!bank || !file) return;
    busy = true;
    uploaded = null;
    const res = await upload(bank, file);
    busy = false;
    if (!res.ok || !res.result) {
      uploaded = say(false, res.error ?? 'Upload failed');
      return;
    }
    const r = res.result;
    uploaded = say(!r.locked && !r.warning, reconLine(r));
    retry = r.locked ? { bank: r.bank, file } : null;
    if (!r.locked) {
      done += 1;
      files = null;
      await loadAppData();      // an empty volume becomes a dashboard right here
    }
  }

  // ---------------------------------------------------------------- 2. passwords
  let pw = $state<Record<string, string>>({});
  let pwSaved = $state('');
  // Pick mode (#95): a first run has no upload to learn a bank from, so it asks. One
  // field, not six — the grid stays a Settings thing.
  let pwBank = $state('');
  const pickKey = $derived(pwBank ? `CC_PW_${pwBank.toUpperCase()}` : '');
  // The backfill names the banks it could not decrypt; start on the first of them.
  $effect(() => {
    const l = bf?.locked?.[0];
    if (l && !pwBank) pwBank = l;
  });
  // Banks with no stored password, for the warning above "Import all past mail". Derived
  // from the booleans /api/settings already returns — no new endpoint (#95).
  const noPw = $derived(cfg.banks.filter((b) => !cfg.secrets[`CC_PW_${b.toUpperCase()}`]));

  async function savePw(b: string, thenRetry = false) {
    const key = `CC_PW_${b.toUpperCase()}`;
    pwSaved = '';
    busy = true;
    const err = await saveSettings({ [key]: pw[b] ?? '' });
    pw[b] = '';
    busy = false;
    if (err) { pwSaved = err; return; }
    pwSaved = `Saved the ${pretty(b)} password.`;
    if (thenRetry && retry) {
      const again = await upload(retry.bank, retry.file);
      if (again.ok && again.result) {
        uploaded = say(!again.result.locked && !again.result.warning, reconLine(again.result));
        if (!again.result.locked) { retry = null; done += 1; await loadAppData(); }
      }
    }
  }

  // ---------------------------------------------------------------- 3. mail
  let gmailUser = $state('');
  let gmailPw = $state('');
  let gmailLabel = $state('');
  let mailMsg = $state<{ ok: boolean; m: string } | null>(null);
  // Fill the non-secret fields once the server has answered. The secret stays blank on
  // purpose — there is nothing to prefill it with, and that is the contract (#40).
  $effect(() => {
    if (cfg.loaded && !gmailUser) gmailUser = cfg.values.GMAIL_USER ?? '';
    if (cfg.loaded && !gmailLabel) gmailLabel = cfg.values.GMAIL_LABEL ?? '';
  });

  async function saveMail(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    mailMsg = null;
    const patch: Record<string, string> = { GMAIL_USER: gmailUser, GMAIL_LABEL: gmailLabel };
    if (gmailPw) patch.GMAIL_APP_PASSWORD = gmailPw;   // blank = leave it alone
    const err = await saveSettings(patch);
    gmailPw = '';
    mailMsg = err ? say(false, err) : await testMail().then((r) => say(r.ok, r.message));
    busy = false;
  }

  // -------------------------------------------------- 3b. backfill the whole label (#91)
  // Unread mail is all the polling loop can see, so a fresh install starts at whatever
  // Gmail happens to have left unread. This reads the label end to end, once.
  let bf = $state<Backfill | null>(null);
  let bfBusy = $state(false);

  function poll(seed: Backfill | null = null) {
    if (seed) bf = seed;
    setTimeout(async () => {
      const b = await backfillStatus();
      if (!b) return poll();          // one dropped poll is not the end of the run
      bf = b;
      if (b.running) return poll();
      bfBusy = false;
      await loadAppData();            // months that just landed, without a reload
    }, 2000);
  }

  async function runBackfill() {
    bfBusy = true;
    bf = null;
    const r = await startBackfill();
    if (!r.ok) { bfBusy = false; mailMsg = say(false, r.message); return; }
    poll();
  }

  // ---------------------------------------------------------------- 4. reminders
  let tgToken = $state('');
  let tgChat = $state('');
  let remindMsg = $state<{ ok: boolean; m: string } | null>(null);
  $effect(() => {
    if (cfg.loaded && !tgChat) tgChat = cfg.values.TELEGRAM_CHAT_ID ?? '';
  });

  async function saveTelegram(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    remindMsg = null;
    const patch: Record<string, string> = { TELEGRAM_CHAT_ID: tgChat };
    if (tgToken) patch.TELEGRAM_BOT_TOKEN = tgToken;
    const err = await saveSettings(patch);
    tgToken = '';
    busy = false;
    remindMsg = err ? say(false, err) : say(true, 'Saved.');
  }

  async function sendTest() {
    busy = true;
    remindMsg = null;
    const r = await testReminder();
    busy = false;
    remindMsg = say(r.ok, r.message);
  }

  // ---------------------------------------------------------------- 5. categories (#82)
  // Only ever shown from Settings: on an empty volume there is no app.json, so there is
  // nothing that fell through into `Other` to ask about.
  let catMsg = $state<{ ok: boolean; m: string } | null>(null);

  async function saveCat(merchant: string, category: string) {
    busy = true;
    catMsg = null;
    const ok = await cats.set(merchant, category);
    busy = false;
    if (!ok) { catMsg = say(false, `Could not save ${merchant}.`); return; }
    catMsg = say(true, category ? `${merchant} is now ${category}.` : `${merchant} is back in Other.`);
    // The server re-ran the pipeline before answering, so the new categories — and the
    // shorter unknown list — are already on the volume. Pick them up.
    await loadAppData();
  }

  const FIELD = 'w-full border px-2 py-1.5 text-sm';
  const FIELD_STYLE = 'background:var(--surface2);color:var(--text);border-color:var(--divider2)';
  const BTN = 'border px-3 py-1.5 text-xs font-bold uppercase tracking-wide';
  const BTN_STYLE = 'background:var(--surface2);color:var(--text);border-color:var(--divider2)';
</script>

{#snippet lock(name: string)}
  {#if isLocked(name)}
    <span class="text-[11px] uppercase tracking-wide" style="color:var(--accent)"
      >Locked — set by the environment</span
    >
  {/if}
{/snippet}

{#snippet result(r: { ok: boolean; m: string } | null)}
  {#if r}
    <p class="mt-2 text-xs" style="color:{r.ok ? 'var(--ok)' : '#f87171'}" role="status">{r.m}</p>
  {/if}
{/snippet}

<!-- #87: the shell owns the content width, so /settings lines up with the dashboard.
     The first-run mount is rendered by +layout with no shell around it, and keeps its own. -->
<main class="py-8 {first ? 'mx-auto max-w-xl px-4' : ''}">
  <header class="mb-6">
    <h1 class="text-lg font-extrabold tracking-tight">
      {first ? 'Nothing here yet' : 'Settings'}
    </h1>
    <p class="mt-1 text-sm" style="color:var(--muted)">
      {first
        ? 'Upload one credit-card statement and this becomes a dashboard. Everything below that is optional and can wait.'
        : 'Anything set in the environment wins and cannot be edited here.'}
    </p>
  </header>

  <!-- Lives here, not on the /settings route (#74): on an empty volume +layout renders
       <Setup first> directly and the settings page never mounts, so the old banner was
       absent during first run — the exact moment someone is standing at a fresh
       deployment. `unauthenticated` wins when both are somehow true: no password is the
       worse of the two, and only one alert is worth reading. -->
  {#if cfg.unauthenticated}
    <p class="mb-6 border p-3 text-sm" style="border-color:var(--over);color:var(--over)" role="alert">
      <strong>This app has no password.</strong> Anyone who can reach it can upload statements,
      read your spending, and overwrite your mail and reminder credentials. Set
      <code>APP_PASSWORD</code> in your <code>.env</code> and restart.
    </p>
  {:else if cfg.default_password}
    <p class="mb-6 border p-3 text-sm" style="border-color:var(--over);color:var(--over)" role="alert">
      <strong>Change your password.</strong> This app is still using the placeholder
      <code>changeme@123</code> that ships in <code>.env.example</code> — it is in a public repo,
      so it is not a secret. Set <code>APP_PASSWORD</code> in your <code>.env</code> to something
      only you know and restart.
    </p>
  {/if}

  <!-- 1 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s1">
    <h2 id="s1" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      1 · Add a statement
    </h2>
    <form class="mt-3 flex flex-col gap-3" onsubmit={send}>
      <div>
        <label class="mb-1 block text-xs" for="setup-bank" style="color:var(--muted)"
          >Which bank sent it?</label
        >
        <!-- No default, ever. `bank` is permanent: it picks the PDF password and the
             parser branch, and parse.py re-derives it from the stored filename on every
             later run. A wrong-but-valid guess misparses forever (#31). -->
        <select id="setup-bank" bind:value={bank} required class={FIELD} style={FIELD_STYLE}>
          <option value="" disabled>Choose a bank…</option>
          {#each cfg.banks as b (b)}<option value={b}>{pretty(b)}</option>{/each}
        </select>
      </div>
      <div>
        <label class="mb-1 block text-xs" for="setup-file" style="color:var(--muted)"
          >The PDF, straight out of the email</label
        >
        <input
          id="setup-file"
          type="file"
          accept="application/pdf,.pdf"
          bind:files
          required
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div class="flex items-center gap-3">
        <button type="submit" disabled={busy || !bank || !files?.length} class={BTN} style={BTN_STYLE}>
          {busy ? 'Reading…' : 'Upload'}
        </button>
        <span class="text-[11px]" style="color:var(--muted)">
          It stays on your volume — nothing is sent anywhere else.
        </span>
      </div>
    </form>
    {@render result(uploaded)}
    {#if done > 0}
      <p class="mt-2 text-xs" style="color:var(--muted)">
        {done} uploaded this session. <a href="{base || '/'}" class="underline">Go to the dashboard</a> — or add
        another above.
      </p>
    {/if}
  </section>

  <!-- 2 ---------------------------------------------------------------- -->
  <!-- Three modes, one section (#95). retry: a real file came back locked. pick: a first
       run, which used to hide this entirely — leaving no way to set a password before
       the import, so 15 statements failed to decrypt and still reported success. all:
       Settings, where you came looking for it. Pick mode is one field on purpose: an
       unprompted grid of six password boxes is the terminal experience we deleted. -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s2">
    <h2 id="s2" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      2 · Statement passwords
    </h2>
    {#if retry}
      <p class="mt-2 text-sm">
        That {pretty(retry.bank)} statement is password-protected. The covering email says what the
        password is — usually your IC or date of birth.
      </p>
      <div class="mt-3 flex flex-col gap-2">
        <label class="text-xs" for="pw-retry" style="color:var(--muted)"
          >{pretty(retry.bank)} PDF password</label
        >
        <input
          id="pw-retry"
          type="password"
          autocomplete="off"
          bind:value={pw[retry.bank]}
          class={FIELD}
          style={FIELD_STYLE}
        />
        <div>
          <button
            type="button"
            disabled={busy || !pw[retry.bank]}
            class={BTN}
            style={BTN_STYLE}
            onclick={() => savePw(retry!.bank, true)}>Save and retry</button
          >
        </div>
      </div>
    {:else if first}
      <p class="mt-2 text-sm">
        Most banks lock the PDF they email you. The covering email says what the password is —
        usually your IC or date of birth. Set the ones you have; you can come back for the rest.
      </p>
      <div class="mt-3 flex flex-col gap-2">
        <label class="text-xs" for="pw-bank" style="color:var(--muted)">Which bank?</label>
        <select id="pw-bank" bind:value={pwBank} class={FIELD} style={FIELD_STYLE}>
          <option value="" disabled>Choose a bank…</option>
          {#each cfg.banks as b (b)}
            <option value={b}>{pretty(b)}{cfg.secrets[`CC_PW_${b.toUpperCase()}`] ? ' · set' : ''}</option>
          {/each}
        </select>
        <label class="text-xs" for="pw-pick" style="color:var(--muted)">
          PDF password {@render lock(pickKey)}
        </label>
        <input
          id="pw-pick"
          type="password"
          autocomplete="off"
          disabled={!pwBank || isLocked(pickKey)}
          bind:value={pw[pwBank]}
          class={FIELD}
          style={FIELD_STYLE}
        />
        <div>
          <button
            type="button"
            disabled={busy || !pwBank || isLocked(pickKey) || !pw[pwBank]}
            class={BTN}
            style={BTN_STYLE}
            onclick={() => savePw(pwBank)}>Save</button
          >
        </div>
      </div>
    {:else}
      <p class="mt-2 text-xs" style="color:var(--muted)">
        Stored once per bank and reused for every statement it sends. Leave a box empty to keep
        what is already there.
      </p>
      <div class="mt-3 flex flex-col gap-3">
        {#each cfg.banks as b (b)}
          {@const key = `CC_PW_${b.toUpperCase()}`}
          <div class="flex items-end gap-2">
            <div class="flex-1">
              <label class="mb-1 block text-xs" for={'pw-' + b} style="color:var(--muted)">
                {pretty(b)}
                {#if cfg.secrets[key]}<span style="color:var(--ok)">· set</span>{:else}<span
                    >· not set</span
                  >{/if}
                {@render lock(key)}
              </label>
              <input
                id={'pw-' + b}
                type="password"
                autocomplete="off"
                disabled={isLocked(key)}
                bind:value={pw[b]}
                class={FIELD}
                style={FIELD_STYLE}
              />
            </div>
            <button
              type="button"
              disabled={busy || isLocked(key) || !pw[b]}
              class={BTN}
              style={BTN_STYLE}
              onclick={() => savePw(b)}>Save</button
            >
          </div>
        {/each}
      </div>
    {/if}
    <p class="mt-3 text-[11px]" style="color:var(--muted)">
      Set these here, or as <code>CC_PW_*</code> in <code>.env</code> if you run your own stack.
      Env wins and greys the box out.
    </p>
    {#if pwSaved}<p class="mt-2 text-xs" style="color:var(--muted)" role="status">{pwSaved}</p>{/if}
  </section>

  <!-- 3 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s3">
    <h2 id="s3" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      3 · Fetch statements from Gmail <span style="color:var(--divider2)">(optional)</span>
    </h2>
    <p class="mt-2 text-xs" style="color:var(--muted)">
      Label the statement mail <code>CC</code> in Gmail and this checks for new ones every hour, so
      you never upload another by hand. Needs an app password, not your Google password —
      <a href={APP_PW_URL} target="_blank" rel="noreferrer" class="underline">make one here</a>.
    </p>
    <form class="mt-3 flex flex-col gap-3" onsubmit={saveMail}>
      <div>
        <label class="mb-1 block text-xs" for="gmail-user" style="color:var(--muted)"
          >Gmail address {@render lock('GMAIL_USER')}</label
        >
        <input
          id="gmail-user"
          type="email"
          autocomplete="username"
          disabled={isLocked('GMAIL_USER')}
          bind:value={gmailUser}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div>
        <label class="mb-1 block text-xs" for="gmail-pw" style="color:var(--muted)">
          App password
          {#if cfg.secrets.GMAIL_APP_PASSWORD}<span style="color:var(--ok)">· set</span>{/if}
          {@render lock('GMAIL_APP_PASSWORD')}
        </label>
        <input
          id="gmail-pw"
          type="password"
          autocomplete="off"
          placeholder={cfg.secrets.GMAIL_APP_PASSWORD ? 'unchanged' : ''}
          disabled={isLocked('GMAIL_APP_PASSWORD')}
          bind:value={gmailPw}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      <div>
        <label class="mb-1 block text-xs" for="gmail-label" style="color:var(--muted)"
          >Label {@render lock('GMAIL_LABEL')}</label
        >
        <input
          id="gmail-label"
          type="text"
          placeholder="CC"
          disabled={isLocked('GMAIL_LABEL')}
          bind:value={gmailLabel}
          class={FIELD}
          style={FIELD_STYLE}
        />
      </div>
      {#if noPw.length}
        <p class="text-xs" style="color:var(--over)" role="status">
          No password set for {noPw.map(pretty).join(', ')}. Password-protected statements from
          those will fail to parse.
        </p>
      {/if}
      <div class="flex flex-wrap gap-2">
        <button type="submit" disabled={busy} class={BTN} style={BTN_STYLE}>
          {busy ? 'Connecting…' : 'Save and test connection'}
        </button>
        <button
          type="button"
          disabled={busy || bfBusy}
          onclick={runBackfill}
          class={BTN}
          style={BTN_STYLE}
        >
          {bfBusy ? 'Importing…' : 'Import all past mail'}
        </button>
      </div>
    </form>
    {@render result(mailMsg)}
    <p class="mt-2 text-xs" style="color:var(--muted)">
      From here on only unread mail is picked up. Import reads the whole label once, so
      statements you have already opened come in too. It leaves every mail unread, takes
      a few minutes, and keeps going if you close this page.
    </p>
    {#if bf}{@render result(say(!bf.error && !bf.failed, backfillLine(bf)))}{/if}
  </section>

  <!-- 4 ---------------------------------------------------------------- -->
  <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s4">
    <h2 id="s4" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      4 · Bill reminders <span style="color:var(--divider2)">(optional)</span>
    </h2>
    <p class="mt-2 text-xs" style="color:var(--muted)">
      One notification per bill, a few days before it is due.
    </p>

    <div class="mt-3 flex items-center gap-3">
      {#if push.status === 'off' || push.status === 'on' || push.status === 'busy'}
        <button
          type="button"
          class={BTN}
          style={BTN_STYLE}
          aria-pressed={push.status === 'on'}
          disabled={push.status === 'busy'}
          onclick={() => togglePush()}
        >
          {push.status === 'busy'
            ? '…'
            : push.status === 'on'
              ? 'Notifications on'
              : 'Turn on notifications'}
        </button>
      {/if}
      <span class="text-[11px]" style="color:var(--muted)">
        {push.note || 'Nothing to configure — your browser handles it.'}
      </span>
    </div>

    <details class="mt-4">
      <summary class="cursor-pointer text-xs" style="color:var(--muted)">
        Use Telegram instead (or as well)
      </summary>
      <form class="mt-3 flex flex-col gap-3" onsubmit={saveTelegram}>
        <div>
          <label class="mb-1 block text-xs" for="tg-token" style="color:var(--muted)">
            Bot token
            {#if cfg.secrets.TELEGRAM_BOT_TOKEN}<span style="color:var(--ok)">· set</span>{/if}
            {@render lock('TELEGRAM_BOT_TOKEN')}
          </label>
          <input
            id="tg-token"
            type="password"
            autocomplete="off"
            placeholder={cfg.secrets.TELEGRAM_BOT_TOKEN ? 'unchanged' : ''}
            disabled={isLocked('TELEGRAM_BOT_TOKEN')}
            bind:value={tgToken}
            class={FIELD}
            style={FIELD_STYLE}
          />
        </div>
        <div>
          <label class="mb-1 block text-xs" for="tg-chat" style="color:var(--muted)"
            >Chat ID {@render lock('TELEGRAM_CHAT_ID')}</label
          >
          <input
            id="tg-chat"
            type="text"
            disabled={isLocked('TELEGRAM_CHAT_ID')}
            bind:value={tgChat}
            class={FIELD}
            style={FIELD_STYLE}
          />
        </div>
        <p class="text-[11px]" style="color:var(--muted)">
          Message the bot once from that chat first — Telegram will not let a bot speak first.
        </p>
        <div><button type="submit" disabled={busy} class={BTN} style={BTN_STYLE}>Save</button></div>
      </form>
    </details>

    <div class="mt-4">
      <button type="button" disabled={busy} class={BTN} style={BTN_STYLE} onclick={sendTest}
        >Send test message</button
      >
    </div>
    {@render result(remindMsg)}
  </section>

  <!-- 5 ---------------------------------------------------------------- -->
  {#if !first && app.other.length}
    <section class="mb-5 border p-4" style="border-color:var(--divider)" aria-labelledby="s5">
      <h2 id="s5" class="text-xs uppercase tracking-widest" style="color:var(--muted)">
        5 · Unknown merchants <span style="color:var(--divider2)">(optional)</span>
      </h2>
      <p class="mt-2 text-xs" style="color:var(--muted)">
        These did not match anything, so they are sitting in <code>Other</code>. Pick a category
        and it sticks — for every statement, past and future. Biggest spend first.
      </p>
      <div class="mt-3 flex flex-col gap-3">
        {#each app.other as o, i (o.m)}
          <div>
            <label class="mb-1 block text-xs" for={'cat-' + i} style="color:var(--muted)">
              {o.m}
              <span style="color:var(--divider2)">· {o.n}× · RM {o.rm.toFixed(2)}</span>
            </label>
            <select
              id={'cat-' + i}
              disabled={busy}
              class={FIELD}
              style={FIELD_STYLE}
              value={cats.category(o.m)}
              onchange={(e) => saveCat(o.m, e.currentTarget.value)}
            >
              <option value="">Leave it in Other</option>
              {#each app.allCats as c (c)}<option value={c}>{c}</option>{/each}
            </select>
          </div>
        {/each}
      </div>
      {@render result(catMsg)}
    </section>
  {/if}

  {#if first}
    <p class="text-xs" style="color:var(--muted)">
      Steps 2 to 4 are all optional and all live at
      <a href="{base}/settings" class="underline">Settings</a> afterwards.
    </p>
  {:else}
    <p class="text-xs"><a href="{base || '/'}" class="underline">Back to the dashboard</a></p>
  {/if}
</main>
