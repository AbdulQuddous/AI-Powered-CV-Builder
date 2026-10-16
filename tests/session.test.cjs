const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function harness(fetcher){
    const storage=new Map(),calls=[];
    const window={location:{origin:'http://localhost'},sessionStorage:{getItem:k=>storage.get(k)||null,
        setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},
        fetch:async(url,options)=>{calls.push({url,options});return fetcher(url,options);}};
    vm.runInNewContext(fs.readFileSync('accounts/static/accounts/js/session.js','utf8'),{window,Headers,URL,Date,Math});
    window.M1Session.storeTokens({access:'old-access',refresh:'old-refresh'});
    return {api:window.M1Session,storage,calls};
}
const response=(status,data={})=>({status,ok:status<400,json:async()=>data});

test('simultaneous expired requests share one refresh, rotate both tokens and retain identity',async()=>{
    const h=harness(async(url,options)=>url==='/api/auth/refresh/'
        ? response(200,{access:'new-access',refresh:'new-refresh'})
        : response(options.headers.get('Authorization')==='Bearer old-access'?401:200));
    const identity=h.api.identity();
    const results=await Promise.all([h.api.request('/api/cvs/1/'),h.api.request('/api/cvs/2/')]);
    assert.equal(results.every(r=>r.status===200),true);
    assert.equal(h.calls.filter(c=>c.url==='/api/auth/refresh/').length,1);
    assert.equal(h.api.accessToken(),'new-access');assert.equal(h.storage.get('cv_refresh'),'new-refresh');
    assert.equal(h.api.identity(),identity);
});

test('invalid renewal clears tokens while unavailable renewal allows retry',async()=>{
    const invalid=harness(async()=>response(401));
    await assert.rejects(invalid.api.request('/api/cvs/'),e=>e.status===401);
    assert.equal(invalid.storage.size,0);
    const outage=harness(async url=>response(url==='/api/auth/refresh/'?503:401));
    await assert.rejects(outage.api.request('/api/cvs/'),e=>e.status===503);
    assert.equal(outage.api.accessToken(),'old-access');
});

test('logout revokes the latest rotated refresh token and clears local credentials',async()=>{
    const h=harness(async(url,options)=>{
        if(url==='/api/auth/refresh/')return response(200,{access:'new-access',refresh:'new-refresh'});
        if(options.headers.get('Authorization')==='Bearer old-access')return response(401);
        assert.deepEqual(JSON.parse(options.body),{refresh:'new-refresh'});return response(204);
    });
    assert.equal(await h.api.logout(),true);assert.equal(h.storage.size,0);
});

test('late renewal cannot restore a signed-out session or replace a new account',async()=>{
    let finish;
    const h=harness(async url=>url==='/api/auth/refresh/'?new Promise(resolve=>{finish=resolve;}):response(401));
    const pending=h.api.request('/api/cvs/');
    while(!finish)await new Promise(resolve=>setImmediate(resolve));
    h.api.clear();h.api.storeTokens({access:'other-user',refresh:'other-refresh'});
    finish(response(200,{access:'late-old-user',refresh:'late-old-refresh'}));
    await assert.rejects(pending,e=>e.code==='session_changed');
    assert.equal(h.api.accessToken(),'other-user');
});

test('JWT transport refuses external URLs and retries a rejected request at most once',async()=>{
    const h=harness(async url=>url==='/api/auth/refresh/'?response(200,{access:'new',refresh:'rotated'}):response(401));
    await assert.rejects(h.api.request('https://untrusted.example/api/cvs/'),/outside the application API/);
    assert.equal(h.calls.length,0);
    assert.equal((await h.api.request('/api/cvs/')).status,401);
    assert.equal(h.calls.length,3);assert.equal(h.storage.size,0);
});

test('failed server logout still removes all browser credentials',async()=>{
    const h=harness(async()=>{throw new Error('Offline');});
    h.storage.set('access_token','legacy');
    assert.equal(await h.api.logout(),false);assert.equal(h.storage.size,0);
});
