/* Native Jupyter complete_request; no dictionary derived from question answers. */
(() => {
  const doc = document;
  if (doc.__examCompletionCleanup) doc.__examCompletionCleanup();
  const selector = '.exam-complete input';
  const popup = doc.createElement('div');
  popup.id = 'exam-completion-menu';
  popup.setAttribute('role', 'listbox');
  popup.setAttribute('aria-label', 'Jupyter 内核补全候选');
  popup.style.cssText = 'display:none;position:fixed;z-index:100000;background:white;color:#203852;border:1px solid #8caef5;border-radius:6px;box-shadow:0 6px 22px #172b4726;min-width:230px;max-height:260px;overflow:auto;font:14px/1.5 ui-monospace,Consolas,monospace';
  doc.body.appendChild(popup);
  let input=null, matches=[], selected=-1, part=null, generation=0;
  let socket=null, socketKernel='', opening=null;
  const pending=new Map();
  const session=crypto.randomUUID();
  const target=e=>e.target instanceof HTMLInputElement && e.target.matches(selector) && !e.target.disabled ? e.target : null;
  const context=field=>field.closest('.exam-root')?.querySelector('.exam-context');
  function close(){
    generation++;
    if(input){input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
    popup.style.display='none'; input=null; matches=[]; selected=-1; part=null;
  }
  function position(){
    const r=input.getBoundingClientRect();
    popup.style.left=Math.max(4,Math.min(r.left,innerWidth-320))+'px';
    popup.style.top=(r.bottom+4)+'px';popup.style.display='block';
    input.setAttribute('role','combobox');input.setAttribute('aria-expanded','true');
    input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',popup.id);
  }
  function status(text){popup.replaceChildren();const row=doc.createElement('div');row.textContent=text;row.style.cssText='padding:10px;font:13px system-ui';popup.appendChild(row);position();}
  function paint(){
    popup.replaceChildren();
    matches.forEach((word,i)=>{
      const row=doc.createElement('div');row.id='exam-completion-option-'+i;
      row.setAttribute('role','option');row.setAttribute('aria-selected',String(i===selected));
      row.textContent=word;row.style.cssText='padding:6px 12px;cursor:pointer;background:'+(i===selected?'#dfebff':'white');
      row.addEventListener('mousedown',e=>{e.preventDefault();commit(i);});popup.appendChild(row);
    });
    const footer=doc.createElement('div');footer.textContent='Jupyter 内核 · ↑↓ 选择 · Tab / Enter 确认';
    footer.style.cssText='padding:7px 12px;font:12px system-ui;color:#66758c;border-top:1px solid #e2e8f0';popup.appendChild(footer);position();
    if(selected>=0){input.setAttribute('aria-activedescendant','exam-completion-option-'+selected);popup.children[selected].scrollIntoView({block:'nearest'});}
  }
  function failPending(){for(const {reject,timer} of pending.values()){clearTimeout(timer);reject(Error('内核连接已断开，请重新运行界面单元'));}pending.clear();}
  async function connect(kernel){
    if(socket && socketKernel===kernel && socket.readyState===WebSocket.OPEN)return socket;
    if(opening && socketKernel===kernel)return opening;
    if(socket)socket.close();
    socketKernel=kernel;
    let base='/';
    try{base=JSON.parse(doc.getElementById('jupyter-config-data')?.textContent||'{}').baseUrl||'/';}catch{}
    const url=new URL(base+'api/kernels/'+encodeURIComponent(kernel)+'/channels',location.origin);
    url.protocol=location.protocol==='https:'?'wss:':'ws:';url.searchParams.set('session_id',session);
    const ws=new WebSocket(url);socket=ws;
    opening=new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{ws.close();reject(Error('连接内核超时'));},7000);
      ws.onopen=()=>{clearTimeout(timer);resolve(ws);};
      ws.onerror=()=>{clearTimeout(timer);reject(Error('无法连接内核，请重新运行界面单元'));};
    });
    ws.onclose=()=>{if(socket===ws){opening=null;failPending();}};
    ws.onmessage=e=>{
      if(typeof e.data!=='string')return;
      let msg;try{msg=JSON.parse(e.data);}catch{return;}
      if(msg.header?.msg_type!=='complete_reply')return;
      const id=msg.parent_header?.msg_id,p= pending.get(id);if(!p)return;
      clearTimeout(p.timer);pending.delete(id);p.resolve(msg.content);
    };
    try{return await opening;}finally{opening=null;}
  }
  async function nativeCompletion(kernel,code){
    const ws=await connect(kernel),id=crypto.randomUUID();
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{pending.delete(id);reject(Error('补全超时；内核可能繁忙，稍后再按 Tab'));},8000);
      pending.set(id,{resolve,reject,timer});
      ws.send(JSON.stringify({header:{msg_id:id,username:'exam',session,msg_type:'complete_request',version:'5.3',date:new Date().toISOString()},parent_header:{},metadata:{},content:{code,cursor_pos:Array.from(code).length},channel:'shell',buffers:[]}));
    });
  }
  // Some source examples contain several blanks before the active one.  The
  // full snippet is the most faithful request; if its temporary placeholders
  // make the parser reject completion, ask once more with only the current
  // line. Both requests are Jupyter complete_request calls, never a local
  // answer dictionary. `offset` keeps reply positions mapped to this field.
  async function nativeCompletionWithFallback(kernel,code,offset){
    const utf16LineStart=code.lastIndexOf('\n')+1;
    // Protocol offsets count Unicode code points while slice() uses UTF-16;
    // convert the prefix explicitly so Chinese source text maps correctly.
    const lineStart=Array.from(code.slice(0,utf16LineStart)).length;
    const tries=[{code,offset},{code:code.slice(utf16LineStart),offset:offset-lineStart}];
    let fallback=null,lastError=null;
    for(const item of tries){
      try{
        const reply=await nativeCompletion(kernel,item.code);
        if(!fallback)fallback={reply,offset:item.offset};
        if(reply.status==='ok' && (reply.matches||[]).length)return {reply,offset:item.offset};
      }catch(e){lastError=e;}
    }
    if(fallback)return fallback;
    throw (lastError||Error('内核未能完成本次补全'));
  }
  async function show(field){
    close();input=field;const request= generation;
    const ctx=context(field),root=field.closest('.exam-root');
    const wrapper=field.closest('.exam-complete');
    const number=Number(Array.from(wrapper.classList).find(c=>/^exam-blank-\d+$/.test(c))?.split('-').pop());
    const caret=field.selectionStart,value=field.value;
    if(!ctx?.dataset.kernel){status('请在 JupyterLab 中运行本练习单元');return;}
    let code='',offset=0,found=false;
    const chunks=ctx.dataset.code.split(/(\{\{\d+\}\})/);
    for(const chunk of chunks){
      const marker=chunk.match(/^\{\{(\d+)\}\}$/);
      if(!marker){code+=chunk;continue;}
      const n=Number(marker[1]),other=root.querySelector('.exam-blank-'+n+' input');
      if(n===number){offset=Array.from(code).length;code+=value.slice(0,caret);found=true;break;}
      code+=other?.value.trim()?other.value:'__exam_blank_'+n;
    }
    if(!found){status('无法定位本空，请重新运行界面');return;}
    status('正在请求 Jupyter 内核候选…');
    try{
      const completion=await nativeCompletionWithFallback(ctx.dataset.kernel,code,offset);
      const reply=completion.reply;
      if(request!==generation || !field.isConnected || field.value!==value || field.selectionStart!==caret)return;
      if(reply.status!=='ok')throw Error('内核未能完成本次补全');
      // The protocol offsets count Unicode code points. Never replace surrounding fixed code.
      const start=reply.cursor_start-completion.offset,end=reply.cursor_end-completion.offset;
      if(start<0 || end<start || end>Array.from(value.slice(0,caret)).length){status('本候选跨越填空边界，请补全更多前文后重试');return;}
      const toUnits=n=>Array.from(value).slice(0,n).join('').length;
      const marker='{{'+number+'}}',at=ctx.dataset.code.indexOf(marker);
      part={start:toUnits(start),end:toUnits(end),fixedAfter:ctx.dataset.code.slice(at+marker.length)};
      matches=[...new Set(reply.matches||[])];selected=0;
      if(!matches.length){status('内核暂无候选；检查前文与对象类型，或手动填写');return;}
      const used=root.querySelector('.exam-assistance input[type=checkbox]');
      if(used && !used.checked)used.click();
      if(matches.length===1){commit(0);return;}paint();
    }catch(e){if(request===generation)status(e.message);}
  }
  function commit(i){
    if(!input||!part||!matches[i])return;
    const field=input,p=part;
    let word=matches[i];
    // Native parameter suggestions may include '='; the exam already supplies it.
    if(word.endsWith('=') && p.fixedAfter.trimStart().startsWith('='))word=word.slice(0,-1);
    const value=field.value.slice(0,p.start)+word+field.value.slice(p.end);
    close();field.value=value;field.setSelectionRange(p.start+word.length,p.start+word.length);
    field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));field.focus();
  }
  function onKey(e){
    const field=target(e);if(!field||e.isComposing||e.ctrlKey||e.metaKey||e.altKey)return;
    if(e.key==='Escape'){close();return;}
    if(e.key==='Tab'&&e.shiftKey){close();return;}
    if(input===field&&matches.length&&['ArrowUp','ArrowDown','Enter','Tab'].includes(e.key)){
      e.preventDefault();e.stopImmediatePropagation();
      if(e.key==='Enter'||e.key==='Tab')commit(selected);
      else{selected=(selected+(e.key==='ArrowUp'?-1:1)+matches.length)%matches.length;paint();}return;
    }
    if(e.key!=='Tab')return;
    if(context(field)?.dataset.completion!=='true'||!field.value.trim()||field.selectionStart!==field.selectionEnd){close();return;}
    if(input===field && !matches.length){close();return;}
    e.preventDefault();e.stopImmediatePropagation();show(field);
  }
  function onInput(e){if(target(e))close();}
  function onBlur(e){if(e.target===input)close();}
  function onOutside(e){if(input&&e.target!==input&&!popup.contains(e.target))close();}
  doc.addEventListener('keydown',onKey,true);doc.addEventListener('input',onInput,true);
  doc.addEventListener('focusout',onBlur,true);doc.addEventListener('mousedown',onOutside,true);
  window.addEventListener('resize',close);
  doc.__examCompletionCleanup=()=>{close();popup.remove();if(socket)socket.close();failPending();doc.removeEventListener('keydown',onKey,true);doc.removeEventListener('input',onInput,true);doc.removeEventListener('focusout',onBlur,true);doc.removeEventListener('mousedown',onOutside,true);window.removeEventListener('resize',close);};
})();
