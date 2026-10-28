"""Integration smoke test. No live model calls; exercises heuristic fallback."""
import importlib.util
from types import SimpleNamespace
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('food_backend', 'app(1).py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

def unavailable(**kwargs):
    raise RuntimeError('Deliberate offline model stub')

backend.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=unavailable)))
client = TestClient(backend.app)
for path in ['/', '/style.css', '/app.js', '/enhancements.js', '/backend.js', '/solo-fix.js', '/solo-fix.css', '/monitor', '/monitor.html', '/Original.png', '/Dynamic.png', '/legacy', '/api/dishes']:
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
html = client.get('/').text
assert html.index('app.js') < html.index('enhancements.js') < html.index('solo-fix.js') < html.index('backend.js')
catalog = client.get('/api/dishes').json()['dishes']
assert len(catalog) == 50
assert len({d['image'] for d in catalog}) == 50
assert all(d['image_kind'] == 'dish_illustration' for d in catalog)
for dish in catalog:
    assert (backend.BASE_DIR / 'FoodCompass-Web' / 'assets' / dish['image']).is_file()
    assert client.get(dish['image_url']).status_code == 200
assert next(d for d in catalog if d['name'] == 'Mapo Tofu')['image'] == 'dishes/dish-01.png'
assert next(d for d in catalog if d['name'] == 'Tonkotsu Pork Ramen')['image'] == 'dishes/dish-31.png' 
assert backend.check_dish_restrictions(backend.ALL_DISHES[0], ['No meat', 'Soy']) == ['No meat', 'Soy']
profile = {'language':'English','restrictions':['No pork'],'cuisines':['Chinese'],'goals':['Balance']}
client.post('/api/live-sync', json={'event_type':'reset'})
for payload,node,items in [
    ({'event_type':'page_step','page':3,'restrictions':['No pork']},'node_l1_restrictions',['No pork']),
    ({'event_type':'page_step','page':4,'cuisines':['Chinese']},'node_l2_cuisines',['Chinese']),
    ({'event_type':'page_step','page':5,'goals':['Balance']},'node_l3_goals',['Balance']),
]:
    assert client.post('/api/live-sync',json=payload).status_code == 200
    monitor = client.get('/api/monitor-state').json()
    assert monitor['left_track'][node]['items'] == items
    assert monitor['left_track'][node]['status'] == 'done'
    assert monitor['current_page'] == payload['page']
assert monitor['left_track']['base_profile_ready']
client.post('/api/live-sync',json={'event_type':'swipe_snapshot','swipes':[{'dish_id':1,'name':'Tofu','liked':True}]})
assert len(client.get('/api/monitor-state').json()['right_track']['node_r2_swipes']['swipes']) == 1
client.post('/api/live-sync',json={'event_type':'swipe_snapshot','swipes':[]})
assert client.get('/api/monitor-state').json()['right_track']['node_r2_swipes']['status'] == 'pending'
client.post('/api/live-sync',json={'event_type':'probe_reset','page':5})
assert client.get('/api/monitor-state').json()['left_track']['base_profile_ready']
first = client.post('/api/step1-probe', json=profile).json()
second = client.post('/api/step1-probe', json={**profile,'cuisines':['Italian']}).json()
assert first['session_id'] != second['session_id']
choices = [{'dish_id':d['id'],'liked':False} for d in first['five_dishes']]
assert len(choices) == 5
assert all(d.get('image') for d in first['five_dishes'])
assert client.post('/api/step2-finalize-and-rank', json={'session_id':first['session_id'],'choices':choices[:1]}).status_code == 422
for choice, dish in zip(choices, first['five_dishes']):
    assert client.post('/api/live-sync', json={'event_type':'single_swipe','swipe_item':{'name':dish['name'],'category':dish['probe_category'],'liked':choice['liked']}}).status_code == 200
response = client.post('/api/step2-finalize-and-rank', json={'session_id':first['session_id'],'choices':choices})
assert response.status_code == 200, response.text
result = response.json()
assert len(result['ranked_dishes']) == 50
assert all(d.get('image') for d in result['ranked_dishes'])
assert result['merged_final_user_profile']['initial_base_preferences']['cuisine_preferences'] == ['Chinese']
assert result['merged_final_user_profile']['inferred_current_preferences']['accepts_high_price_dishes']['max_comfortable_price_gbp'] == 12
scores = [d['evaluation']['consensus_ranking_score'] for d in result['ranked_dishes']]
assert scores == sorted(scores, reverse=True)
monitor = client.get('/api/monitor-state').json()
assert monitor['consensus_node']['status'] == 'done'
assert len(monitor['right_track']['node_r2_swipes']['swipes']) == 5
assert client.post('/api/step2-finalize-and-rank', json={'session_id':'missing','choices':choices}).status_code == 400
print('PASS: static routes, catalog, restrictions, isolated sessions, probe/feedback/ranking, validation and live monitor (offline fallback).')
