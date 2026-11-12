from test_saas import hosted, demo, headers

def test_rover_structure_routes_keep_workspace_auth_and_csrf(hosted):
    app,repo,settings,alice,bob,alice_id,bob_id,wa,wb=hosted
    graph=demo(alice,wa);project=graph['project_id'];plan='a'*32;version='b'*64
    path=f'/projects/{project}/inventory/{plan}/robot-design/structure'
    body={'function_version':version,'expected_revision':0,'structure':{'version':1,'objects':[]}}
    assert bob.get(f'/api/w/{wa}'+path,params={'function_version':version}).status_code==404
    assert bob.get(f'/api/w/{wb}'+path,params={'function_version':version}).status_code==404
    assert alice.put(f'/api/w/{wa}'+path,json=body).status_code==403
    # A valid actor still cannot write to an absent analysis plan.
    assert alice.put(f'/api/w/{wa}'+path,json=body,headers=headers(alice)).status_code==404
    circuit_path=f'/projects/{project}/inventory/{plan}/robot-design/circuit'
    circuit_body={'function_version':version,'expected_revision':0,'circuit':{'version':1,'components':[],'connections':[]}}
    assert bob.get(f'/api/w/{wa}'+circuit_path,params={'function_version':version}).status_code==404
    assert bob.get(f'/api/w/{wb}'+circuit_path,params={'function_version':version}).status_code==404
    assert alice.put(f'/api/w/{wa}'+circuit_path,json=circuit_body).status_code==403
    assert alice.put(f'/api/w/{wa}'+circuit_path,json=circuit_body,headers=headers(alice)).status_code==404
    photo_path=f'/projects/{project}/inventory/{plan}/photo-structure'
    assert bob.get(f'/api/w/{wa}'+photo_path).status_code==404
    assert bob.get(f'/api/w/{wb}'+photo_path).status_code==404
    assert alice.post(f'/api/w/{wa}'+photo_path,json={'expected_revision':graph['revision']}).status_code==403
    assert alice.post(f'/api/w/{wa}'+photo_path,json={'expected_revision':graph['revision']},headers=headers(alice)).status_code==404
