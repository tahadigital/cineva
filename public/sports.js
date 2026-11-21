'use strict';
window.MavieSports = (() => {
  const zone = 'Europe/Istanbul';
  const days = new Intl.DateTimeFormat('tr-TR', {weekday:'short', day:'numeric', month:'short', timeZone:'UTC'});
  const dates = new Intl.DateTimeFormat('en-CA', {year:'numeric',month:'2-digit',day:'2-digit',timeZone:zone});
  const clock = new Intl.DateTimeFormat('tr-TR', {hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:zone});

  function localDate(now = new Date()) {
    const parts = Object.fromEntries(dates.formatToParts(now).map(({type,value}) => [type,value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  function range(today) {
    const midnight = Date.parse(today + 'T00:00:00Z');
    return Array.from({length:10}, (_,index) => {
      const date = new Date(midnight + (index - 1) * 86400000);
      const id = date.toISOString().slice(0,10);
      return {id, label:index === 0 ? 'Dün' : index === 1 ? 'Bugün' : index === 2 ? 'Yarın' : days.format(date)};
    });
  }

  const searchable = text => String(text).toLocaleLowerCase('tr-TR').normalize('NFD')
    .replace(/\p{M}/gu, '').replace(/ı/g, 'i');

  function spotlight(events, selected, today, now = new Date()) {
    if (selected < today) return null;
    const cutoff = clock.format(new Date(now.getTime() - 120 * 60000));
    const current = clock.format(now);
    const relevant = selected === today ? events.filter(event => event.time >= (cutoff <= current ? cutoff : '00:00')) : events;
    const rank = event => Number(event.featured);
    return relevant.reduce((best,event) => !best || rank(event) > rank(best) ? event : best,null);
  }

  function broadcastButtons(event, channels) {
    return event.channels.map(label => {
      const match = Object.hasOwn(channels,label) ? channels[label] : null;
      return match ? `<button type="button" class="sports-channel playable" data-action="play"
        data-id="${esc(match.id)}" aria-label="${esc(event.title)} · ${esc(label)} kanalını aç">${icon('play')}${esc(label)}</button>`
        : `<span class="sports-channel missing" title="Bu kanal IPTV listende bulunamadı">${esc(label)}<small>Listende yok</small></span>`;
    }).join('');
  }

  function program(event, channels) {
    return `<li class="sports-event">
      <time>${esc(event.time)}</time><div class="sports-event-text"><small>${esc(event.sport)}${event.league ? ' · '+esc(event.league) : ''}</small>
      <h3>${esc(event.title)}</h3></div><div class="sports-channels">${broadcastButtons(event,channels)}</div>
    </li>`;
  }

  async function render(main, params, current, force = false) {
    const today = localDate();
    const availableDays = range(today);
    const selected = availableDays.some(day => day.id === params.get('date')) ? params.get('date') : today;
    const reqSource = ['sporekrani', 'xmltv'].includes(params.get('source')) ? params.get('source') : 'auto';
    const sourceSuffix = reqSource !== 'auto' ? `&source=${encodeURIComponent(reqSource)}` : '';

    main.innerHTML = `<div class="sports-page">
      <header class="sports-intro"><span class="sports-kicker">${icon('sports')} MAVIE SPOR EKRANI</span>
        <h1>Spor Ekranı & Yayın Rehberi</h1><p>Türkiye saatine göre günün maçları, yarışları ve eşleşen IPTV kanalları.</p>
      </header>
      <nav aria-label="Yayın günü" class="sports-dates">${availableDays.map(day => `<a href="#sports?date=${day.id}${sourceSuffix}"
        ${selected === day.id ? 'aria-current="date"' : ''}>${esc(day.label)}</a>`).join('')}</nav>
      <div class="sports-body" aria-live="polite"><div class="sports-status"><span class="spinner"></span> Spor yayın akışı yükleniyor…</div></div>
    </div>`;
    const body = main.querySelector('.sports-body');
    let guide;
    try {
      const query = new URLSearchParams({
        date: selected,
        ...(reqSource !== 'auto' ? {source: reqSource} : {}),
        ...(force ? {refresh: '1'} : {}),
      });
      guide = await api(`/api/sports?${query}`);
    } catch (error) {
      if (!current()) return;
      body.innerHTML = `<div class="sports-status"><p>${esc(error.message)}</p>
        <button type="button" class="button secondary">Tekrar dene</button></div>`;
      body.querySelector('button').onclick = () => render(main,params,current,true);
      return;
    }
    if (!current()) return;
    const {events, channels} = guide;
    const activeSource = guide.sourceType || 'sporekrani';
    remember(Object.values(channels));
    const sports = [...new Set(events.map(event => event.sport))].sort((a,b) => a.localeCompare(b,'tr'));
    const hero = spotlight(events,selected,today);
    const sourceSwitch = guide.hasEpg
      ? `<div class="sports-tabs" aria-label="Rehber kaynağı" style="margin-bottom:12px;">
          <a class="button small ${activeSource === 'sporekrani' ? '' : 'secondary'}" href="#sports?date=${selected}&source=sporekrani">Spor Ekranı</a>
          <a class="button small ${activeSource === 'xmltv' ? '' : 'secondary'}" href="#sports?date=${selected}&source=xmltv">XMLTV EPG</a>
        </div>`
      : '';
    const sourceFooter = activeSource === 'xmltv'
      ? (guide.configured ? 'Yayın bilgileri · Kullanıcının XMLTV EPG kaynağı' : 'Ayarlar bölümünden kendi XMLTV (.xml / .xml.gz) rehber adresini ekleyebilirsin.')
      : 'Yayın bilgileri · Spor Ekranı (Türkiye saati · Europe/Istanbul) · Kanala tıklayıp IPTV’den anında izle';

    body.innerHTML = `${sourceSwitch}${guide.stale ? '<p class="sports-stale">Son alınan yayın akışı gösteriliyor.</p>' : ''}
      ${hero ? `<article class="sports-spotlight">
        <div><span class="sports-kicker">ÖNE ÇIKAN KARŞILAŞMA</span><h2>${esc(hero.title)}</h2>
        <p>${esc(hero.time)} · ${esc(hero.league || hero.sport)}</p>
        <div class="sports-channels">${broadcastButtons(hero,channels)}</div></div>
      </article>` : ''}
      <section class="sports-program" aria-labelledby="sports-program-heading">
        <div class="sports-program-heading"><h2 id="sports-program-heading">Yayın Akışı</h2>
        <button class="text-button sports-refresh" type="button">${icon('refresh')} Yenile</button></div>
        ${events.length ? `<div class="sports-filter">
          <label class="sports-search">${icon('search')}<input type="search" aria-label="Maç, takım veya kanal ara" placeholder="Maç, takım veya kanal ara"></label>
          <div class="sports-tabs" aria-label="Spor türü"><button type="button" aria-pressed="true">Tümü</button>
          ${sports.map(sport => `<button type="button" data-sport="${esc(sport)}" aria-pressed="false">${esc(sport)}</button>`).join('')}</div>
        </div>` : ''}
        <ul class="sports-events"></ul><p class="sports-status sports-empty" hidden></p>
        <p class="sports-source">${sourceFooter}</p>
      </section>`;
    body.querySelector('.sports-refresh').onclick = () => render(main,params,current,true);
    const search = body.querySelector('input');
    const list = body.querySelector('.sports-events');
    const empty = body.querySelector('.sports-empty');
    let sport = '';
    function filter() {
      const query = searchable(search?.value.trim() || '');
      const results = events.filter(event => (!sport || event.sport === sport) &&
        (!query || searchable([event.title,event.league,event.sport,...event.channels].join(' ')).includes(query)));
      list.innerHTML = results.map(event => program(event,channels)).join('');
      empty.hidden = !!results.length;
      empty.textContent = !guide.configured
        ? 'Henüz bir XMLTV yayın rehberi (EPG) adresi bağlanmadı. Ayarlar bölümünden M3U veya EPG URL ekleyebilirsin.'
        : (events.length ? 'Bu filtreye uyan yayın yok.' : 'Bu gün için yayın bilgisi listelenmiyor.');
    }
    search?.addEventListener('input',filter);
    const tabs = [...body.querySelectorAll('.sports-tabs button')];
    for (const tab of tabs) tab.onclick = () => {
      sport = tab.dataset.sport || '';
      tabs.forEach(item => item.setAttribute('aria-pressed', String(item === tab)));
      filter();
    };
    filter();
  }
  return {render};
})();
