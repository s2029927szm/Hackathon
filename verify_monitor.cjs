const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('monitor(1).html','utf8').replace(/<!--[\s\S]*?-->/g,'');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
function classList(){const values=new Set();return {add(...x){x.forEach(v=>values.add(v))},remove(...x){x.forEach(v=>values.delete(v))},toggle(v,on){if(on)values.add(v);else values.delete(v)},contains(v){return values.has(v)}}}
const nodes=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],{innerText:'',innerHTML:'',className:'',classList:classList()}]));
const completed=JSON.parse(fs.readFileSync('monitor-test-state.json','utf8'));completed.run_id='test-run';
function emptyState(){const s=structuredClone(completed);s.run_id='empty-run';s.current_page=1;s.subtitle_stream=[];
 for(const k of ['node_l1_restrictions','node_l2_cuisines','node_l3_goals'])s.left_track[k]={status:'pending',items:[]};s.left_track.base_profile_ready=false;
 s.right_track.node_r1_prompt1={status:'pending',probes:[]};s.right_track.node_r2_swipes={status:'pending',swipes:[]};s.right_track.node_r3_prompt2={status:'pending',verdicts:{}};s.right_track.dynamic_profile_ready=false;
 s.fusion_node={status:'pending',summary:''};s.dispatch_animation=false;
 Object.keys(s.experts_node).forEach(k=>s.experts_node[k]={status:'pending',batch_1:'pending',batch_2:'pending',sample_scores:[]});s.consensus_node={status:'pending',top_dishes:[],price_filter:null};return s;}
let state=emptyState(),clock=0;const body={classList:classList()};
const context=vm.createContext({console,structuredClone,performance:{now:()=>clock},document:{body,getElementById(id){assert(nodes.has(id),'Unknown element '+id);return nodes.get(id)}},fetch:async()=>({json:async()=>structuredClone(state)}),setInterval(fn,ms){assert.equal(ms,600)}});
vm.runInContext(script,context);
async function poll(at){clock=at;await vm.runInContext('pollState()',context)}
(async()=>{
 await poll(0);
 assert.doesNotMatch(nodes.get('l1-items').innerHTML,/Egg|No pork/);assert.match(nodes.get('r2-swipes').innerHTML,/Waiting/);
 for(const id of ['declared-track','inferred-track','fusion-box','reviewers-row','consensus-card'])assert(!nodes.get(id).classList.contains('stage-active'));
 assert(!body.classList.contains('pipeline-active'));assert(!nodes.get('fuse-icon-core').classList.contains('profile-merged'));
 state=structuredClone(completed);await poll(0);
 assert.match(nodes.get('r3-verdicts').innerHTML,/Flavor Exploration/);assert.match(nodes.get('r3-verdicts').innerHTML,/Selective Explorer/);
 assert.match(nodes.get('r1-probes').innerHTML,/Budget Anchor/);assert.doesNotMatch(nodes.get('r1-probes').innerHTML,/[\u4e00-\u9fff]/);
 assert.match(nodes.get('base-avatar-card').className,/opacity-100/);assert(nodes.get('declared-track').classList.contains('stage-active'));
 assert(nodes.get('particle-dispatcher').classList.contains('hidden'));assert.match(nodes.get('top-consensus-list').innerHTML,/Waiting/);
 await poll(1199);assert(!nodes.get('fuse-icon-core').classList.contains('profile-merged'));
 await poll(1200);assert(nodes.get('fuse-icon-core').classList.contains('profile-merged'));assert(nodes.get('particle-dispatcher').classList.contains('hidden'));
 await poll(11199);assert(nodes.get('particle-dispatcher').classList.contains('hidden'));
 await poll(11200);assert(!nodes.get('particle-dispatcher').classList.contains('hidden'));assert(!nodes.get('reviewers-row').classList.contains('stage-active'));
 await poll(12599);assert.match(nodes.get('top-consensus-list').innerHTML,/Waiting/);
 await poll(12600);assert(nodes.get('reviewers-row').classList.contains('stage-active'));assert(nodes.get('consensus-card').classList.contains('stage-active'));assert.match(nodes.get('top-consensus-list').innerHTML,/8.8/);
 state.experts_node.nutrition_expert.status='running';state.experts_node.nutrition_expert.batch_2='running';await poll(14000);
 assert.match(nodes.get('exp-nutrition').className,/running-glow/);assert.match(nodes.get('nutri-b2').innerText,/Running/);
 state=emptyState();await poll(15000);assert(!nodes.get('fuse-icon-core').classList.contains('profile-merged'));assert(nodes.get('particle-dispatcher').classList.contains('hidden'));assert.doesNotMatch(nodes.get('r2-swipes').innerHTML,/Mapo/);assert.match(nodes.get('top-consensus-list').innerHTML,/Waiting/);
 state=structuredClone(completed);state.run_id='new-run';await poll(16000);assert(nodes.get('particle-dispatcher').classList.contains('hidden'));
 assert.equal((html.match(/src="Original.png"/g)||[]).length,2);assert.equal((html.match(/src="Dynamic.png"/g)||[]).length,2);
 console.log('PASS: empty initial state; stage activation; 1.2s fusion + 10s hold + 1.4s dispatch; persistent merged border; deferred reviewers/ranking; reset/new-run timing; English labels and 600ms polling.');
})().catch(e=>{console.error(e);process.exitCode=1});
