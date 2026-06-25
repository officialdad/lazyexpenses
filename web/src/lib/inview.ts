/** Svelte action: add `.in-view` to the node the first time it scrolls into the viewport,
 *  then stop observing. Used to defer chart entrance animations (see app.css `.in-view …`)
 *  until the chart is actually visible, for a more natural scroll-driven reveal.
 *  rootMargin trims 12% off the bottom so it fires as the card clearly enters, not at 1px. */
export function inview(node: HTMLElement) {
  const io = new IntersectionObserver(
    (entries, obs) => {
      if (entries[0].isIntersecting) {
        node.classList.add('in-view');
        obs.disconnect();
      }
    },
    { rootMargin: '0px 0px -12% 0px' }
  );
  io.observe(node);
  return { destroy: () => io.disconnect() };
}
