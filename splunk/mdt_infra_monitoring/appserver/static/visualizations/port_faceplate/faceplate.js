var de=Object.defineProperty,ce=Object.defineProperties;var pe=Object.getOwnPropertyDescriptors;var F=Object.getOwnPropertySymbols;var ue=Object.prototype.hasOwnProperty,fe=Object.prototype.propertyIsEnumerable;var N=(e,t,n)=>t in e?de(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,I=(e,t)=>{for(var n in t||(t={}))ue.call(t,n)&&N(e,n,t[n]);if(F)for(var n of F(t))fe.call(t,n)&&N(e,n,t[n]);return e},j=(e,t)=>ce(e,pe(t));var R=Object.defineProperty,C=(e,t)=>{let n={};for(var s in e)R(n,s,{get:e[s],enumerable:!0});return t||R(n,Symbol.toStringTag,{value:"Module"}),n};var k=C({addDataSourcesListener:()=>me,addDimensionsListener:()=>ye,addDrilldownListener:()=>Pe,addErrorListener:()=>De,addModeListener:()=>ze,addOptionsListener:()=>xe,addThemeListener:()=>we,addTokensListener:()=>Le,clearError:()=>Te,getDataSources:()=>ge,getDimensions:()=>$e,getError:()=>Oe,getMode:()=>ke,getOptions:()=>be,getTheme:()=>Ee,getTokens:()=>Me,setError:()=>Se,setOptions:()=>ve,triggerDrilldown:()=>_e}),he=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),B,l=(B=globalThis.DashboardExtensionAPI)!=null?B:he,me=l.addDataSourcesListener,ge=l.getDataSources,xe=l.addOptionsListener,be=l.getOptions,ve=l.setOptions,ye=l.addDimensionsListener,$e=l.getDimensions,ze=l.addModeListener,ke=l.getMode,we=l.addThemeListener,Ee=l.getTheme,Le=l.addTokensListener,Me=l.getTokens,Pe=l.addDrilldownListener,_e=l.triggerDrilldown,De=l.addErrorListener,Oe=l.getError,Se=l.setError,Te=l.clearError;var Ae=/^\D+(\d+(?:\/\d+)+)/,W=/^(Ethernet|eth)\d/,H={"PA-550":{ports:24,sfpFrom:17},"PA-560":{ports:24,sfpFrom:17}},M=e=>{let t=String(e!=null?e:"").trim();return Object.hasOwn(H,t)?H[t]:null},V=30,Y=18,P=54,$=24,L=11,Fe=44,q=34,Q=84,E=16,G=10;function _(e){let t=Ae.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[s,a,d]=n;return n.length===2?{member:s,module:0,port:a,lane:null}:W.test(e)?{member:s,module:0,port:a,lane:d}:{member:s,module:a,port:d,lane:null}}var Ne=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function U(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let t=_(e.interface),n=M(e.model),s=n?(t==null?void 0:t.port)>=n.sfpFrom:!!t&&(t.module!==0||W.test(e.interface)||Ne.test(e.interface)),a=Number(e.speed),d=!(a>0)||a>=(s?1e10:1e9);return(s?"fibre":"copper")+(d?"":"-slow")}function J(e){return e.poe_state==="deny"?"deny":e.poe_state==="ok"&&Number(e.poe_w)>0?"on":null}function Z(e,t,n=!1){let s=String(t!=null?t:"").trim();return s?n?`Switch ${e} \xB7 ${s}`:s:`Switch ${e}`}var X=e=>e*V+Math.floor(e/6)*Y,K=e=>Math.floor((e-1)/2),ee=e=>e%2===1?0:Fe;function te(e){let t=e.find(n=>M(n.model));return t?Ie(e,M(t.model),t.model):je(e)}function Ie(e,t,n){var m;let s=new Map,a=0;e.forEach((i,p)=>{let r=_(i.interface);r&&r.member===1&&r.module===0&&r.lane===null&&r.port>=1&&r.port<=t.ports?s.set(r.port,p):a+=1});let d=[],f=[],c=0;for(let i=1;i<=t.ports;i+=1){let p=Math.floor((i-1)/4),r=(2*p+Math.floor((i-1)%4/2))*V+p*Y+(i>=t.sfpFrom?P:0),x=E+ee(i);d.push({index:(m=s.get(i))!=null?m:null,port:i,x:r,y:x,size:$}),f.push({text:String(i),x:r+$/2,y:x+q}),c=Math.max(c,r+$)}return{items:d,labels:f,heads:[{text:Z(1,n),x:0,y:11}],skipped:a,width:c,height:Q+E}}function je(e){let t=new Map,n=new Map,s=0;e.forEach((i,p)=>{var x;let r=_(i.interface);if(!r){s+=1;return}t.has(r.member)||t.set(r.member,[]),t.get(r.member).push(j(I({},r),{index:p})),!n.has(r.member)&&String((x=i.model)!=null?x:"").trim()&&n.set(r.member,i.model)});let a=[],d=[],f=[],c=0,m=0;return[...t.keys()].sort((i,p)=>i-p).forEach(i=>{let p=new Map;t.get(i).forEach(u=>{let o=`${u.module}:${u.port}`;p.has(o)||p.set(o,{module:u.module,port:u.port,ports:[]}),p.get(o).ports.push(u)});let r=new Map;p.forEach(u=>{r.has(u.module)||r.set(u.module,[]),r.get(u.module).push(u)});let x=c+E;f.push({text:Z(i,n.get(i),t.size>1),x:0,y:c+11});let v=0;[...r.keys()].sort((u,o)=>u-o).forEach(u=>{let o=0;r.get(u).forEach(h=>{let y=v+X(K(h.port)),z=x+ee(h.port);o=Math.max(o,X(K(h.port))+$),h.ports.length===1&&h.ports[0].lane===null?a.push({index:h.ports[0].index,x:y,y:z,size:$}):h.ports.forEach(S=>{var A;let T=(((A=S.lane)!=null?A:1)-1)%4;a.push({index:S.index,x:y+T%2*(L+2),y:z+Math.floor(T/2)*(L+2),size:L})}),d.push({text:String(h.port),x:y+$/2,y:z+q})}),v+=o+P,m=Math.max(m,v-P)}),c+=Q+E+G}),{items:a,labels:d,heads:f,skipped:s,width:m,height:Math.max(c-G,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 8px 16px;
  font-family: "Splunk Platform Sans", sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.viz-container--empty {
  align-items: center;
}
.viz-svg {
  width: 100%;
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
}
.viz-port {
  cursor: pointer;
}
.viz-port:hover rect {
  stroke: #6ab0f9;
  stroke-width: 2;
}
.viz-message {
  padding: 20px;
  color: #8a929b;
}
.viz-note {
  font-size: 11px;
  text-align: center;
}
.viz-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 4px 14px;
  font-size: 11px;
  padding-top: 4px;
}
.viz-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.viz-legend .viz-swatch {
  width: 10px;
  height: 10px;
  border: 1px solid;
  border-radius: 2px;
}
.viz-legend-bolt {
  width: 14px;
  height: 14px;
}
`,document.head.appendChild(e)})();var ne={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},D={on:"#f5d90a",deny:"#dc4e41"},O=[.7,0,.16,.58,.45,.58,.34,1,.86,.4,.56,.4],Re=[["copper","Copper"],["copper-slow","Copper, reduced speed"],["fibre","Fibre"],["fibre-slow","Fibre, reduced speed"],["admin","Admin down"],["down","Down"]],oe="#ff3b30",ae=e=>(Number(e.in_errs)||0)+(Number(e.out_errs)||0),se={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},b=document.createElement("div");b.className="viz-container";(document.getElementById("root")||document.body).appendChild(b);var g={data:null,rows:[],loading:!1,theme:"dark"};function Ce(e){var a;let t=((e==null?void 0:e.fields)||[]).map(d=>{var f;return(f=d.name)!=null?f:d}),n=(e==null?void 0:e.columns)||[],s=((a=n[0])==null?void 0:a.length)||0;return Array.from({length:s},(d,f)=>Object.fromEntries(t.map((c,m)=>[c,n[m][f]])))}function Be(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function He(e){var s;let t=[e.interface,e.state||"down",Be(e.speed)];e.port_channel&&t.push(`Port-channel: ${e.port_channel}`),e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;if(n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),e.poe_state==="deny")t.push("PoE denied");else if(e.poe_state==="ok"&&e.poe_w!==""&&e.poe_w!=null){let a=Math.round(Number(e.poe_w)*10)/10;t.push(`PoE ${a} W${/^\d+$/.test((s=e.pd_class)!=null?s:"")?`, class ${e.pd_class}`:""}`)}return ae(e)>0&&t.push(`Errors: ${Number(e.in_errs)||0} in, ${Number(e.out_errs)||0} out`),t.filter(Boolean).join(" \xB7 ")}function w(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function re(e,t,n){let s=n*.7,a=e+n*.15,d=t+n*.15,f=[];for(let c=0;c<O.length;c+=2)f.push(`${(a+O[c]*s).toFixed(2)},${(d+O[c+1]*s).toFixed(2)}`);return f.join(" ")}function Ge(e){let t=se[g.theme]||se.dark,n=te(e),s=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${w(o.text)}</text>`).join(""),a=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${w(o.text)}</text>`).join(""),d=n.items.map(o=>{if(o.index==null)return`<g class="viz-port-empty"><title>${w(`Port ${o.port} \xB7 not configured`)}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="none" stroke="${t.outline}" stroke-width="1" stroke-dasharray="3 2"/></g>`;let h=e[o.index],y=J(h),z=y?`<polygon points="${re(o.x,o.y,o.size)}" fill="${D[y]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`:"";return`<g class="viz-port" data-i="${o.index}"><title>${w(He(h))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${ne[U(h)]}" `+(ae(h)>0?`stroke="${oe}" stroke-width="2.5"`:`stroke="${t.outline}"`)+`/>${z}</g>`}).join(""),f=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",c=7,m=28,i=14,p=35,r=`<rect x="${-m}" y="${-c}" width="${n.width+2*m}" height="${n.height+2*c}" rx="6" fill="none" stroke="${t.outline}" stroke-width="1.5"/>`,x=o=>`<span class="viz-swatch" style="background:${o};border-color:${t.outline}"></span>`,v=o=>`<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${re(0,0,10)}" fill="${o}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`,u=`<div class="viz-legend" style="color:${t.muted}">`+Re.map(([o,h])=>`<span>${x(ne[o])}${h}</span>`).join("")+`<span>${v(D.on)}PoE</span><span>${v(D.deny)}PoE denied</span><span><span class="viz-swatch" style="border:2px solid ${oe}"></span>Errors</span></div>`;b.innerHTML=`<svg class="viz-svg" viewBox="${-p} ${-i} ${n.width+2*p} ${n.height+2*i}" preserveAspectRatio="xMidYMid meet" role="img">`+r+s+d+a+"</svg>"+u+f,b.classList.remove("viz-container--empty")}function ie(e){b.innerHTML=`<div class="viz-message">${w(e)}</div>`,b.classList.add("viz-container--empty")}function le(){if(g.loading)return ie("Loading ports...");if(g.rows=g.data?Ce(g.data):[],g.rows.length===0)return ie("No ports to show for this switch");Ge(g.rows)}b.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=g.rows[Number(t.dataset.i)];n&&k.triggerDrilldown({action:"point.click",payload:{name:"interface",value:n.interface,"click.name":"interface","click.value":n.interface,"row.interface.value":n.interface},originalEvent:e})});k.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;g.loading=t,g.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,le()},{invokeImmediately:!0});k.addThemeListener(({theme:e})=>{g.theme=e,b.dataset.theme=e,le()},{invokeImmediately:!0});
