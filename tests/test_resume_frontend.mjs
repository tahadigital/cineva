import assert from 'node:assert/strict';
import test from 'node:test';
import {harness} from './playback_harness.mjs';

test('resume card opens the selected episode and identifies the season and episode',()=>{
  const h=harness();
  const html=h.resumeCard({id:'episode:8',kind:'episode',name:'Gibi S01E08',seriesName:'Gibi',season:1,episode:8,progress:{position:120,duration:1800}});
  assert.match(html,/data-action="play" data-id="episode:8"/);
  assert.match(html,/<strong>Gibi<\/strong>/);
  assert.match(html,/1\. Sezon · 8\. Bölüm/);
  assert.match(html,/2:00 izlendi/);
});

test('the next episode card explicitly offers continuation without a false watched label',()=>{
  const h=harness();
  const html=h.resumeCard({id:'episode:9',kind:'episode',name:'Gibi S02E01',seriesName:'Gibi',season:2,episode:1,continueReason:'nextEpisode',progress:null});
  assert.match(html,/data-id="episode:9"/);
  assert.match(html,/Sonraki bölümden devam et · 2\. Sezon · 1\. Bölüm/);
  assert.doesNotMatch(html,/izlendi|progress-track/);
});

test('empty, confirmDialog, section, and empty library views render without ReferenceError or duplicate subtitles',()=>{
  const h=harness();
  const emptyHtml=h.empty('Sevdiklerini bir araya getir','Bir afişteki kalbe dokun.','heart');
  assert.match(emptyHtml,/<h2>Sevdiklerini bir araya getir<\/h2>/);
  assert.match(emptyHtml,/<p>Bir afişteki kalbe dokun\.<\/p>/);

  const sectionHtml=h.section('Öne Çıkanlar',[{id:'vod:1',kind:'vod',name:'Test Film'}],'vod','vod','Senin için seçildi');
  assert.equal((sectionHtml.match(/class="discovery-subtitle"/g)||[]).length,1);

  h.renderFavorites([]);
  assert.match(h.element('#main').innerHTML,/Kalbini kazananlar burada/);

  h.state.route='playlists';
  h.state.playlists=[];
  h.renderPlaylists();
  assert.match(h.element('#main').innerHTML,/İlk listenin bir adı olsun\./);

  h.confirmDialog('Listeyi sil?','Bu işlem geri alınamaz.',()=>{},'Sil');
  assert.match(h.element('#listContent').innerHTML,/<h2>Listeyi sil\?<\/h2>/);
  assert.match(h.element('#listContent').innerHTML,/<p>Bu işlem geri alınamaz\.<\/p>/);
});
