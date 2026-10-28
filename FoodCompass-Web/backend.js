'use strict';
// Same-origin backend integration; ?demo keeps the original standalone experience.
const backendEnabled = location.protocol !== 'file:' && !new URLSearchParams(location.search).has('demo');
const backendState = {session:null, signature:'', probes:[], choices:new Map(), ranked:[], busy:false, error:''};
const profilePayload = () => ({language:S.language, restrictions:[...new Set(S.avoid)], cuisines:S.flavours, goals:S.goals});
async function backendPost(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`Backend returned HTTP ${response.status}. Check the server log and retry.`); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Invalid API request');
  return data;
}
let monitorSyncQueue = Promise.resolve();
function backendSync(body) {
  // Keep rapid Continue / Undo events in the same order as the user's actions.
  monitorSyncQueue = monitorSyncQueue.then(() => backendPost('/api/live-sync', body)).catch(() => {});
  return monitorSyncQueue;
}
function syncProbeChoices() {
  const swipes = backendState.probes.filter(d => backendState.choices.has(d.id)).map(d => ({
    dish_id:d.id, name:d.name, category:d.probe_category, liked:backendState.choices.get(d.id)
  }));
  return backendSync({event_type:'swipe_snapshot', page:5, swipes});
}
function syncVisibleFilters() {
  if (!backendState.ranked.length || mode === 'group') return;
  const prices = backendState.ranked.map(d => d.price);
  const bounds = {'£0–5':[0,5],'£5–10':[5,10],'£10–20':[10,20],'£20+':[20,Math.max(20,...prices)]};
  const [min,max] = bounds[S.filters.budget] || [Math.min(...prices),Math.max(...prices)];
  backendSync({event_type:'price_slider',price_filter:{min,max,visible_count:available().length}});
}
const goBeforeMonitorSync = go;
go = function(nextRoute) {
  goBeforeMonitorSync(nextRoute);
  if (!backendEnabled || mode === 'group') return;
  const page = nextRoute === 'onboard' ? step+1 : ['results','wheel'].includes(nextRoute) ? 6 : ['passport','explore'].includes(nextRoute) ? 5 : null;
  if (page !== null) backendSync({event_type:'page_step',page});
  if (['results','wheel','explore'].includes(nextRoute)) syncVisibleFilters();
};
function backendFood(d) {
  const ingredients = d.ingredients || [];
  const text = ingredients.join(' ').toLowerCase();
  const meat = /beef|pork|chicken|duck|lamb|bacon|sausage|fish|salmon|cod|shrimp|clams|sea bass|seafood/.test(text);
  return {id:'api-'+d.id, backendId:d.id, name:d.name, cuisine:d.cuisine,
    venue:'Backend sample dataset', image:d.image || 'dish-placeholder.svg', imageNote:d.image_note || 'Illustrative image', price:d.price,
    distance:Math.round((d.distance_km || 0)*1000), rating:d.rating, reviews:'sample',
    ingredients, allergens:[], meat, vegan:!meat && !/egg|milk|cream|butter|cheese|yogurt|paneer/.test(text),
    hot:!['Raw','Chilled'].includes(d.cooking_method), calories:d.calories, protein:d.protein_g,
    carbs:'—', fat:'—', tags:[d.cooking_method], dining:['Dine-in','Takeaway'],
    description:d.evaluation ? 'Consensus score: '+d.evaluation.consensus_ranking_score+' · '+d.evaluation.ranking_formula : d.probe_category,
    evaluation:d.evaluation};
}
function installBackendFoods(dishes) {
  dishes.forEach(d => {
    const f = backendFood(d), i = foods.findIndex(x => x.id === f.id);
    if (i >= 0) foods[i] = f; else foods.push(f);
  });
}
async function startBackend() {
  if (backendState.busy) return;
  backendState.busy = true; backendState.error = ''; render();
  try {
    await backendSync({event_type:'probe_reset',page:5});
    const payload = profilePayload();
    await backendSync({event_type:'page_step',page:5,...payload});
    const data = await backendPost('/api/step1-probe', payload);
    if (!data.five_dishes?.length) throw new Error('No probe dishes returned. Adjust preferences and retry.');
    installBackendFoods(data.five_dishes);
    Object.assign(backendState, {session:data.session_id, signature:JSON.stringify(payload), probes:data.five_dishes, choices:new Map(), ranked:[]});
    deckIndex = 0; lastSwipe = null; S.complete = true; save(); mode = 'solo'; go('explore');
  } catch (error) { backendState.error = error.message; toast(error.message); }
  finally { backendState.busy = false; render(); }
}
async function rankBackend(target = 'results') {
  if (backendState.busy) return;
  if (backendState.signature !== JSON.stringify(profilePayload())) return startBackend();
  if (backendState.choices.size !== backendState.probes.length) return toast('Please choose Like or Pass for every probe first.');
  backendState.busy = true; backendState.error = ''; render();
  try {
    await monitorSyncQueue;
    const data = await backendPost('/api/step2-finalize-and-rank', {session_id:backendState.session, choices:[...backendState.choices].map(([dish_id,liked]) => ({dish_id,liked}))});
    installBackendFoods(data.ranked_dishes);
    backendState.ranked = data.ranked_dishes; go(target);
  } catch (error) { backendState.error = error.message; toast(error.message); }
  finally { backendState.busy = false; render(); }
}
const soloWheelOptionsBeforeBackend = soloWheelOptions;
soloWheelOptions = function() {
  if (!backendEnabled) return soloWheelOptionsBeforeBackend();
  const list = backendState.signature === JSON.stringify(profilePayload()) && backendState.ranked.length ? available().slice(0,6) : [];
  return Array.from({length:6},(_,i)=>{
    const food = list[i] || null;
    return {food,slot:food ? {id:food.id,label:food.name,image:food.image} : {id:'',label:'No eligible meal',image:soloFixSlots[i].image}};
  });
};
const availableBeforeBackend = available;
available = function() {
  if (!backendEnabled || mode === 'group' || !backendState.session) return availableBeforeBackend();
  const ids = backendState.ranked.length ? backendState.ranked.map(d=>d.id) : backendState.probes.map(d=>d.id);
  return ids.map(id=>getFood('api-'+id)).filter(f => {
    // Probe choices must remain visible even when they test a stated restriction.
    if (!backendState.ranked.length) return true;
    const d = backendState.ranked.find(d=>d.id===f.backendId);
    return !checkBackendRestriction(d) && matchesFood(f,S.filters);
  });
};
function checkBackendRestriction(d) {
  return (d.violated_restrictions || []).length > 0;
}
const swipeBeforeBackend = swipe;
swipe = function(like) {
  if (!backendEnabled || mode === 'group' || !backendState.session || backendState.ranked.length) return swipeBeforeBackend(like);
  if (backendState.busy || swiping) return;
  const f = currentFood();
  if (!f) return;
  const old = backendState.choices.has(f.backendId) ? backendState.choices.get(f.backendId) : null;
  swipeBeforeBackend(like);
  lastSwipe.backendChoice = {id:f.backendId, old};
  backendState.choices.set(f.backendId,like);
  syncProbeChoices();
  if (backendState.choices.size === backendState.probes.length) {
    // The V2 timer would wrap the deck to its first card. Finish the probe
    // phase instead, using the existing loading and View picks flow.
    clearTimeout(swipeTimerV2);
    swiping = false;
    go('loading');
    rankBackend().finally(() => {
      if (route === 'loading') go('explore');
    });
  }
};
// Demo controls remain separate from the original page content.
const renderBeforeBackend = render;
render = function() {
  renderBeforeBackend();
  if (!backendEnabled || mode === 'group' || !['explore','results','passport','preferences','loading','wheel'].includes(route)) return;
  $$('[data-action="finish"], [data-action="results"], [data-action="open-wheel"], [data-action="solo-wheel"], [data-action="solo-fixed-spin"]').forEach(button => {
    if (!backendState.busy) return;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.classList.add('backend-loading');
    button.textContent = 'Loading…';
  });
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.style.cssText = 'margin:16px auto;max-width:1100px;padding:18px';
  panel.innerHTML = `<strong>Food Compass · Backend recommendations</strong><p class="small muted" role="status" aria-live="polite">${backendState.busy?'Processing model requests… This may take several minutes.':backendState.session?`${backendState.choices.size} / ${backendState.probes.length} probe choices recorded`:'Start to generate your personalized probe cards.'}</p><p class="small muted">Sample dish data · illustrative images · simulated distances. Multiplayer remains a local demo. Model failures use heuristic fallback scores.</p>${backendState.error?`<p role="alert">${esc(backendState.error)}</p>`:''}<div class="actions"><button class="btn" data-action="backend-start" ${backendState.busy?'disabled':''}>${backendState.session?'Restart with current preferences':'Start recommendations'}</button><button class="btn primary" data-action="backend-rank" ${backendState.busy||!backendState.session||backendState.choices.size!==backendState.probes.length?'disabled':''}>Get expert ranking</button><a class="btn" href="/monitor" target="_blank" rel="noopener">Live monitor</a></div>`;
  root.prepend(panel);
};
// Window capture runs before the existing document capture handlers.
window.addEventListener('click', event => {
  if (!backendEnabled || mode === 'group') return;
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'start') {
    Object.assign(backendState,{session:null,signature:'',probes:[],choices:new Map(),ranked:[]});
    backendSync({event_type:'reset'});
  }
  if (action === 'onboard-next') {
    const payload = {event_type:'page_step',page:Math.min(step+2,5)};
    if (step >= 1) payload.restrictions = [...new Set(S.avoid)];
    if (step >= 2) payload.cuisines = [...S.flavours];
    if (step >= 3) payload.goals = [...S.goals];
    backendSync(payload);
  }
  if (action === 'onboard-back' || action === 'step') {
    backendSync({event_type:'page_step',page:action === 'step' ? Number(button.dataset.value)+1 : Math.max(1,step)});
  }

  if (['open-wheel','solo-wheel','solo-fixed-spin'].includes(action)) {
    if (backendState.busy) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    const currentRanking = backendState.ranked.length && backendState.signature === JSON.stringify(profilePayload());
    if (!currentRanking) {
      event.preventDefault(); event.stopImmediatePropagation();
      if (!backendState.session) startBackend(); else rankBackend('wheel');
      return;
    }
  }
  if (action === 'v2-undo' && lastSwipe?.backendChoice) {
    const c = lastSwipe.backendChoice;
    if (c.old === null) backendState.choices.delete(c.id); else backendState.choices.set(c.id,c.old);
    syncProbeChoices();
  }
  if (['backend-start','backend-rank','finish'].includes(action) || (action === 'results' && !backendState.ranked.length)) {
    event.preventDefault(); event.stopImmediatePropagation();
    if (action === 'backend-rank' || (action === 'results' && backendState.session)) rankBackend(); else startBackend();
  }
},true);
if (backendEnabled) render();

if (backendEnabled) {
  fetch('/api/dishes').then(response => {
    if (!response.ok) throw new Error('Backend unavailable. Start the FastAPI server or use ?demo.');
    return response.json();
  }).then(data => { installBackendFoods(data.dishes); if (!soloFixBusy) render(); }).catch(error => {
    backendState.error = error.message; render();
  });
}

