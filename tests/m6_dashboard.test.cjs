const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const clone=value=>JSON.parse(JSON.stringify(value));
function sample(id=12) {
    const data=JSON.parse(fs.readFileSync('shared/examples/cv_draft.json','utf8'));
    data.meta={target_role:'Backend Developer',career_level:'fresher',template_id:'modern'};
    data.personal.full_name='Ali';data.summary='I develop Django APIs.';data.skills=['Python','Django'];
    data.projects=[{name:'CV Maker',description:'I made a CV maker.',technologies:['Django'],url:'',highlights:['Built REST APIs.']}];
    return {id,name:'Backend CV '+id,version:1,data};
}
const insights={valid:true,warnings:[{message:'Phone is missing.',section:'personal',severity:'high'}],suggestions:[{section:'summary',priority:'high',source:'ai',message:'Improve summary.',recommended_action:'Describe supported work.'}],strengths:['Python'],gaps:['Phone'],match_score:65};
function harness(overrides={}) {
    const elements=new Map(),calls=[],saved=new Map([[12,sample()],[13,sample(13)]]);
    const nodes=()=>{
        const classes=new Set(['hidden']);
        return {value:'',textContent:'',disabled:false,children:[],options:[],listeners:{},dataset:{},
            classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){if(on)classes.add(x);else classes.delete(x);}},
            addEventListener(name,fn){this.listeners[name]=fn;},appendChild(item){this.children.push(item);return item;},append(...items){this.children.push(...items);},
            replaceChildren(){this.children=[];this.options=[];this.value='';},add(option){this.options.push(option);if(this.options.length===1)this.value=option.value;},setAttribute(){},focus(){},click(){},
        };
    };
    const get=id=>{if(!elements.has(id))elements.set(id,nodes());return elements.get(id);};
    const storage=new Map([['cv_access','jwt']]);
    const window={location:{href:'http://localhost/dashboard/',origin:'http://localhost',search:''},history:{replaceState() {}}};
    const c=vm.createContext({window,console,URL,URLSearchParams,Headers,FormData,AbortController,setTimeout,clearTimeout,
        Option:function(text,value){this.text=text;this.value=value;},
        document:{getElementById:get,createElement:nodes,createTextNode:text=>text,addEventListener(){},querySelector:()=>null,body:{style:{}}},
        sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
        fetch:async(url,options)=>{
            assert.equal(options.headers.get('Authorization'),'Bearer jwt');
            const body=options.body && !(options.body instanceof FormData)?JSON.parse(options.body):null;
            calls.push({url,method:options.method||'GET',body});
            if(overrides.fetch){const response=await overrides.fetch(url,options,body);if(response)return response;}
            let result,status=200;
            const match=url.match(/^\/api\/cvs\/(\d+)\/$/);
            if(match){const id=Number(match[1]),cv=saved.get(id);if(options.method==='PATCH'){
                if(body.expected_version!==cv.version){status=409;result={error:{details:'CV changed'}};}
                else{cv.data=clone(body.data);cv.version++;result=cv;}
            }else result=cv;}
            else if(url==='/api/cvs/'){const cv={id:14,name:body.name,version:1,data:clone(body.data)};saved.set(14,cv);result=cv;}
            else if(url==='/api/templates/')result=[{id:'modern',name:'Modern'}];
            else if(url==='/api/ai/validate/')result={data:{...insights,suggestions:[],match_score:null}};
            else if(url==='/api/ai/rewrite/'||url==='/api/ai/improve/')result={data:{original:body.text,rewritten:'Developed Django APIs.',changes:['Improved wording']}};
            else if(url==='/api/ai/extract/')result={data:{cv:sample().data,warnings:[]}};
            else if(url.startsWith('/api/ai/'))result={data:insights};
            else if(url.startsWith('/api/cv-import/'))result={import_id:7,file_name:'CV.docx',file_type:'docx',file_size:500,status:'extracted',text:'Ali Khan\nPython Django Developer\nSkills: Python Django',error_message:''};
            else throw Error('Unexpected route '+url);
            return {status,ok:status<400,json:async()=>clone(result)};
        }
    });
    for(const file of ['dashboard','ai_api','ai_ui','ai_review','import_cv'])vm.runInContext(fs.readFileSync(`m9_dashboard/static/m9_dashboard/js/${file}.js`,'utf8'),c);
    vm.runInContext('window.M6Review.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}});window.M4Import.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}})',c);
    return {c,get,calls,saved,open:id=>vm.runInContext(`window.M6Review.open(${id})`,c),click:id=>get(id).listeners.click(),change:id=>get(id).listeners.input()};
}
const text=node=>node.textContent+' '+node.children.map(text).join(' ');

test('selection only loads M2; health check sends use_ai=false and complete JSON',async()=>{
    const h=harness();assert.equal(h.calls.length,0);await h.open(12);
    assert.deepEqual(h.calls.map(x=>x.url),['/api/cvs/12/']);
    await h.click('aiValidate');const call=h.calls.find(x=>x.url==='/api/ai/validate/');
    assert.equal(call.body.use_ai,false);assert.deepEqual(call.body.cv,h.saved.get(12).data);
    assert.match(h.get('aiStructure').textContent,/Valid.*Issues found: 1/);
    assert.equal(h.get('aiScore').textContent,'');
});

test('optimization uses full selected CV and suggestions reuse it without another AI call',async()=>{
    const h=harness();await h.open(13);h.get('aiRole').value='AI Engineer';h.change('aiRole');
    await h.click('aiOptimize');const call=h.calls.find(x=>x.url==='/api/ai/optimize/');
    assert.equal(call.body.target_role,'AI Engineer');assert.deepEqual(call.body.cv,h.saved.get(13).data);
    assert.equal(h.get('aiScore').textContent,'Role Alignment Score: 65/100');
    await h.click('aiViewSuggestions');await h.click('aiOptimize');
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,1);
    assert.match(text(h.get('aiSuggestions')),/Improve summary/);
});

test('duplicate Analyze clicks produce one in-flight request',async()=>{
    let finish;const h=harness({fetch:url=>url==='/api/ai/optimize/'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);const request=h.click('aiOptimize');
    while(!finish)await new Promise(resolve=>setImmediate(resolve));
    await h.click('aiOptimize');assert.equal(h.calls.filter(x=>x.url==='/api/ai/optimize/').length,1);
    finish({ok:true,status:200,json:async()=>({data:insights})});await request;
});

test('discard never writes; apply updates only selected field and invalidates results',async()=>{
    const h=harness();await h.open(12);const original=clone(h.saved.get(12).data);
    await h.click('aiOptimize');await h.click('aiRewrite');
    assert.equal(h.get('aiOriginal').value,original.summary);assert.equal(h.get('aiRewritten').value,'Developed Django APIs.');
    await h.click('aiDiscard');assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    h.get('aiField').value='1';h.get('aiField').listeners.change();
    await h.click('aiImprove');await h.click('aiApply');
    const updated=clone(original);updated.projects[0].description='Developed Django APIs.';
    assert.deepEqual(h.saved.get(12).data,updated);assert.equal(h.saved.get(12).version,2);
    assert.equal(h.get('aiAnalysis').classList.contains('hidden'),true);
    const patch=h.calls.find(x=>x.method==='PATCH');assert.equal(patch.body.expected_version,1);
});

test('version conflicts reload instead of overwriting another edit',async()=>{
    const h=harness();await h.open(12);await h.click('aiRewrite');
    h.saved.get(12).version=2;h.saved.get(12).data.personal.location='Islamabad';
    await h.click('aiApply');assert.equal(h.saved.get(12).data.personal.location,'Islamabad');
    assert.equal(h.saved.get(12).data.summary,'I develop Django APIs.');assert.match(h.get('aiError').textContent,/changed elsewhere/);
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
});

test('CV switching, content changes and target changes clear stale results',async()=>{
    const h=harness();await h.open(12);await h.click('aiOptimize');
    h.get('aiRole').value='Data Engineer';h.change('aiRole');assert.equal(h.get('aiAnalysis').classList.contains('hidden'),true);
    await h.click('aiOptimize');await h.open(13);assert.equal(h.get('aiAnalysis').classList.contains('hidden'),true);
    await h.click('aiOptimize');h.saved.get(13).version=2;h.saved.get(13).data.skills.push('Git');
    await h.click('aiOptimize');const last=h.calls.filter(x=>x.url==='/api/ai/optimize/').at(-1);assert.ok(last.body.cv.skills.includes('Git'));
});

test('late results from another CV are discarded',async()=>{
    let finish;const h=harness({fetch:url=>url==='/api/ai/optimize/'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);const request=h.click('aiOptimize');while(!finish)await new Promise(resolve=>setImmediate(resolve));
    await h.open(13);finish({ok:true,status:200,json:async()=>({data:insights})});await request;
    assert.equal(h.get('aiCVName').textContent,'Backend CV 13');assert.equal(h.get('aiAnalysis').classList.contains('hidden'),true);
});

test('provider errors show friendly messages and never save',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/optimize/'?{ok:false,status:503,json:async()=>({error:{message:'internal provider error'}})}:null});
    await h.open(12);await h.click('aiOptimize');assert.match(h.get('aiError').textContent,/temporarily unavailable/);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('import AI extraction is explicit; M2 creation only follows confirmation',async()=>{
    const h=harness();vm.runInContext('window.location.search="?import=7";window.M4Import.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}})',h.c);
    await vm.runInContext('window.M4Import.resume()',h.c);assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,0);
    await h.click('importParse');assert.match(text(h.get('importCVPreview')),/Ali/);
    assert.equal(h.calls.filter(x=>x.url==='/api/cvs/'&&x.method==='POST').length,0);
    await h.click('importDiscard');await h.click('importParse');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/extract/').length,1);
    await h.click('importConfirm');await h.click('importConfirm');
    assert.equal(h.calls.filter(x=>x.url==='/api/cvs/'&&x.method==='POST').length,1);
    assert.equal(h.saved.get(14).data.meta.template_id,'modern');assert.equal(h.get('importEditor').href,'/cvs/14/edit/');
});

test('missing score is never rendered as a fabricated quality score',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/optimize/'?{ok:true,status:200,json:async()=>({data:{...insights,match_score:null}})}:null});
    await h.open(12);await h.click('aiOptimize');assert.equal(h.get('aiScore').textContent,'No role alignment score provided.');
    assert.equal(h.get('aiEstimate').classList.contains('hidden'),true);
});

test('an unavailable CV is never sent to AI',async()=>{
    const h=harness({fetch:url=>url==='/api/cvs/12/'?{ok:false,status:404,json:async()=>({detail:'Not found'})}:null});
    await h.open(12);await h.click('aiOptimize');assert.match(h.get('aiError').textContent,/does not belong/);
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,0);
});

test('rewriting stops when another edit changes the saved document before generation',async()=>{
    const h=harness();await h.open(12);
    h.saved.get(12).version=2;h.saved.get(12).data.projects.reverse();
    await h.click('aiRewrite');assert.match(h.get('aiError').textContent,/changed elsewhere/);
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,0);
});
