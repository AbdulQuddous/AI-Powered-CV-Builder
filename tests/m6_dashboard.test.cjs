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
    const elements=new Map(),calls=[],saved=new Map([[12,sample()],[13,sample(13)]]),windowEvents=new Map();
    const nodes=()=>{
        const classes=new Set(['hidden']),attributes={};
        return {value:'',textContent:'',disabled:false,checked:false,children:[],options:[],listeners:{},dataset:{},
            classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){if(on)classes.add(x);else classes.delete(x);}},
            addEventListener(name,fn){this.listeners[name]=fn;},appendChild(item){this.children.push(item);return item;},append(...items){this.children.push(...items);},
            replaceChildren(...items){this.children=items;this.options=[];this.value='';},add(option){this.options.push(option);if(this.options.length===1)this.value=option.value;},
            setAttribute(name,value){attributes[name]=String(value);},getAttribute(name){return attributes[name]??null;},removeAttribute(name){delete attributes[name];},
            querySelectorAll(selector){return descendants(this).filter(item=>selector.startsWith('.')?String(item.className||'').split(' ').includes(selector.slice(1)):selector==='input[type="checkbox"]'?item.type==='checkbox':false);},
            getClientRects(){return classes.has('hidden')?[]:[{}];},focus(){},click(){return this.listeners.click?.();},
        };
    };
    const get=id=>{if(!elements.has(id))elements.set(id,nodes());return elements.get(id);};
    get('m9-cv-schema').textContent=fs.readFileSync('shared/schemas/cv_schema.json','utf8');
    const storage=new Map([['cv_access','jwt']]);
    const window={location:{href:'http://localhost/dashboard/',origin:'http://localhost',search:''},history:{replaceState() {}},addEventListener:(name,fn)=>windowEvents.set(name,fn)};
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
            else if(url==='/api/ai/tailor/'){
                const cv=saved.get(body.cv_id);
                result={data:{cv_id:cv.id,version:cv.version,summary:'Clearer wording across your CV.',changes:[
                    {path:'/summary',original:cv.data.summary,rewritten:'Developed Django APIs.',reason:'Use direct wording.'},
                    {path:'/projects/0/description',original:cv.data.projects[0].description,rewritten:'Developed a CV maker.',reason:'Clarify the project contribution.'}
                ],suggestions:['Only include skills you can support.'],cached:false}};
            }
            else if(url==='/api/ai/extract/')result={data:{cv:sample().data,warnings:[]}};
            else if(url.startsWith('/api/ai/'))result={data:insights};
            else if(url.startsWith('/api/cv-import/'))result={import_id:7,file_name:'CV.docx',file_type:'docx',file_size:500,status:'extracted',text:'Ali Khan\nPython Django Developer\nSkills: Python Django',error_message:''};
            else throw Error('Unexpected route '+url);
            return {status,ok:status<400,json:async()=>clone(result)};
        }
    });
    for(const file of ['dashboard','ai_api','ai_ui','ai_review','import_cv'])vm.runInContext(fs.readFileSync(`m9_dashboard/static/m9_dashboard/js/${file}.js`,'utf8'),c);
    vm.runInContext('window.M6Review.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}});window.M4Import.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}})',c);
    return {c,get,calls,saved,open:async id=>{
        await vm.runInContext(`window.M6Review.open(${id})`,c);
        get('aiJob').value='Build Django APIs.';
    },click:id=>get(id).listeners.click(),change:id=>get(id).listeners.input(),focus:()=>windowEvents.get('focus')?.()};
}
const text=node=>node.textContent+' '+(node.value || '')+' '+node.children.map(text).join(' ');
const find=(node,id)=>node.id===id?node:node.children.map(child=>find(child,id)).find(Boolean);

test('rewrite and improve preserve standalone payloads and forward only optional saved-field context',async()=>{
    for(const action of ['rewrite','improve']) {
        const h=harness();
        await vm.runInContext(`window.M6Api.create(apiFetch).${action}('Saved wording', 'summary', 'AI Developer', 'Build Django applications.')`,h.c);
        assert.deepEqual(h.calls[0].body,{text:'Saved wording',section:'summary',target_role:'AI Developer',job_description:'Build Django applications.'});
        await vm.runInContext(`window.M6Api.create(apiFetch).${action}('Saved wording', 'summary', 'AI Developer', 'Build Django applications.', {cv_id:12,expected_version:4,field_path:'/summary',cv:{personal:{email:'private@example.test'}}})`,h.c);
        assert.deepEqual(h.calls[1].body,{text:'Saved wording',section:'summary',target_role:'AI Developer',job_description:'Build Django applications.',cv_id:12,expected_version:4,field_path:'/summary'});
    }
});

test('an unreadable AI response offers retry without reporting a connection failure',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/tailor/'
        ? {ok:true,status:200,json:async()=>{throw new SyntaxError('Unexpected provider response');}}
        :null});
    await h.open(12);h.get('aiJob').value='Build Django APIs.';
    await h.click('aiTailor');
    assert.match(h.get('aiError').textContent,/usable suggestion/);
    assert.doesNotMatch(h.get('aiError').textContent,/connection/);
    assert.equal(h.get('aiRetry').classList.contains('hidden'),false);
    assert.equal(h.get('aiStatus').textContent,'');
    assert.equal(h.get('aiJob').value,'Build Django APIs.');
    assert.equal(h.saved.get(12).version,1);
});

test('server input errors explain how to fix the CV instead of suggesting a network retry',async()=>{
    const message='Add a summary, work highlight, project description or achievement before improving this CV.';
    const h=harness({fetch:url=>url==='/api/ai/tailor/'
        ? {ok:false,status:400,json:async()=>({error:{code:'invalid_ai_input',message}})}
        :null});
    await h.open(12);await h.click('aiTailor');
    assert.equal(h.get('aiError').textContent,message);
    assert.equal(h.get('aiRetry').classList.contains('hidden'),true);
    assert.equal(h.get('aiStatus').textContent,'');
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});
const descendants=node=>(node.children||[]).flatMap(child=>child&&typeof child==='object'?[child,...descendants(child)]:[]);
const changeChecks=h=>h.get('aiTailorChanges').querySelectorAll('.ai-change-check');

test('a partial review explains omitted suggestions and saves only the validated changes',async()=>{
    const warning='Some suggested changes were left out because they could not be verified against your CV.';
    const h=harness({fetch:(url,options,body)=>url==='/api/ai/tailor/'
        ? {ok:true,status:200,json:async()=>({data:{cv_id:12,version:1,summary:'Clearer wording.',
            changes:[{path:'/summary',original:sample().data.summary,rewritten:'Developed Django APIs.',reason:'Use direct wording.'}],
            suggestions:[],warnings:[warning],cached:false}})}
        :null});
    await h.open(12);const original=clone(h.saved.get(12).data);
    await h.click('aiTailor');
    assert.match(text(h.get('aiTailorWarnings')),/left out.*could not be verified/);
    assert.equal(h.get('aiError').classList.contains('hidden'),true);
    assert.equal(changeChecks(h).length,1);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    await h.click('aiApply');
    assert.deepEqual(h.saved.get(12).data,{...original,summary:'Developed Django APIs.'});
    assert.equal(h.saved.get(12).version,2);
});

test('AI validation failures explain the cause and retain the job inputs for retry',async()=>{
    for(const [reason,expected] of [['factual_validation',/could not be verified/],['response_truncated',/cut short/],
        ['response_invalid_json',/incomplete review/],['source_mismatch',/match its changes/]]) {
        const h=harness({fetch:url=>url==='/api/ai/tailor/'
            ? {ok:false,status:502,json:async()=>({error:{code:'ai_output_invalid',reason,message:'AI returned an invalid response.'}})}
            :null});
        await h.open(12);h.get('aiJob').value='Build Django APIs.';
        await h.click('aiTailor');
        assert.match(h.get('aiError').textContent,expected);
        assert.doesNotMatch(h.get('aiError').textContent,/connection/);
        assert.equal(h.get('aiRetry').classList.contains('hidden'),false);
        assert.equal(h.get('aiStatus').textContent,'');
        assert.equal(h.get('aiJob').value,'Build Django APIs.');
        assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    }
});

test('selection only loads M2; health check sends use_ai=false and complete JSON',async()=>{
    const h=harness();assert.equal(h.calls.length,0);await h.open(12);
    assert.deepEqual(h.calls.map(x=>x.url),['/api/cvs/12/']);
    await h.click('aiValidate');const call=h.calls.find(x=>x.url==='/api/ai/validate/');
    assert.equal(call.body.use_ai,false);assert.deepEqual(call.body.cv,h.saved.get(12).data);
    assert.match(h.get('aiStructure').textContent,/Valid.*Issues found: 1/);
    assert.equal(h.get('aiScore').textContent,'');
});

test('optional job-fit review uses full selected CV and reuses analysis',async()=>{
    const h=harness();await h.open(13);h.get('aiRole').value='AI Engineer';h.change('aiRole');
    await h.click('aiOptimize');const call=h.calls.find(x=>x.url==='/api/ai/optimize/');
    assert.equal(call.body.target_role,'AI Engineer');assert.deepEqual(call.body.cv,h.saved.get(13).data);
    assert.equal(h.get('aiScore').textContent,'Role Alignment Score: 65/100');
    await h.click('aiOptimize');
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
    await h.click('aiOptimize');await h.click('aiModePart');await h.click('aiRewrite');
    assert.equal(h.get('aiOriginal').value,original.summary);assert.equal(h.get('aiRewritten').value,'Developed Django APIs.');
    await h.click('aiDiscard');assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    h.get('aiField').value='1';h.get('aiField').listeners.change();
    await h.click('aiRewrite');await h.click('aiApply');
    const updated=clone(original);updated.projects[0].description='Developed Django APIs.';
    assert.deepEqual(h.saved.get(12).data,updated);assert.equal(h.saved.get(12).version,2);
    assert.equal(h.get('aiAnalysis').classList.contains('hidden'),true);
    const patch=h.calls.find(x=>x.method==='PATCH');assert.equal(patch.body.expected_version,1);
});

test('polish wording calls improve and saves only the explicitly approved field',async()=>{
    const h=harness();await h.open(12);await h.click('aiModePart');
    const original=clone(h.saved.get(12).data);
    h.get('aiJob').value='Develop and test Django APIs.';
    await h.click('aiImprove');
    const call=h.calls.find(x=>x.url==='/api/ai/improve/');
    assert.equal(call.body.text,original.summary);
    assert.equal(call.body.section,'summary');
    assert.equal(call.body.job_description,'Develop and test Django APIs.');
    assert.equal(call.body.cv_id,12);
    assert.equal(call.body.expected_version,1);
    assert.equal(call.body.field_path,'/summary');
    assert.match(h.get('aiReviewContext').textContent,/Review focus: Backend Developer.*Job description included/);
    assert.match(h.get('aiFieldHelp').textContent,/throughout your saved CV/);
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,0);
    assert.equal(h.saved.get(12).version,1);
    await h.click('aiApply');
    assert.deepEqual(h.saved.get(12).data,{...original,summary:'Developed Django APIs.'});
    assert.equal(h.saved.get(12).version,2);
});

test('polish retry retains the improve operation and disables duplicate actions',async()=>{
    let attempts=0,finish;
    const h=harness({fetch:url=>{
        if(url!=='/api/ai/improve/')return null;
        attempts++;
        return attempts===1?{ok:false,status:503,json:async()=>({error:{message:'Please retry.'}})}
            :new Promise(resolve=>{finish=resolve;});
    }});
    await h.open(12);await h.click('aiModePart');await h.click('aiImprove');
    assert.equal(h.get('aiRetry').classList.contains('hidden'),false);
    const retry=h.click('aiRetry');
    while(!finish)await new Promise(resolve=>setImmediate(resolve));
    assert.equal(h.get('aiImprove').disabled,true);
    assert.equal(h.get('aiRewrite').disabled,true);
    await h.click('aiImprove');
    assert.equal(attempts,2);
    finish({ok:true,status:200,json:async()=>({data:{rewritten:'Developed Django APIs.',changes:[]}})});
    await retry;
    assert.equal(h.get('aiImprove').disabled,false);
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,0);
    assert.equal(h.saved.get(12).version,1);
});

test('version conflicts reload instead of overwriting another edit',async()=>{
    const h=harness();await h.open(12);await h.click('aiModePart');await h.click('aiRewrite');
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

test('import review corrections are submitted to M2 without another AI call',async()=>{
    const h=harness();
    vm.runInContext('window.location.search="?import=7";window.M4Import.init({fetch:apiFetch,ai:window.M6Api.create(apiFetch),requireLogin,openModal,refresh:async()=>{}})',h.c);
    await vm.runInContext('window.M4Import.resume()',h.c);await h.click('importParse');
    const name=find(h.get('importCVPreview'),'importField-personal_full_name');
    name.value='Ali Corrected';name.listeners.input();
    const skills=find(h.get('importCVPreview'),'importField-skills');
    skills.value='Python\nDjango\nPostgreSQL';skills.listeners.input();
    h.get('importCVTitle').value='Corrected CV';h.get('importTemplate').value='modern';
    await h.click('importConfirm');
    const saved=h.calls.find(call=>call.url==='/api/cvs/'&&call.method==='POST');
    assert.equal(saved.body.data.personal.full_name,'Ali Corrected');
    assert.deepEqual(saved.body.data.skills,['Python','Django','PostgreSQL']);
    assert.equal(h.calls.filter(call=>call.url==='/api/ai/extract/').length,1);
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
    const h=harness();await h.open(12);await h.click('aiModePart');
    h.saved.get(12).version=2;h.saved.get(12).data.projects.reverse();
    await h.click('aiRewrite');assert.match(h.get('aiError').textContent,/changed elsewhere/);
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,0);
});

test('whole-CV mode is the clear default and selected-text rewriting is separate',async()=>{
    const h=harness();await h.open(12);
    assert.equal(h.get('aiWholeMode').classList.contains('hidden'),false);
    assert.equal(h.get('aiPartMode').classList.contains('hidden'),true);
    await h.click('aiModePart');
    assert.equal(h.get('aiWholeMode').classList.contains('hidden'),true);
    assert.equal(h.get('aiPartMode').classList.contains('hidden'),false);
    assert.equal(h.get('aiSource').value,h.saved.get(12).data.summary);
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,0);
});

test('whole-CV generation sends the saved version and JD without saving',async()=>{
    const h=harness();await h.open(12);const original=clone(h.saved.get(12));
    h.get('aiRole').value='Backend Developer';h.change('aiRole');
    h.get('aiJob').value='Build and maintain Django APIs.';h.change('aiJob');
    await h.click('aiTailor');
    const call=h.calls.find(x=>x.url==='/api/ai/tailor/');
    assert.deepEqual(call.body,{cv_id:12,expected_version:1,target_role:'Backend Developer',job_description:'Build and maintain Django APIs.'});
    assert.deepEqual(h.saved.get(12),original);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    assert.equal(h.get('aiWholeComparison').classList.contains('hidden'),false);
    assert.equal(h.get('aiSingleComparison').classList.contains('hidden'),true);
    assert.equal(changeChecks(h).length,2);assert.ok(changeChecks(h).every(node=>node.checked));
    assert.match(text(h.get('aiTailorChanges')),/Developed Django APIs/);
    assert.match(text(h.get('aiTailorChanges')),/Developed a CV maker/);
    assert.match(text(h.get('aiTailorSuggestions')),/Only include skills/);
});

test('whole-CV tailoring asks for the target role before requesting AI',async()=>{
    const h=harness();await h.open(12);h.get('aiRole').value='';h.change('aiRole');
    await h.click('aiTailor');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/tailor/').length,0);
    assert.equal(h.get('aiError').classList.contains('hidden'),false);
    assert.match(h.get('aiError').textContent,/role|job description/i);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('whole-CV tailoring requires a JD while single-part rewriting keeps it optional',async()=>{
    const h=harness();await h.open(12);h.get('aiJob').value='   ';h.change('aiJob');
    await h.click('aiTailor');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/tailor/').length,0);
    assert.match(h.get('aiError').textContent,/Paste the job description/);
    assert.equal(h.get('aiJob').getAttribute('aria-invalid'),'true');
    assert.equal(h.get('aiJob').getAttribute('aria-required'),'true');
    await h.click('aiModePart');
    assert.equal(h.get('aiJob').getAttribute('aria-required'),'false');
    await h.click('aiRewrite');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,1);
});

test('provider configuration, rejected requests and quota failures have useful safe messages',async()=>{
    for (const [reason, expected] of [['invalid_request',/could not accept the review request/],
        ['quota_exceeded',/Gemini request quota/], ['authentication_failed',/rejected the service credentials/],
        ['model_not_found',/configured Gemini model/], ['timeout',/took too long/]]) {
        const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:false,status:503,json:async()=>({error:{
            code:'ai_provider_unavailable',message:'secret raw provider message',reason}})}:null});
        await h.open(12);const original=clone(h.saved.get(12));await h.click('aiTailor');
        assert.match(h.get('aiError').textContent,expected);
        assert.doesNotMatch(h.get('aiError').textContent,/secret raw/);
        assert.equal(h.get('aiJob').value,'Build Django APIs.');
        assert.equal(h.get('aiRetry').classList.contains('hidden'),false);
        assert.deepEqual(h.saved.get(12),original);
    }
});

test('job requirements show supporting quotes and gaps without adding facts to saved CV',async()=>{
    const alignment=[{requirement:'Build Django APIs',status:'supported',evidence:[{path:'/summary',quote:sample().data.summary}]},
        {requirement:'Deploy with Kubernetes',status:'missing',evidence:[]}];
    const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:{
        cv_id:12,version:1,summary:'Emphasize API contributions.',changes:[{path:'/summary',original:sample().data.summary,
            rewritten:'Developed Django APIs.',reason:'Emphasizes the Django API requirement.'}],suggestions:['Confirm deployment experience if available.'],job_alignment:alignment,cached:false}})}:null});
    await h.open(12);const original=clone(h.saved.get(12).data);await h.click('aiTailor');
    assert.equal(h.get('aiJobAlignment').classList.contains('hidden'),false);
    assert.match(text(h.get('aiJobAlignment')),/CV evidence found.*Build Django APIs/);
    assert.match(text(h.get('aiJobAlignment')),/Not evidenced in your CV.*Deploy with Kubernetes/);
    assert.match(text(h.get('aiJobAlignment')),/I develop Django APIs/);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    await h.click('aiApply');
    assert.deepEqual(h.saved.get(12).data,{...original,summary:'Developed Django APIs.'});
    assert.equal(JSON.stringify(h.saved.get(12).data).includes('Kubernetes'),false);
    h.get('aiJob').value='New JD';h.change('aiJob');
    assert.equal(h.get('aiJobAlignment').classList.contains('hidden'),true);
});

test('omitted job-fit notes do not hide verified CV wording changes or allow facts to be inserted',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:{
        cv_id:12,version:1,summary:'One wording change.',job_alignment_warning:'Some job-fit notes could not be verified and were left out. Your saved CV is unchanged.',
        changes:[{path:'/summary',original:sample().data.summary,rewritten:'Developed Django APIs.',reason:'Clarifies the API work.'}],suggestions:[],cached:false}})}:null});
    await h.open(12);await h.click('aiTailor');
    assert.equal(h.get('aiError').classList.contains('hidden'),true);
    assert.equal(h.get('aiApply').disabled,false);
    assert.match(text(h.get('aiJobAlignment')),/job-fit notes.*left out/);
    assert.equal(changeChecks(h).length,1);
    await h.click('aiApply');
    assert.equal(h.saved.get(12).data.summary,'Developed Django APIs.');
    assert.equal(h.saved.get(12).data.job_alignment_warning,undefined);
});

test('one approval saves all selected whole-CV changes exactly once',async()=>{
    const h=harness();await h.open(12);const original=clone(h.saved.get(12).data);
    await h.click('aiTailor');await h.click('aiApply');await h.click('aiApply');
    const patches=h.calls.filter(x=>x.method==='PATCH');assert.equal(patches.length,1);
    const expected=clone(original);expected.summary='Developed Django APIs.';expected.projects[0].description='Developed a CV maker.';
    assert.deepEqual(patches[0].body,{data:expected,expected_version:1});
    assert.deepEqual(h.saved.get(12).data,expected);assert.equal(h.saved.get(12).version,2);
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
});

test('whole-CV review lets users leave an individual suggested change unchanged',async()=>{
    const h=harness();await h.open(12);const original=clone(h.saved.get(12).data);
    await h.click('aiTailor');const checks=changeChecks(h);
    checks[1].checked=false;checks[1].listeners.change();
    assert.match(h.get('aiApply').textContent,/1 change/);
    await h.click('aiApply');
    const expected=clone(original);expected.summary='Developed Django APIs.';
    assert.deepEqual(h.saved.get(12).data,expected);
    assert.equal(h.saved.get(12).data.projects[0].description,original.projects[0].description);
});

test('a whole-CV response with no wording changes offers no save action',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:{cv_id:12,version:1,summary:'Your wording is clear.',changes:[],suggestions:['Add only relevant verified details.'],cached:false}})}:null});
    await h.open(12);await h.click('aiTailor');
    assert.equal(h.get('aiApply').disabled,true);assert.equal(changeChecks(h).length,0);
    assert.match(text(h.get('aiTailorSummary')),/No wording changes were proposed.*saved CV is unchanged/);
    assert.equal(h.get('aiApply').classList.contains('hidden'),true);
    assert.equal(h.get('aiReviewState').textContent,'No changes to save');
    assert.equal(h.get('aiComparisonTitle').textContent,'Advice for your CV');
    await h.click('aiApply');assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('whole-CV discard and deselecting every suggestion never save',async()=>{
    const h=harness();await h.open(12);await h.click('aiTailor');
    for(const checkbox of changeChecks(h)){checkbox.checked=false;checkbox.listeners.change();}
    assert.equal(h.get('aiApply').disabled,true);await h.click('aiApply');
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    await h.click('aiDiscard');assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.equal(h.saved.get(12).version,1);
});

test('switching modes keeps each proposal and discard affects only the active choice',async()=>{
    const h=harness();await h.open(12);await h.click('aiTailor');
    const first=changeChecks(h)[0];first.checked=false;first.listeners.change();
    await h.click('aiModePart');await h.click('aiRewrite');await h.click('aiDiscard');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    await h.click('aiModeWhole');
    assert.equal(h.get('aiWholeComparison').classList.contains('hidden'),false);
    assert.equal(changeChecks(h)[0].checked,false);assert.match(h.get('aiApply').textContent,/1 change/);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('selected-text rewrite uses the same job description and changes just that field',async()=>{
    const h=harness();await h.open(12);const original=clone(h.saved.get(12).data);
    await h.click('aiModePart');h.get('aiJob').value='Maintain Django REST APIs.';h.change('aiJob');
    h.get('aiField').value='1';h.get('aiField').listeners.change();await h.click('aiRewrite');
    const call=h.calls.find(x=>x.url==='/api/ai/rewrite/');
    assert.deepEqual(call.body,{text:original.projects[0].description,section:'projects',target_role:'Backend Developer',job_description:'Maintain Django REST APIs.',cv_id:12,expected_version:1,field_path:'/projects/0/description'});
    assert.match(h.get('aiReviewContext').textContent,/Review focus: Backend Developer.*Job description included/);
    assert.match(h.get('aiFieldHelp').textContent,/selected entry/);
    assert.equal(h.get('aiSingleComparison').classList.contains('hidden'),false);
    assert.equal(h.get('aiWholeComparison').classList.contains('hidden'),true);
    await h.click('aiApply');const expected=clone(original);expected.projects[0].description='Developed Django APIs.';
    assert.deepEqual(h.saved.get(12).data,expected);
});

test('a selected work bullet sends its saved entry location without including unrelated CV data',async()=>{
    const h=harness();
    h.saved.get(12).version=4;
    h.saved.get(12).data.experience=[{company:'Example Systems',job_title:'Developer',highlights:['Built Django endpoints.']}];
    await h.open(12);await h.click('aiModePart');
    const option=h.get('aiField').options.find(item=>item.text==='Example Systems — bullet 1');
    assert.ok(option);h.get('aiField').value=option.value;h.get('aiField').listeners.change();
    h.get('aiRole').value='Full Stack AI Developer';h.change('aiRole');
    h.get('aiJob').value='Build reliable Django APIs and AI features.';h.change('aiJob');
    await h.click('aiRewrite');
    assert.deepEqual(h.calls.find(item=>item.url==='/api/ai/rewrite/').body,{
        text:'Built Django endpoints.',section:'experience',target_role:'Full Stack AI Developer',
        job_description:'Build reliable Django APIs and AI features.',cv_id:12,expected_version:4,field_path:'/experience/0/highlights/0'});
    assert.match(h.get('aiFieldHelp').textContent,/selected entry/);
    assert.match(h.get('aiReviewContext').textContent,/Full Stack AI Developer.*Saved CV target: Backend Developer/);
    assert.equal(h.calls.filter(item=>item.method==='PATCH').length,0);
});

test('changing target role or JD invalidates both part and whole-CV proposals before saving',async()=>{
    for(const input of ['aiRole','aiJob']) {
        const h=harness();await h.open(12);await h.click('aiTailor');
        await h.click('aiModePart');await h.click('aiRewrite');
        h.get(input).value='Changed job requirements';h.change(input);
        assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
        assert.equal(h.get('aiReviewContext').classList.contains('hidden'),true);
        assert.equal(h.get('aiApply').disabled,true);
        await h.click('aiApply');await h.click('aiModeWhole');
        assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
        await h.click('aiApply');
        assert.equal(h.calls.filter(item=>item.method==='PATCH').length,0);
        assert.equal(h.saved.get(12).version,1);
    }
});

test('a part response for a different original cannot become an approved change',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/rewrite/'?{ok:true,status:200,json:async()=>({data:{
        original:'Another field or previous version.',rewritten:'Developed Django APIs.',changes:[]}})}:null});
    await h.open(12);await h.click('aiModePart');await h.click('aiRewrite');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.equal(h.get('aiApply').disabled,true);
    assert.equal(h.get('aiError').classList.contains('hidden'),false);
    await h.click('aiApply');assert.equal(h.calls.filter(item=>item.method==='PATCH').length,0);
});

test('a part response cannot be offered for job details that changed while it was in flight',async()=>{
    let finish;
    const h=harness({fetch:url=>url==='/api/ai/rewrite/'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);await h.click('aiModePart');const request=h.click('aiRewrite');
    while(!finish)await new Promise(resolve=>setImmediate(resolve));
    h.get('aiJob').value='A different job description.';
    finish({ok:true,status:200,json:async()=>({data:{original:sample().data.summary,rewritten:'Developed Django APIs.',changes:[]}})});
    await request;
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.equal(h.get('aiApply').disabled,true);
    await h.click('aiApply');assert.equal(h.calls.filter(item=>item.method==='PATCH').length,0);
});

test('changing the target clears a whole-CV proposal before approval',async()=>{
    const h=harness();await h.open(12);await h.click('aiTailor');
    h.get('aiJob').value='A different job description.';h.change('aiJob');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);assert.equal(h.get('aiApply').disabled,true);
    await h.click('aiApply');assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('whole-CV save conflicts preserve the newer document and require regeneration',async()=>{
    const h=harness();await h.open(12);await h.click('aiTailor');
    h.saved.get(12).version=2;h.saved.get(12).data.personal.location='Islamabad';
    await h.click('aiApply');
    assert.equal(h.saved.get(12).data.personal.location,'Islamabad');
    assert.equal(h.saved.get(12).data.summary,'I develop Django APIs.');
    assert.equal(h.saved.get(12).data.projects[0].description,'I made a CV maker.');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.match(h.get('aiError').textContent,/changed elsewhere/);
});

test('whole-CV duplicate clicks make one request and late results cannot follow a CV switch',async()=>{
    let finish;const h=harness({fetch:url=>url==='/api/ai/tailor/'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);const request=h.click('aiTailor');while(!finish)await new Promise(resolve=>setImmediate(resolve));
    await h.click('aiTailor');assert.equal(h.calls.filter(x=>x.url==='/api/ai/tailor/').length,1);
    await h.open(13);finish({ok:true,status:200,json:async()=>({data:{cv_id:12,version:1,summary:'Clearer CV.',changes:[{path:'/summary',original:'I develop Django APIs.',rewritten:'Developed Django APIs.',reason:'Clearer wording.'}],suggestions:[]}})});
    await request;
    assert.equal(h.get('aiCVName').textContent,'Backend CV 13');assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('an observed concurrent edit discards pending whole-CV generation',async()=>{
    let finish;const h=harness({fetch:url=>url==='/api/ai/tailor/'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);const request=h.click('aiTailor');while(!finish)await new Promise(resolve=>setImmediate(resolve));
    const updated=clone(h.saved.get(12));updated.version=2;updated.data.personal.location='Islamabad';
    vm.runInContext(`window.M6Review.observe(${JSON.stringify([updated])})`,h.c);
    finish({ok:true,status:200,json:async()=>({data:{cv_id:12,version:1,summary:'Clearer CV.',changes:[{path:'/summary',original:'I develop Django APIs.',rewritten:'Developed Django APIs.',reason:'Clearer wording.'}],suggestions:[]}})});
    await request;
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);assert.equal(h.get('aiApply').disabled,true);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('whole-CV responses with a wrong document or unsupported field cannot be applied',async()=>{
    const valid={cv_id:12,version:1,summary:'Clearer wording.',changes:[{path:'/summary',original:'I develop Django APIs.',rewritten:'Developed Django APIs.',reason:'Improve clarity.'}],suggestions:[]};
    const variants=[{...clone(valid),cv_id:13},{...clone(valid),version:2},
        {...clone(valid),changes:[{...valid.changes[0],path:'/personal/full_name'}]},
        {...clone(valid),changes:[{...valid.changes[0],original:'A different summary.'}]},
        {...clone(valid),changes:[...clone(valid.changes),...clone(valid.changes)]}];
    for(const result of variants){
        const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:result})}:null});
        await h.open(12);await h.click('aiTailor');
        assert.equal(h.get('aiError').classList.contains('hidden'),false);
        assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
        assert.equal(h.get('aiApply').disabled,true);await h.click('aiApply');
        assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    }
});

test('approved whole-CV saving is guarded against duplicate clicks while pending',async()=>{
    let finish;const h=harness({fetch:(url,options)=>options.method==='PATCH'?new Promise(resolve=>{finish=resolve;}):null});
    await h.open(12);await h.click('aiTailor');const saving=h.click('aiApply');
    while(!finish)await new Promise(resolve=>setImmediate(resolve));
    assert.ok(changeChecks(h).every(node=>node.disabled));
    await h.click('aiApply');assert.equal(h.calls.filter(x=>x.method==='PATCH').length,1);
    const updated=clone(h.saved.get(12));updated.version=2;updated.data.summary='Developed Django APIs.';updated.data.projects[0].description='Developed a CV maker.';
    finish({ok:true,status:200,json:async()=>updated});await saving;
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
});

test('whole-CV errors use one visible message and retry the failed action without saving',async()=>{
    let failures=0;const h=harness({fetch:url=>url==='/api/ai/tailor/'&&failures++===0?{ok:false,status:503,json:async()=>({error:{message:'provider unavailable'}})}:null});
    await h.open(12);h.get('aiJob').value='Django API development';h.change('aiJob');await h.click('aiTailor');
    assert.match(h.get('aiError').textContent,/temporarily unavailable/);assert.equal(h.get('aiError').classList.contains('hidden'),false);
    assert.equal(h.get('aiStatus').textContent,'');assert.equal(h.get('aiStatus').classList.contains('hidden'),true);
    assert.equal(h.get('aiRetry').classList.contains('hidden'),false);await h.click('aiRetry');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/tailor/').length,2);
    assert.equal(h.get('aiError').classList.contains('hidden'),true);assert.equal(h.get('aiComparison').classList.contains('hidden'),false);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('reloading a changed CV retains job details and clears the stale proposal',async()=>{
    const h=harness();await h.open(12);h.get('aiRole').value='Python Engineer';h.change('aiRole');
    h.get('aiJob').value='Develop Django APIs';h.change('aiJob');await h.click('aiTailor');
    h.saved.get(12).version=2;h.saved.get(12).data.personal.location='Islamabad';
    await h.click('aiReload');
    assert.equal(h.get('aiRole').value,'Python Engineer');assert.equal(h.get('aiJob').value,'Develop Django APIs');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
});

test('partial review shows per-field omission reasons and an accurate ready count',async()=>{
    const warning='Some suggested changes were left out because they could not be verified against your CV.';
    const h=harness({fetch:url=>url==='/api/ai/tailor/'
        ? {ok:true,status:200,json:async()=>({data:{cv_id:12,version:1,summary:'1 wording change passed the checks.',
            changes:[{path:'/summary',original:sample().data.summary,rewritten:'Developed Django APIs.',reason:'Clarify wording.'}],suggestions:[],
            warnings:[warning,'Work experience 1, bullet 3: excluded because a number changed. Original wording kept.',
                'Project 1, description: excluded because the suggestion changed your stated responsibility. Original wording kept.'],cached:false}})}:null});
    await h.open(12);await h.click('aiTailor');
    assert.match(text(h.get('aiTailorWarnings')),/Why 2 suggestions were left out/);
    assert.match(text(h.get('aiTailorWarnings')),/Work experience 1, bullet 3/);
    assert.match(text(h.get('aiTailorWarnings')),/stated responsibility/);
    assert.match(h.get('aiStatus').textContent,/1 wording change is ready.*Other suggestions were left out/);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});

test('window focus is rate limited while explicit AI requests always check the saved CV',async()=>{
    const h=harness();vm.runInContext('Date.now = () => 1000000',h.c);
    await h.open(12);await h.focus();await h.focus();
    assert.equal(h.calls.filter(x=>x.url==='/api/cvs/12/').length,1);
    vm.runInContext('Date.now = () => 1060001',h.c);await h.focus();await h.focus();
    assert.equal(h.calls.filter(x=>x.url==='/api/cvs/12/').length,2);
    await h.click('aiTailor');
    assert.equal(h.calls.filter(x=>x.url==='/api/cvs/12/').length,3);
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/tailor/').length,1);
    assert.match(h.get('aiStatus').textContent,/2 wording changes are ready/);
    await h.focus();assert.equal(h.calls.filter(x=>x.url==='/api/cvs/12/').length,3);
});

test('focus recheck clears stale proposals and explains a changed CV without overwriting it',async()=>{
    const h=harness();vm.runInContext('Date.now = () => 1000000',h.c);
    await h.open(12);h.get('aiJob').value='Build reliable Django APIs.';await h.click('aiTailor');
    h.saved.get(12).version=2;h.saved.get(12).data.summary='Updated elsewhere.';
    vm.runInContext('Date.now = () => 1060001',h.c);await h.focus();
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.match(h.get('aiStatus').textContent,/saved CV changed.*Previous suggestions were cleared/);
    assert.equal(h.get('aiJob').value,'Build reliable Django APIs.');
    assert.equal(h.saved.get(12).data.summary,'Updated elsewhere.');
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,1);
});

test('reported advice-only review hides copied CV text and allows explicit polishing without an automatic call',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:{
        cv_id:12,version:1,summary:sample().data.summary,changes:[],
        suggestions:['Mention cloud experience only if you have it.'],cached:true}})}:null});
    await h.open(12);h.get('aiRole').value='DevOps Engineer';h.change('aiRole');await h.click('aiTailor');
    assert.equal(h.get('aiApply').classList.contains('hidden'),true);
    assert.equal(h.get('aiApply').disabled,true);
    assert.doesNotMatch(h.get('aiApply').textContent,/Save 0/);
    assert.equal(h.get('aiPolishPart').classList.contains('hidden'),false);
    assert.match(h.get('aiReviewContext').textContent,/Review focus: DevOps Engineer.*Saved CV target: Backend Developer/);
    assert.equal(h.get('aiReviewCache').classList.contains('hidden'),false);
    assert.doesNotMatch(h.get('aiTailorSummary').textContent,/I develop Django APIs/);
    assert.match(h.get('aiTailorSummary').textContent,/saved CV is unchanged/);
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,1);
    await h.click('aiPolishPart');
    assert.equal(h.get('aiModePart').getAttribute('aria-selected'),'true');
    assert.equal(h.get('aiSource').value,sample().data.summary);
    assert.equal(h.calls.filter(x=>x.url.startsWith('/api/ai/')).length,1);
    await h.click('aiRewrite');
    assert.equal(h.calls.filter(x=>x.url==='/api/ai/rewrite/').length,1);
    assert.equal(h.get('aiApply').classList.contains('hidden'),false);
    assert.equal(h.get('aiApply').textContent,'Save this change');
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
    await h.click('aiApply');
    assert.equal(h.saved.get(12).data.summary,'Developed Django APIs.');
    assert.equal(h.saved.get(12).data.meta.target_role,'Backend Developer');
    assert.equal(h.saved.get(12).version,2);
});

test('closing advice-only review never writes or hides the target inputs',async()=>{
    const h=harness({fetch:url=>url==='/api/ai/tailor/'?{ok:true,status:200,json:async()=>({data:{
        cv_id:12,version:1,summary:'Already clear.',changes:[],suggestions:[],cached:false}})}:null});
    await h.open(12);h.get('aiJob').value='Graduate software development';await h.click('aiTailor');
    assert.equal(h.get('aiReviewCache').classList.contains('hidden'),true);
    assert.equal(h.get('aiDiscard').textContent,'Close review');
    await h.click('aiDiscard');
    assert.equal(h.get('aiComparison').classList.contains('hidden'),true);
    assert.equal(h.get('aiJob').value,'Graduate software development');
    assert.match(h.get('aiStatus').textContent,/Review closed.*saved CV is unchanged/);
    assert.equal(h.calls.filter(x=>x.method==='PATCH').length,0);
});
