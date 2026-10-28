// Contract checks for the integration overrides without a model or browser.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
function context(demo=false) {
  const c=vm.createContext({console,URLSearchParams,location:{protocol:'http:',search:demo?'?demo':''},
    structuredClone,fetch:()=>new Promise(()=>{}),setTimeout:()=>1,clearTimeout:()=>{},
    document:{addEventListener:()=>{},createElement:()=>({})},window:{listeners:[],addEventListener:function(type,callback){this.listeners.push(callback)}}});
  vm.runInContext(`
    let step=0,route='welcome',mode='solo',S={language:'English',avoid:[],flavours:[],goals:[],filters:{}},foods=[],lastSwipe=null,deckIndex=0,selectedFood='',previous='';
    const esc=x=>String(x),asset=x=>'assets/'+x,money=x=>'£'+x,root={prepend:()=>{}},dlg={close:()=>{},className:''};
    const nodes={'#solo-fixed-rotor':{style:{},dataset:{}},'.solo-fixed-spin':{setAttribute:()=>{}},'#solo-fixed-status':{}};
    const $=s=>nodes[s];
    let rejectAll=false,chosen='';
    function matchesFood(){return !rejectAll} function getFood(id){return foods.find(f=>f.id===id)||{id,name:id,image:'tofu.jpg',price:5,dining:['Takeaway']}}
    function available(){return foods} function render(){} function go(r){route=r} function results(){} function swipe(){} function save(){} function toast(){} function modal(){} function btn(){return ''} function shell(s){return s}
    function handleClick(e){chosen=e.target.closest().dataset.action}
  `,c);
  for(const file of ['solo-fix.js','backend.js'])vm.runInContext(fs.readFileSync('FoodCompass-Web/'+file,'utf8'),c);
  return c;
}
const c=context();
vm.runInContext(`
  if(soloWheelOptions().some(x=>x.food))throw Error('Unranked backend wheel must be empty');
  const dishes=Array.from({length:8},(_,i)=>({id:i+1,name:'Dish '+(i+1),ingredients:[],price:5,cuisine:'Chinese',calories:200,protein_g:10,rating:4,evaluation:{consensus_ranking_score:9-i,ranking_formula:'test'},violated_restrictions:i===0?['No pork']:[]}));
  installBackendFoods(dishes);backendState.session='test';backendState.signature=JSON.stringify(profilePayload());backendState.ranked=dishes;
`,c);
assert.equal(vm.runInContext("backendFood({id:99,ingredients:[],image:'food-4.jpg'}).image",c),'food-4.jpg');
assert.equal(vm.runInContext('soloWheelOptions().length',c),6);
assert.equal(vm.runInContext('soloWheelOptions()[0].food.id',c),'api-2');
assert.equal(vm.runInContext('soloWheelOptions()[5].food.id',c),'api-7');
vm.runInContext("soloFixSelection=soloWheelOptions()[0];soloFixChoose()",c);
assert.equal(vm.runInContext('chosen',c),'choose:api-2');
vm.runInContext('soloFixDetails()',c);
assert.equal(vm.runInContext('selectedFood',c),'api-2');
assert.equal(vm.runInContext('route',c),'detail');
vm.runInContext("rejectAll=true",c);
assert.equal(vm.runInContext('soloWheelOptions().filter(x=>x.food).length',c),0);
vm.runInContext("rejectAll=false;S.goals=['changed']",c);
assert.equal(vm.runInContext('soloWheelOptions().filter(x=>x.food).length',c),0);
const demo=context(true);
assert.equal(vm.runInContext('soloWheelOptions().filter(x=>x.food).length',demo),6);
console.log('PASS: ranked wheel uses backend IDs/order, restrictions, empty filters, changed profiles, details/choose, demo mode.');

(async () => {
  const auto = context();
  vm.runInContext(`
    render=()=>{};
    backendState.session='wheel-test';
    backendState.signature=JSON.stringify(profilePayload());
    backendState.probes=[{id:1}];backendState.choices.set(1,true);
    let rankCalls=0;
    backendPost=async(path)=>{if(path==='/api/step2-finalize-and-rank')rankCalls++;return {ranked_dishes:[{id:1,name:'Ranked meal',ingredients:[],price:5,rating:4}]}};
    window.listeners[0]({target:{closest:()=>({dataset:{action:'open-wheel'}})},preventDefault(){},stopImmediatePropagation(){}});
  `, auto);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(vm.runInContext('rankCalls',auto),1);
  assert.equal(vm.runInContext('route',auto),'wheel');
  vm.runInContext(`window.listeners[0]({target:{closest:()=>({dataset:{action:'open-wheel'}})},preventDefault(){},stopImmediatePropagation(){}})`,auto);
  assert.equal(vm.runInContext('rankCalls',auto),1);
  console.log('PASS: wheel click generates ranking once and opens wheel; existing ranking is reused.');
})().catch(error=>{console.error(error);process.exitCode=1});

(async()=>{
 const live=context();
 vm.runInContext(`
   render=()=>{};
   const sentEvents=[];
   backendPost=async(path,body)=>{if(path==='/api/live-sync')sentEvents.push(body);return {status:'ok'}};
   function clickSync(action,value){window.listeners[0]({target:{closest:()=>({dataset:{action,value}})},preventDefault(){},stopImmediatePropagation(){}})}
   clickSync('start');
   step=0;clickSync('onboard-next');
   S.avoid=['No pork'];step=1;clickSync('onboard-next');
   S.flavours=['Chinese'];step=2;clickSync('onboard-next');
   S.goals=['Balance'];step=3;clickSync('onboard-next');
 `,live);
 await vm.runInContext('monitorSyncQueue',live);
 assert.equal(vm.runInContext("sentEvents[0].event_type",live),'reset');
 assert.equal(vm.runInContext("sentEvents[2].restrictions[0]",live),'No pork');
 assert.equal(vm.runInContext("sentEvents[2].page",live),3);
 assert.equal(vm.runInContext("sentEvents[3].cuisines[0]",live),'Chinese');
 assert.equal(vm.runInContext("sentEvents[4].goals[0]",live),'Balance');
 vm.runInContext(`backendState.probes=[{id:1,name:'Tofu',probe_category:'Budget Anchor'}];backendState.choices.set(1,true);syncProbeChoices();lastSwipe={backendChoice:{id:1,old:null}};clickSync('v2-undo')`,live);
 await vm.runInContext('monitorSyncQueue',live);
 assert.equal(vm.runInContext('sentEvents.at(-2).swipes.length',live),1);
 assert.equal(vm.runInContext('sentEvents.at(-1).swipes.length',live),0);
 console.log('PASS: ordered Continue events publish restrictions, cuisines, goals and exact Undo snapshots.');
})().catch(e=>{console.error(e);process.exitCode=1});
(async()=>{
  const flow=context();
  vm.runInContext(`
    render=()=>{};route='explore';
    let swiping=false,swipeTimerV2=123,probePosition=0;
    function currentFood(){return getFood('api-'+(probePosition+1))}
    backendState.session='five-probes';backendState.signature=JSON.stringify(profilePayload());
    backendState.probes=Array.from({length:5},(_,i)=>({id:i+1,name:'Probe '+(i+1),ingredients:[],price:5,rating:4}));
    installBackendFoods(backendState.probes);
    let autoRankCalls=0,submittedChoices=[];
    backendPost=async(path,body)=>{
      if(path==='/api/step2-finalize-and-rank'){autoRankCalls++;submittedChoices=body.choices;return {ranked_dishes:backendState.probes}}
      return {status:'ok'};
    };
    for(probePosition=0;probePosition<4;probePosition++){lastSwipe={};swipe(probePosition%2===0)}
  `,flow);
  assert.equal(vm.runInContext('autoRankCalls',flow),0);
  assert.equal(vm.runInContext('route',flow),'explore');
  vm.runInContext('lastSwipe={};swipe(false)',flow);
  assert.equal(vm.runInContext('route',flow),'loading');
  assert.equal(vm.runInContext('backendState.busy',flow),true);
  // A repeated click while ranking must not submit again.
  vm.runInContext('swipe(true)',flow);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(vm.runInContext('autoRankCalls',flow),1);
  assert.equal(vm.runInContext('submittedChoices.length',flow),5);
  assert.equal(vm.runInContext('route',flow),'results');
  console.log('PASS: only the fifth distinct probe choice auto-ranks, shows loading, prevents duplicates and opens picks.');
})().catch(e=>{console.error(e);process.exitCode=1});
