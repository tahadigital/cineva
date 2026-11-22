'use strict';
// Presentation only: no playback, account or navigation state is changed here.
(() => {
  const introKey = 'mavie:launch:v1';
  const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const launchDuration = 720;
  const fadeDuration = 180;
  const animations = new Set();
  const observed = new Set();
  const seen = new WeakSet();
  let intro = null, introTimer = null, removalTimer = null, safetyTimer = null;
  let navigationEntrance = true, launched = false, scheduled = false, intersection = null;
  const reduced = () => motion?.matches === true;
  function removeIntro() {
    clearTimeout(introTimer); clearTimeout(removalTimer); clearTimeout(safetyTimer);
    if (intro) { intro.hidden = true; intro.remove(); intro = null; scheduleScan(); }
  }
  function finishIntro(immediate = false) {
    if (!intro) return;
    clearTimeout(introTimer);
    if (immediate || reduced() || document.hidden) { removeIntro(); return; }
    intro.classList.add('is-leaving');
    removalTimer = setTimeout(removeIntro, fadeDuration);
  }
  function startIntro() {
    intro = document.getElementById('mavieLaunch');
    if (!intro) return;
    let played = false;
    try { played = sessionStorage.getItem(introKey) === '1'; sessionStorage.setItem(introKey, '1'); } catch {}
    if (played || reduced() || document.hidden) { removeIntro(); return; }
    launched = true;
    intro.hidden = false;
    intro.classList.add('is-active');
    introTimer = setTimeout(() => finishIntro(), launchDuration);
    // A failed transition event or interrupted animation cannot strand a cover.
    safetyTimer = setTimeout(removeIntro, launchDuration + fadeDuration + 100);
  }
  function enter(element, index = 0) {
    if (reduced() || document.hidden || !element.isConnected || !element.animate) return;
    const animation = element.animate([
      {opacity: 0, transform: 'translate3d(0,12px,0)'},
      {opacity: 1, transform: 'translate3d(0,0,0)'},
    ], {duration: 330, delay: Math.min(index * 22, 154), easing: 'cubic-bezier(0.22, 1.25, 0.36, 1)', fill: 'backwards'});
    animations.add(animation);
    animation.finished.catch(() => {}).finally(() => animations.delete(animation));
  }
  function updateRail(rail) {
    const maxScroll = rail.scrollWidth - rail.clientWidth;
    const previous = rail.parentElement?.querySelector('.rail-prev');
    const next = rail.parentElement?.querySelector('.rail-next');
    if (previous) previous.hidden = rail.scrollLeft < 2;
    if (next) next.hidden = maxScroll - rail.scrollLeft < 2;
  }
  function updateRails() {
    document.querySelectorAll?.('.rail-strip').forEach(updateRail);
  }
  function scan() {
    scheduled = false;
    const main = document.getElementById('main');
    updateRails();
    for (const element of observed) {
      if (!element.isConnected) { intersection?.unobserve(element); observed.delete(element); }
    }
    if (!main || !navigationEntrance || intro || main.querySelector('.loading-grid,.initial-loading')) return;
    navigationEntrance = false;
    const revealFromIntro = launched;
    launched = false;
    if (reduced() || document.hidden) return;
    const candidates = main.querySelectorAll(
      '.hero,.page-heading,.cinema-rail,.media-card:not(.cinema-rail *),.resume-card:not(.cinema-rail *),.live-card:not(.cinema-rail *),.playlist-card,.empty-state,.panel'
    );
    let visibleIndex = 0;
    for (const element of candidates) {
      if (seen.has(element)) continue;
      seen.add(element);
      if (revealFromIntro && element.matches?.('.cinema-hero, .cinema-rail')) continue;
      if (intersection) { observed.add(element); intersection.observe(element); }
      else if (visibleIndex < 12) enter(element, visibleIndex++);
    }
  }
  function scheduleScan() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(scan);
  }
  function boot() {
    startIntro();
    if ('IntersectionObserver' in window) intersection = new IntersectionObserver(entries => {
      let index = 0;
      for (const entry of entries) if (entry.isIntersecting) {
        intersection.unobserve(entry.target); observed.delete(entry.target);
        enter(entry.target, index++);
      }
    }, {threshold: .06, rootMargin: '20px'});
    const main = document.getElementById('main');
    if (main) new MutationObserver(scheduleScan).observe(main, {childList: true, subtree: false});
    const topbar = document.querySelector?.('.topbar');
    function updateHeader() { topbar?.classList.toggle('is-scrolled', window.scrollY > 32); }
    document.addEventListener('scroll', event => {
      if (event.target?.classList?.contains('rail-strip')) updateRail(event.target);
      else if (event.target === document) updateHeader();
    }, {capture: true, passive: true});
    window.addEventListener('resize', updateRails, {passive: true});
    updateHeader();
    document.addEventListener('click', event => {
      const button = event.target.closest?.('[data-rail-step]');
      if (button) {
        const rail = button.parentElement.querySelector('.rail-strip');
        const cardWidth = rail.firstElementChild?.getBoundingClientRect().width || 0;
        const gap = parseFloat(getComputedStyle(rail).columnGap) || 0;
        const pitch = cardWidth + gap;
        const page = pitch > 0 ? Math.max(1, Math.floor(rail.clientWidth / pitch)) * pitch : rail.clientWidth;
        rail.scrollBy({left: Number(button.dataset.railStep) * page, behavior: reduced() ? 'instant' : 'smooth'});
      } else if (event.target.closest?.('[data-focus-search]')) {
        document.getElementById('searchInput')?.focus();
      }
    });
    window.addEventListener('hashchange', () => { navigationEntrance = true; scheduleScan(); });
    document.addEventListener('visibilitychange', () => { if (document.hidden) finishIntro(true); });
    const motionChanged = () => {
      if (!reduced()) return;
      finishIntro(true);
      for (const animation of animations) animation.cancel();
      animations.clear();
      for (const element of observed) intersection?.unobserve(element);
      observed.clear();
    };
    if (motion?.addEventListener) motion.addEventListener('change', motionChanged);
    else motion?.addListener?.(motionChanged);
    window.addEventListener('pagehide', () => { removeIntro(); for (const animation of animations) animation.cancel(); animations.clear(); });
    scheduleScan();
  }
  window.MavieExperience = {finishIntro: () => finishIntro(true), version: 3};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
