var X=Object.defineProperty,Y=Object.defineProperties;var q=Object.getOwnPropertyDescriptors;var _=Object.getOwnPropertySymbols;var J=Object.prototype.hasOwnProperty,Z=Object.prototype.propertyIsEnumerable;var A=(e,n,t)=>n in e?X(e,n,{enumerable:!0,configurable:!0,writable:!0,value:t}):e[n]=t,M=(e,n)=>{for(var t in n||(n={}))J.call(n,t)&&A(e,t,n[t]);if(_)for(var t of _(n))Z.call(n,t)&&A(e,t,n[t]);return e},D=(e,n)=>Y(e,q(n));var T=Object.defineProperty,S=(e,n)=>{let t={};for(var s in e)T(t,s,{get:e[s],enumerable:!0});return n||T(t,Symbol.toStringTag,{value:"Module"}),t};var v=S({addDataSourcesListener:()=>ne,addDimensionsListener:()=>ie,addDrilldownListener:()=>he,addErrorListener:()=>ge,addModeListener:()=>de,addOptionsListener:()=>oe,addThemeListener:()=>ce,addTokensListener:()=>ue,clearError:()=>ve,getDataSources:()=>te,getDimensions:()=>ae,getError:()=>xe,getMode:()=>le,getOptions:()=>se,getTheme:()=>pe,getTokens:()=>fe,setError:()=>be,setOptions:()=>re,triggerDrilldown:()=>me}),ee=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),O,i=(O=globalThis.DashboardExtensionAPI)!=null?O:ee,ne=i.addDataSourcesListener,te=i.getDataSources,oe=i.addOptionsListener,se=i.getOptions,re=i.setOptions,ie=i.addDimensionsListener,ae=i.getDimensions,de=i.addModeListener,le=i.getMode,ce=i.addThemeListener,pe=i.getTheme,ue=i.addTokensListener,fe=i.getTokens,he=i.addDrilldownListener,me=i.triggerDrilldown,ge=i.addErrorListener,xe=i.getError,be=i.setError,ve=i.clearError;var ye=/^\D+(\d+(?:\/\d+)+)/,R=/^(Ethernet|eth)\d/i;function C(e){let n=ye.exec(e!=null?e:"");if(!n)return null;let t=n[1].split("/").map(Number);if(t.length>3)return null;let[s,a,c]=t;return t.length===2?{member:s,module:0,port:a,lane:null}:R.test(e)?{member:s,module:0,port:a,lane:c}:{member:s,module:a,port:c,lane:null}}var $e=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function j(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let n=C(e.interface),t=!!n&&(n.module!==0||R.test(e.interface)||$e.test(e.interface)),s=Number(e.speed)>=(t?1e10:1e9);return(t?"fibre":"copper")+(s?"":"-slow")}function F(e){return e.poe_state==="deny"?"deny":e.poe_state==="ok"&&Number(e.poe_w)>0?"on":null}var N=e=>e*30+Math.floor(e/6)*18,I=e=>Math.floor((e-1)/2),ze=e=>e%2===1?0:44;function B(e){let n=new Map,t=0;e.forEach((g,u)=>{let p=C(g.interface);if(!p){t+=1;return}n.has(p.member)||n.set(p.member,[]),n.get(p.member).push(D(M({},p),{index:u}))});let s=[],a=[],c=[],d=0,l=0;return[...n.keys()].sort((g,u)=>g-u).forEach(g=>{let u=new Map;n.get(g).forEach(r=>{let h=`${r.module}:${r.port}`;u.has(h)||u.set(h,{module:r.module,port:r.port,ports:[]}),u.get(h).ports.push(r)});let p=new Map;u.forEach(r=>{p.has(r.module)||p.set(r.module,[]),p.get(r.module).push(r)});let o=d+16;c.push({text:`Switch ${g}`,x:0,y:d+11});let f=0;[...p.keys()].sort((r,h)=>r-h).forEach(r=>{r!==0&&c.push({text:`Module ${r}`,x:f,y:d+11});let h=0;p.get(r).forEach(x=>{let $=f+N(I(x.port)),z=o+ze(x.port);h=Math.max(h,N(I(x.port))+24),x.ports.length===1&&x.ports[0].lane===null?s.push({index:x.ports[0].index,x:$,y:z,size:24}):x.ports.forEach(L=>{var P;let k=(((P=L.lane)!=null?P:1)-1)%4;s.push({index:L.index,x:$+k%2*13,y:z+Math.floor(k/2)*13,size:11})}),a.push({text:String(x.port),x:$+24/2,y:z+34})}),f+=h+54,l=Math.max(l,f-54)}),d+=110}),{items:s,labels:a,heads:c,skipped:t,width:l,height:Math.max(d-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var G={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},E={on:"#f5d90a",deny:"#dc4e41"},w=[.7,0,.16,.58,.45,.58,.34,1,.86,.4,.56,.4],Ee=[["copper","Copper"],["copper-slow","Copper, reduced speed"],["fibre","Fibre"],["fibre-slow","Fibre, reduced speed"],["admin","Admin down"],["down","Down"]],H="#ff3b30",U=e=>(Number(e.in_errs)||0)+(Number(e.out_errs)||0),K={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},b=document.createElement("div");b.className="viz-container";(document.getElementById("root")||document.body).appendChild(b);var m={data:null,rows:[],loading:!1,theme:"dark"};function we(e){var a;let n=((e==null?void 0:e.fields)||[]).map(c=>{var d;return(d=c.name)!=null?d:c}),t=(e==null?void 0:e.columns)||[],s=((a=t[0])==null?void 0:a.length)||0;return Array.from({length:s},(c,d)=>Object.fromEntries(n.map((l,g)=>[l,t[g][d]])))}function Le(e){let n=Number(e);return n>0?n>=1e9?`${Math.round(n/1e9*10)/10} Gb/s`:`${Math.round(n/1e6)} Mb/s`:""}function ke(e){var s;let n=[e.interface,e.state||"down",Le(e.speed)];e.neighbour&&n.push(`CDP: ${e.neighbour}`);let t=Number(e.macs)||0;if(t>5?n.push(`${t} MACs`):t>0&&n.push(`MACs: ${e.mac_list}`),e.poe_state==="deny")n.push("PoE denied");else if(e.poe_state==="ok"&&e.poe_w!==""&&e.poe_w!=null){let a=Math.round(Number(e.poe_w)*10)/10;n.push(`PoE ${a} W${/^\d+$/.test((s=e.pd_class)!=null?s:"")?`, class ${e.pd_class}`:""}`)}return U(e)>0&&n.push(`Errors: ${Number(e.in_errs)||0} in, ${Number(e.out_errs)||0} out`),n.filter(Boolean).join(" \xB7 ")}function y(e){return String(e!=null?e:"").replace(/[&<>"']/g,n=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[n])}function Q(e,n,t){let s=t*.7,a=e+t*.15,c=n+t*.15,d=[];for(let l=0;l<w.length;l+=2)d.push(`${(a+w[l]*s).toFixed(2)},${(c+w[l+1]*s).toFixed(2)}`);return d.join(" ")}function Pe(e){let n=K[m.theme]||K.dark,t=B(e),s=t.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${n.muted}">${y(o.text)}</text>`).join(""),a=t.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${n.text}">${y(o.text)}</text>`).join(""),c=t.items.map(o=>{let f=e[o.index],r=F(f),h=r?`<polygon points="${Q(o.x,o.y,o.size)}" fill="${E[r]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`:"";return`<g class="viz-port" data-i="${o.index}"><title>${y(ke(f))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${G[j(f)]}" `+(U(f)>0?`stroke="${H}" stroke-width="2.5"`:`stroke="${n.outline}"`)+`/>${h}</g>`}).join(""),d=t.skipped?`<div class="viz-note" style="color:${n.muted}">${t.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",l=4,g=o=>`<span class="viz-swatch" style="background:${o};border-color:${n.outline}"></span>`,u=o=>`<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${Q(0,0,10)}" fill="${o}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`,p=`<div class="viz-legend" style="color:${n.muted}">`+Ee.map(([o,f])=>`<span>${g(G[o])}${f}</span>`).join("")+`<span>${u(E.on)}PoE</span><span>${u(E.deny)}PoE denied</span><span><span class="viz-swatch" style="border:2px solid ${H}"></span>Errors</span></div>`;b.innerHTML=`<svg class="viz-svg" viewBox="${-l} ${-l} ${t.width+2*l} ${t.height+2*l}" preserveAspectRatio="xMidYMid meet" role="img">`+s+c+a+"</svg>"+p+d,b.classList.remove("viz-container--empty")}function W(e){b.innerHTML=`<div class="viz-message">${y(e)}</div>`,b.classList.add("viz-container--empty")}function V(){if(m.loading)return W("Loading ports...");if(m.rows=m.data?we(m.data):[],m.rows.length===0)return W("No ports to show for this switch");Pe(m.rows)}b.addEventListener("click",e=>{let n=e.target.closest(".viz-port");if(!n)return;let t=m.rows[Number(n.dataset.i)];t&&v.triggerDrilldown({action:"point.click",payload:{name:"interface",value:t.interface,"click.name":"interface","click.value":t.interface,"row.interface.value":t.interface},originalEvent:e})});v.addDataSourcesListener(({dataSources:e,loading:n})=>{var t;m.loading=n,m.data=((t=e==null?void 0:e.primary)==null?void 0:t.data)||null,V()},{invokeImmediately:!0});v.addThemeListener(({theme:e})=>{m.theme=e,b.dataset.theme=e,V()},{invokeImmediately:!0});
