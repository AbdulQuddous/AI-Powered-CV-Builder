const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const clone=value=>JSON.parse(JSON.stringify(value));
function sample(id,name='Backend CV') {
    const data=JSON.parse(fs.readFileSync('shared/examples/cv_draft.json','utf8'));
    data.meta={target_role:'Backend Developer',career_level:'fresher',template_id:'modern'};
    data.personal.full_name='Ali Khan';data.skills=['Python','Django'];
    return {id,name,data,version:1,created_at:'2026-10-13T09:00:00Z',updated_at:'2026-10-13T09:00:00Z'};
}
function harness(overrides={}) {
    const elements=new Map(),calls=[],saved=new Map([[12,sample(12,'Ali’s Backend CV')],[13,sample(13,'Frontend CV')]]),documentListeners=new Map();
    let document;
    function element() {
        const classes=new Set(['hidden']);
        const node={style:{},value:'',textContent:'',disabled:false,children:[],options:[],listeners:{},attributes:{},dataset:{},isConnected:true,
            classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){if(on)classes.add(x);else classes.delete(x);}},
            addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);},
            append(...children){this.children.push(...children);},
            appendChild(child){this.children.push(child);return child;},replaceChildren(){this.children=[];this.options=[];this.value='';},
            add(option){this.options.push(option);if(this.options.length===1)this.value=option.value;},
            setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},
            focus(){document.activeElement=this;},reset(){},getClientRects(){return [{}];},
            querySelectorAll(){return this.children.flatMap(child=>[child,...child.querySelectorAll()]).filter(child=>child.type==='button'&&!child.disabled);},
            closest(){return this;}
        };
        Object.defineProperty(node,'innerHTML',{get(){return this.html??String(this.textContent).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');},set(value){this.html=value;}});
        return node;
    }
    const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
    document={getElementById:get,createElement:element,createTextNode:text=>({textContent:text,querySelectorAll:()=>[]}),body:{style:{}},querySelector:()=>null,querySelectorAll:()=>[],
        addEventListener(name,fn){const list=documentListeners.get(name)||[];list.push(fn);documentListeners.set(name,list);}};
    const storage=new Map([['cv_access','jwt']]);
    const location={href:'http://localhost/dashboard/',origin:'http://localhost',search:''};
    const window={location,history:{replaceState(_a,_b,url){location.href=String(url);location.search=new URL(url).search;}},
        M6Api:{create:()=>({})},M6Review:{init(){},observe(){},reset(){}},M4Import:{init(){},async resume(){},reset(){}}};
    const c=vm.createContext({window,document,URL,URLSearchParams,Headers,FormData,console,
        setTimeout:()=>0,clearTimeout(){},Option:function(text,value){this.text=text;this.value=value;},
        sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},
        fetch:async(url,options)=>{
            assert.equal(options.headers.get('Authorization'),'Bearer jwt');
            const body=options.body?JSON.parse(options.body):null;
            calls.push({url,method:options.method||'GET',body});
            if(overrides.fetch){const result=await overrides.fetch(url,options,body);if(result)return result;}
            let result,status=200;
            if(url==='/api/cvs/'&&options.method==='POST') {
                const id=20;result=sample(id,body.name);result.data.meta={target_role:body.target_role,career_level:body.career_level,template_id:body.template_id};saved.set(id,result);status=201;
            }else if(url.startsWith('/api/cvs/')&&url.endsWith('/duplicate/')) {
                const source=saved.get(Number(url.split('/')[3]));result={...clone(source),id:20,name:source.name+' (copy)',version:1};saved.set(20,result);status=201;
            }else if(url==='/api/cvs/')result={results:[...saved.values()],next:null};
            else if(url.includes('/versions/'))result={results:[{version:2,name:'Updated CV',created_at:'2026-10-13T10:00:00Z'},{version:1,name:'Original CV',created_at:'2026-10-12T10:00:00Z'}],next:null};
            else if(url==='/api/templates/')result=[{id:'modern',name:'Modern'}];
            else if(options.method==='DELETE') { saved.delete(Number(url.split('/')[3]));status=204; }
            else if(url.endsWith('/preview/'))return {ok:true,status:200,text:async()=>'<html><head></head><body>Saved CV</body></html>'};
            else if(/^\/api\/cvs\/\d+\/$/.test(url))result=saved.get(Number(url.split('/')[3]));
            else throw Error('Unexpected request '+url);
            return {ok:true,status,json:async()=>{if(status===204)throw Error('204 must not be parsed');return clone(result);}};
        }
    });
    for(const name of ['dashboard','cv_operations'])vm.runInContext(fs.readFileSync(`m9_dashboard/static/m9_dashboard/js/${name}.js`,'utf8'),c);
    vm.runInContext('registerEvents()',c);
    const click=async id=>{for(const fn of get(id).listeners.click||[])await fn();};
    const action=async(action,id=12)=>{const button=element();button.type='button';button.dataset={action,id:String(id)};button.textContent=action;const event={target:button};await vm.runInContext('handleCardClick',c)(event);return button;};
    return {c,get,calls,saved,storage,click,action,documentListeners,load:()=>vm.runInContext('loadCVs()',c),run:source=>vm.runInContext(source,c)};
}
const fail=status=>({ok:false,status,json:async()=>({detail:'Operation failed'})});

test('manual creation sends all selected fields and opens the existing editor',async()=>{
    const h=harness();h.get('cvName').value='My CV';h.get('targetRole').value='Backend Developer';h.get('careerLevel').value='experienced';h.get('templateId').value='modern';
    await h.run('handleCreateCV({preventDefault(){}})');
    assert.deepEqual(h.calls.find(x=>x.method==='POST').body,{name:'My CV',target_role:'Backend Developer',career_level:'experienced',template_id:'modern',data:{}});
    assert.equal(h.c.window.location.href,'/cvs/20/edit/');
});

test('creation displays wrapped API field errors and preserves form values for retry',async()=>{
    const h=harness({fetch:(url,options)=>url==='/api/cvs/'&&options.method==='POST'
        ? {ok:false,status:400,json:async()=>({error:{code:'validation_error',details:{
            career_level:['"junior" is not a valid choice.'],template_id:['The selected template is unavailable.']}}})}
        : null});
    h.get('cvName').value='My CV';h.get('targetRole').value='Backend';
    h.get('careerLevel').value='junior';h.get('templateId').value='modern';
    await h.run('handleCreateCV({preventDefault(){}})');
    assert.match(h.get('createError').textContent,/Career level:.*junior.*not a valid choice/);
    assert.match(h.get('createError').textContent,/Template: The selected template is unavailable/);
    assert.equal(h.get('createError').classList.contains('hidden'),false);
    assert.equal(h.get('cvName').value,'My CV');assert.equal(h.get('createSubmit').disabled,false);
    assert.equal(h.run('state.creating'),false);assert.equal(h.saved.size,2);
});

test('API error messages cover canonical documents, plain DRF fields, and non-JSON failures',async()=>{
    const h=harness();
    assert.equal(h.run('apiErrorMessage({error:{details:{data:[{path:"education/0/end_date",message:"Invalid date."}]}}},400)'),
        'education/0/end_date: Invalid date.');
    assert.equal(h.run('apiErrorMessage({name:["This field is required."]},400)'), 'CV name: This field is required.');
    assert.equal(h.run('apiErrorMessage({detail:"Try again later."},429)'), 'Try again later.');
    assert.equal(h.run('apiErrorMessage({},500)'), 'Request failed (500).');
});

test('AI creation sends selected metadata to M5 and does not create an empty M2 record',async()=>{
    const id='00000000-0000-4000-8000-000000000001';
    const h=harness({fetch:url=>url==='/api/chat/sessions/'?{ok:true,status:201,json:async()=>({id,cv_id:null,status:'active',current_section:'personal',assistant_message:'What is your full name?'})}:null});
    h.c.document.createTextNode=text=>text;
    for(const element of ['chatHistory'])h.get(element).appendChild=child=>h.get(element).children.push(child);
    // Chat bubbles use the native append API.
    const create=h.c.document.createElement;
    h.c.document.createElement=()=>{const node=create();node.append=(...items)=>node.children.push(...items);return node;};
    await h.run("openCreateCV('ai')");
    h.get('cvName').value='AI CV';h.get('targetRole').value='Backend';h.get('careerLevel').value='fresher';h.get('templateId').value='modern';
    await h.run('handleCreateCV({preventDefault(){}})');
    assert.deepEqual(h.calls.find(c=>c.url==='/api/chat/sessions/').body,{cv_id:null,cv_name:'AI CV',target_role:'Backend',career_level:'fresher',template_id:'modern'});
    assert.equal(h.calls.some(c=>c.url==='/api/cvs/'&&c.method==='POST'),false);
    assert.equal(h.get('chatModal').classList.contains('hidden'),false);
});

test('AI startup validation returns to the creation form with the actual field error',async()=>{
    const h=harness({fetch:url=>url==='/api/chat/sessions/'
        ? {ok:false,status:400,json:async()=>({error:{code:'validation_error',details:{career_level:['Choose a supported career level.']}}})}
        : null});
    await h.run("openCreateCV('ai')");
    h.get('cvName').value='My AI CV';h.get('targetRole').value='Backend';
    h.get('careerLevel').value='junior';h.get('templateId').value='classic';
    await h.run('handleCreateCV({preventDefault(){}})');
    assert.match(h.get('createError').textContent,/Career level: Choose a supported career level/);
    assert.equal(h.get('createModal').classList.contains('hidden'),false);
    assert.equal(h.get('chatModal').classList.contains('hidden'),true);
    assert.equal(h.get('chatRetry').classList.contains('hidden'),true);
    assert.equal(h.get('cvName').value,'My AI CV');assert.equal(h.get('templateId').value,'classic');
    assert.equal(h.get('createSubmit').disabled,false);
});

test('AI startup Retry retains all creation metadata after a service failure',async()=>{
    let posts=0;
    const id='00000000-0000-4000-8000-000000000009';
    const h=harness({fetch:url=>url==='/api/chat/sessions/'
        ? (++posts===1 ? fail(502) : {ok:true,status:201,json:async()=>({id,cv_id:null,status:'active',current_section:'personal',assistant_message:'What is your full name?'})})
        :null});
    await h.run("openCreateCV('ai')");
    h.get('cvName').value='Retry AI CV';h.get('targetRole').value='Backend';
    h.get('careerLevel').value='experienced';h.get('templateId').value='classic';
    await h.run('handleCreateCV({preventDefault(){}})');
    assert.equal(h.get('chatRetry').classList.contains('hidden'),false);
    await h.click('chatRetry');
    const attempts=h.calls.filter(c=>c.url==='/api/chat/sessions/');
    assert.equal(attempts.length,2);assert.deepEqual(attempts[1].body,attempts[0].body);
    assert.deepEqual(attempts[1].body,{cv_id:null,cv_name:'Retry AI CV',target_role:'Backend',career_level:'experienced',template_id:'classic'});
    assert.equal(h.run('chat.session.id'),id);
    assert.equal(h.get('createModal').classList.contains('hidden'),true);
    assert.ok(h.calls.every(c=>!(c.url==='/api/cvs/'&&c.method==='POST')));
});

test('retrying an explicit conversation resume keeps its session ID without creating another chat',async()=>{
    let reads=0;
    const id='00000000-0000-4000-8000-000000000010';
    const h=harness({fetch:url=>url===`/api/chat/sessions/${id}/`
        ? (++reads===1 ? fail(502) : {ok:true,status:200,json:async()=>({id,cv_id:null,status:'active',current_section:'personal',messages:[]})})
        : null});
    await h.run(`openAIChat(null,'${id}')`);await h.click('chatRetry');
    assert.equal(reads,2);assert.equal(h.run('chat.session.id'),id);
    assert.ok(h.calls.every(c=>c.method==='GET'));
});

test('chat validation preserves the message and shows a correction instead of network Retry',async()=>{
    const h=harness({fetch:url=>url.endsWith('/messages/')
        ? {ok:false,status:400,json:async()=>({error:{details:{message:['Ensure this field has no more than 10000 characters.']}}})}
        : null});
    h.run('chat.session={id:"11111111-1111-1111-1111-111111111111",status:"active",current_section:"summary",messages:[]}');
    h.get('chatInput').value='A message needing correction';await h.run('sendChatMessage()');
    assert.match(h.get('chatError').textContent,/10000 characters/);
    assert.doesNotMatch(h.get('chatError').textContent,/Unable to reach/);
    assert.equal(h.get('chatInput').value,'A message needing correction');
    assert.equal(h.get('chatRetry').classList.contains('hidden'),true);
    assert.equal(h.get('chatSend').disabled,false);
});

test('listing preserves search/filter/sort, shows career level, and Edit/View retain existing routes',async()=>{
    const h=harness();await h.load();assert.equal(h.get('summaryTotal').textContent,2);
    const card=h.get('cardsGrid').children[0];assert.match(card.innerHTML,/Career level: Fresher/);
    const controls=card.children.flatMap(x=>x.children||[]);assert.ok(controls.some(x=>x.dataset.action==='delete'));assert.ok(controls.some(x=>x.dataset.action==='versions'));
    h.get('searchInput').value='Frontend';h.run('renderCVs()');assert.equal(h.get('cardsGrid').children.length,1);
    h.get('searchInput').value='';h.get('sortSelect').value='name';h.run('renderCVs()');assert.equal(h.get('cardsGrid').children.length,2);
    await h.action('view');assert.match(h.get('previewFrame').srcdoc,/Saved CV/);
    await h.action('edit');assert.equal(h.c.window.location.href,'/cvs/12/edit/');
});

test('cancelled deletion makes no DELETE request and restores focus',async()=>{
    const h=harness();await h.load();const trigger=await h.action('delete');
    assert.equal(h.get('deleteCVName').textContent,'Ali’s Backend CV');
    assert.equal(h.c.document.activeElement,h.get('deleteCancel'));
    await h.click('deleteCancel');assert.equal(h.calls.filter(x=>x.method==='DELETE').length,0);
    assert.equal(h.get('summaryTotal').textContent,2);assert.equal(h.c.document.activeElement,trigger);
});

test('confirmed 204 deletion removes only that CV and updates cards, statistics, and chat resume state',async()=>{
    const h=harness();await h.load();h.storage.set('m9_chat_sessions',JSON.stringify({12:'chat-12',13:'chat-13'}));
    await h.action('delete');await h.click('deleteConfirm');
    assert.equal(h.saved.has(12),false);assert.equal(h.saved.has(13),true);
    assert.equal(h.get('summaryTotal').textContent,1);assert.equal(h.get('cardsGrid').children.length,1);
    assert.deepEqual(JSON.parse(h.storage.get('m9_chat_sessions')),{13:'chat-13'});
    assert.match(h.get('toast').textContent,/Deleted.*Ali’s Backend CV/);
    assert.equal(h.get('deleteModal').classList.contains('hidden'),true);
});

test('failed deletion preserves cards and permits retry',async()=>{
    const h=harness({fetch:(_url,options)=>options.method==='DELETE'?fail(500):null});await h.load();
    await h.action('delete');await h.click('deleteConfirm');
    assert.equal(h.get('summaryTotal').textContent,2);assert.equal(h.get('cardsGrid').children.length,2);
    assert.equal(h.get('deleteConfirm').disabled,false);assert.match(h.get('deleteError').textContent,/Could not confirm deletion/);
});

test('duplicate Delete clicks produce one request and cannot cancel an in-flight deletion',async()=>{
    let finish;const h=harness({fetch:(_url,options)=>options.method==='DELETE'?new Promise(resolve=>{finish=resolve;}):null});await h.load();await h.action('delete');
    const request=h.click('deleteConfirm');await h.click('deleteConfirm');await h.click('deleteCancel');
    assert.equal(h.calls.filter(x=>x.method==='DELETE').length,1);assert.equal(h.get('deleteConfirm').disabled,true);
    assert.equal(h.get('deleteModal').classList.contains('hidden'),false);
    finish({ok:true,status:204,json:()=>{throw Error('No JSON allowed');}});await request;
    assert.equal(h.get('summaryTotal').textContent,1);
});

test('expired authentication clears private state and opens existing login',async()=>{
    const h=harness({fetch:(_url,options)=>options.method==='DELETE'?fail(401):null});await h.load();await h.action('delete');await h.click('deleteConfirm');
    assert.equal(h.get('loginModal').classList.contains('hidden'),false);assert.equal(h.get('deleteModal').classList.contains('hidden'),true);
    assert.equal(h.get('summaryTotal').textContent,0);assert.equal(h.storage.has('cv_access'),false);
});

test('owner-hidden 404 preserves the card and shows a useful error',async()=>{
    const h=harness({fetch:(_url,options)=>options.method==='DELETE'?fail(404):null});await h.load();await h.action('delete');await h.click('deleteConfirm');
    assert.equal(h.get('summaryTotal').textContent,2);assert.match(h.get('deleteError').textContent,/does not belong/);
});

test('deleting the last CV displays the empty state and resets statistics',async()=>{
    const h=harness();h.saved.delete(13);await h.load();await h.action('delete');await h.click('deleteConfirm');
    assert.equal(h.get('summaryTotal').textContent,0);assert.equal(h.get('summaryTemplates').textContent,0);
    assert.equal(h.get('summaryUpdated').textContent,'—');assert.equal(h.get('emptyState').classList.contains('hidden'),false);
});

test('duplication keeps the original and identifies the returned copy',async()=>{
    const h=harness();await h.load();const original=clone(h.saved.get(12));await h.action('duplicate');
    assert.deepEqual(h.saved.get(12),original);assert.deepEqual(h.saved.get(20).data,original.data);
    assert.equal(h.get('summaryTotal').textContent,3);assert.match(h.get('toast').textContent,/copy.*CV #20/);
});

test('version history is read-only and renders saved timestamps',async()=>{
    const h=harness();await h.load();await h.action('versions');
    assert.equal(h.get('versionsRows').children.length,2);
    const first=h.get('versionsRows').children[0];assert.equal(first.children[0].textContent,'2');assert.match(first.children[2].textContent,/2026/);
    assert.ok(h.calls.every(x=>x.method==='GET'));await h.click('versionsClose');assert.equal(h.get('versionsModal').classList.contains('hidden'),true);
});

test('re-registering dashboard events never duplicates the delete handler',async()=>{
    const h=harness();h.run('registerEvents()');assert.equal(h.get('deleteConfirm').listeners.click.length,1);
});

test('an old list response cannot resurrect a successfully deleted CV',async()=>{
    let finish,defer=false;
    const h=harness({fetch:(url,options)=>url==='/api/cvs/'&&defer?new Promise(resolve=>{finish=resolve;}):null});await h.load();
    const old=[...h.saved.values()].map(clone);defer=true;const list=h.load();
    await h.action('delete');await h.click('deleteConfirm');
    finish({ok:true,status:200,json:async()=>({results:old,next:null})});await list;
    assert.equal(h.get('summaryTotal').textContent,1);assert.equal(h.get('cardsGrid').children.length,1);
});

test('history pagination appends older versions and rejects external pagination URLs',async()=>{
    let external=false;
    const h=harness({fetch:url=>url.includes('/versions/')?{ok:true,status:200,json:async()=>url.includes('page=2')?{results:[{version:1,name:'Original',created_at:'2026-10-12T10:00:00Z'}],next:null}:{results:[{version:2,name:'Updated',created_at:'2026-10-13T10:00:00Z'}],next:external?'https://example.com/api/cvs/12/versions/?page=2':'/api/cvs/12/versions/?page=2'}}:null});
    await h.load();await h.action('versions');await h.click('versionsMore');assert.equal(h.get('versionsRows').children.length,2);
    assert.equal(h.get('versionsMore').classList.contains('hidden'),true);
    await h.click('versionsClose');external=true;await h.action('versions');await h.click('versionsMore');
    assert.equal(h.calls.filter(x=>x.url.startsWith('https://')).length,0);assert.match(h.get('versionsError').textContent,/Could not load/);
});

test('failed history reads can be retried without modifying the CV',async()=>{
    let failed=true;const h=harness({fetch:url=>url.includes('/versions/')&&failed?fail(500):null});await h.load();await h.action('versions');
    assert.equal(h.get('versionsMore').textContent,'Retry loading');failed=false;await h.click('versionsMore');
    assert.equal(h.get('versionsRows').children.length,2);assert.ok(h.calls.every(x=>x.method==='GET'));
});

test('Escape cancels deletion and Tab keeps focus in the confirmation dialog',async()=>{
    const h=harness();await h.load();await h.action('delete');
    for(const id of ['deleteCancel','deleteConfirm'])h.get(id).type='button';
    h.get('deleteModal').children=[h.get('deleteCancel'),h.get('deleteConfirm')];
    const listener=h.documentListeners.get('keydown')[0];
    listener({key:'Tab',shiftKey:true,preventDefault(){}});assert.equal(h.c.document.activeElement,h.get('deleteConfirm'));
    listener({key:'Escape',preventDefault(){},stopImmediatePropagation(){}});
    assert.equal(h.get('deleteModal').classList.contains('hidden'),true);assert.equal(h.calls.filter(x=>x.method==='DELETE').length,0);
});

test('repeated Create submissions produce one in-flight POST',async()=>{
    let finish;const h=harness({fetch:(url,options)=>url==='/api/cvs/'&&options.method==='POST'?new Promise(resolve=>{finish=resolve;}):null});
    h.get('cvName').value='CV';h.get('targetRole').value='Backend';h.get('careerLevel').value='fresher';h.get('templateId').value='modern';
    const request=h.run('handleCreateCV({preventDefault(){}})');await h.run('handleCreateCV({preventDefault(){}})');
    assert.equal(h.calls.filter(x=>x.method==='POST').length,1);finish({ok:true,status:201,json:async()=>sample(20)});await request;
});

test('repeated Duplicate clicks for the same CV produce one in-flight POST',async()=>{
    let finish;const h=harness({fetch:(url)=>url.endsWith('/duplicate/')?new Promise(resolve=>{finish=resolve;}):null});await h.load();
    const request=h.action('duplicate');await h.action('duplicate');assert.equal(h.calls.filter(x=>x.url.endsWith('/duplicate/')).length,1);
    const copied={...clone(h.saved.get(12)),id:20,name:'Copy'};h.saved.set(20,copied);finish({ok:true,status:201,json:async()=>copied});await request;
});

test('deleting a CV closes its active chat UI without deleting its chat session',async()=>{
    const h=harness();await h.load();h.run('chat.cvId=12;chat.session={id:"session-12",cv_id:12};');
    await h.action('delete');await h.click('deleteConfirm');assert.equal(h.run('chat.session'),null);
    assert.equal(h.get('chatModal').classList.contains('hidden'),true);assert.ok(h.calls.every(x=>!x.url.startsWith('/api/chat/')));
});

function completedChat(h) {
    h.run('chat.session={id:"11111111-1111-1111-1111-111111111111",cv_id:12,status:"completed",messages:[],conversation_state:{existing_cv_version:1}}');
}
const jsonResult=value=>({ok:true,status:200,json:async()=>clone(value)});
const draftResult=()=>({draft:sample(12).data,fingerprint:'a'.repeat(64),recommendations:[]});
const reviewResult=()=>({fingerprint:'a'.repeat(64),cached:false,result:{overall_feedback:'Clear CV',suggestions:[],missing_information:[],warnings:[],proposed_changes:[{path:'/summary',original:'Original',replacement:'Improved',reason:'Clarity'}]}});

test('chat draft can be inspected without an external AI call',async()=>{
    const h=harness({fetch:url=>url.endsWith('/draft/')?jsonResult(draftResult()):null});completedChat(h);
    await h.click('chatDraft');
    assert.equal(h.calls.length,1);assert.ok(h.calls[0].url.endsWith('/draft/'));
    assert.equal(h.get('chatDraftPanel').classList.contains('hidden'),false);
    assert.equal(h.get('chatExternalApproval').checked,false);
    assert.equal(h.run('chat.draft.fingerprint'),'a'.repeat(64));
});

test('final Gemini review requires the consent checkbox',async()=>{
    const h=harness();completedChat(h);h.run('chat.draft={fingerprint:"draft"}');
    await h.click('chatFinalReview');
    assert.equal(h.calls.length,0);assert.match(h.get('chatReviewStatus').textContent,/approve external processing/);
});

test('final review sends consent and fingerprint without saving changes',async()=>{
    const h=harness({fetch:url=>url.endsWith('/final-review/')?jsonResult(reviewResult()):null});completedChat(h);
    h.run('chat.draft={fingerprint:"'+'a'.repeat(64)+'"}');h.get('chatExternalApproval').checked=true;
    await h.click('chatFinalReview');
    assert.deepEqual(h.calls[0].body,{approved_external_processing:true,fingerprint:'a'.repeat(64)});
    assert.ok(h.calls.every(c=>!c.url.startsWith('/api/cvs/')));
    assert.equal(h.get('chatReviewSuggestions').children[1].children[0].checked,undefined);
    assert.equal(h.get('chatApplyReview').classList.contains('hidden'),false);
});

test('approving selected changes submits only server proposal indexes',async()=>{
    const h=harness({fetch:url=>url.endsWith('/decisions/')?jsonResult({approved_changes:[{}]}):null});completedChat(h);
    h.run('chat.review={fingerprint:"'+'a'.repeat(64)+'"}');
    h.get('chatReviewSuggestions').querySelectorAll=()=>[{checked:true,dataset:{reviewIndex:'0'}},{checked:false,dataset:{reviewIndex:'1'}}];
    await h.click('chatApplyReview');
    assert.deepEqual(h.calls[0].body,{fingerprint:'a'.repeat(64),accepted_indexes:[0]});
    assert.match(h.get('chatReviewStatus').textContent,/Save your CV/);
});

test('reject all leaves no approved wording changes',async()=>{
    const h=harness({fetch:url=>url.endsWith('/decisions/')?jsonResult({approved_changes:[]}):null});completedChat(h);
    h.run('chat.review={fingerprint:"'+'a'.repeat(64)+'"}');
    await h.click('chatDiscardReview');assert.deepEqual(h.calls[0].body.accepted_indexes,[]);
    assert.match(h.get('chatReviewStatus').textContent,/rejected/);
});

test('Gemini failure leaves save enabled and offers save without review',async()=>{
    const h=harness({fetch:url=>url.endsWith('/final-review/')?fail(502):null});completedChat(h);
    h.run('chat.draft={fingerprint:"draft"}');h.get('chatExternalApproval').checked=true;
    await h.click('chatFinalReview');assert.equal(h.get('chatSave').disabled,false);
    assert.match(h.get('chatReviewStatus').textContent,/save your CV without/);
});

test('saved-CV chat supplies the version originally reviewed rather than a newer version',async()=>{
    const h=harness({fetch:url=>url==='/api/cvs/from-chat/'?fail(409):null});completedChat(h);
    h.saved.get(12).version=4;
    await h.click('chatSave');
    assert.equal(h.calls.find(c=>c.url==='/api/cvs/from-chat/').body.expected_version,1);
    assert.match(h.get('chatSaveStatus').textContent,/saved CV changed/);
});

test('completed collected draft can be reopened for corrections without a provider call',async()=>{
    const h=harness({fetch:url=>url.endsWith('/reopen/')?jsonResult({id:'11111111-1111-1111-1111-111111111111',cv_id:12,status:'active',current_section:'review',messages:[]}):null});
    completedChat(h);await h.click('chatReopen');
    assert.equal(h.run('chat.session.status'),'active');assert.equal(h.get('chatInput').disabled,false);
    assert.ok(h.calls.every(c=>c.url.endsWith('/reopen/')));
});

test('retrying an ambiguous message keeps the same idempotency receipt',async()=>{
    let posts=0,ids=0;
    const session={id:'11111111-1111-1111-1111-111111111111',cv_id:12,status:'active',current_section:'personal',messages:[],updated_at:'2026-10-16T10:00:00Z'};
    const h=harness({fetch:(url,options)=>url.startsWith('/api/chat/sessions/')
        ? options.method==='POST'
            ? (++posts===1?fail(502):jsonResult({assistant_message:'What email?',intent:'update_cv',section:'personal',cv_updates:{personal:{full_name:'Ali'}},next_action:'ask_question'}))
            :jsonResult(session)
        :null});
    h.c.window.crypto={randomUUID:()=>`00000000-0000-4000-8000-${String(++ids).padStart(12,'0')}`};
    h.run('chat.session='+JSON.stringify(session));h.get('chatInput').value='Ali';
    await h.run('sendChatMessage()');await h.run('sendChatMessage()');
    const sent=h.calls.filter(c=>c.method==='POST');assert.equal(sent.length,2);
    assert.equal(sent[0].body.request_id,sent[1].body.request_id);assert.equal(ids,1);
});

test('field validation appears once in the chat history without a duplicate error below',async()=>{
    const session={id:'11111111-1111-1111-1111-111111111111',cv_id:null,status:'active',current_section:'education',messages:[]};
    const message='Please enter a date as YYYY-MM, or a year if the month is unknown.';
    const h=harness({fetch:(url,options)=>url.startsWith('/api/chat/sessions/')
        ? jsonResult(options.method==='POST'
            ? {assistant_message:message,intent:'clarify_information',section:'education',cv_updates:{},next_action:'ask_question'}
            : {...session,messages:[{id:1,role:'user',content:'graduate'},{id:2,role:'assistant',content:message}]})
        :null});
    h.run('chat.session='+JSON.stringify(session));h.get('chatInput').value='graduate';
    await h.run('sendChatMessage()');
    assert.equal(h.get('chatError').classList.contains('hidden'),true);
    assert.equal(h.run('chat.session.messages.filter(m=>m.role==="assistant").length'),1);
    assert.equal(h.get('chatHistory').children.length,2);
});

test('provider errors remain visible below the chat and allow retry',async()=>{
    const h=harness({fetch:url=>url.endsWith('/messages/')?fail(502):null});
    h.run('chat.session={id:"11111111-1111-1111-1111-111111111111",status:"active",current_section:"education",messages:[]}');
    h.get('chatInput').value='I need help with these dates';await h.run('sendChatMessage()');
    assert.equal(h.get('chatError').classList.contains('hidden'),false);
    assert.equal(h.get('chatRetry').classList.contains('hidden'),false);
    assert.equal(h.get('chatInput').value,'I need help with these dates');
});
