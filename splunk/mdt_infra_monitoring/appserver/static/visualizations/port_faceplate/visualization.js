var X=Object.defineProperty,Y=Object.defineProperties;var q=Object.getOwnPropertyDescriptors;var _=Object.getOwnPropertySymbols;var J=Object.prototype.hasOwnProperty,Z=Object.prototype.propertyIsEnumerable;var A=(e,t,n)=>t in e?X(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,M=(e,t)=>{for(var n in t||(t={}))J.call(t,n)&&A(e,n,t[n]);if(_)for(var n of _(t))Z.call(t,n)&&A(e,n,t[n]);return e},D=(e,t)=>Y(e,q(t));var T=Object.defineProperty,S=(e,t)=>{let n={};for(var s in e)T(n,s,{get:e[s],enumerable:!0});return t||T(n,Symbol.toStringTag,{value:"Module"}),n};var v=S({addDataSourcesListener:()=>te,addDimensionsListener:()=>ie,addDrilldownListener:()=>he,addErrorListener:()=>ge,addModeListener:()=>de,addOptionsListener:()=>oe,addThemeListener:()=>ce,addTokensListener:()=>ue,clearError:()=>ve,getDataSources:()=>ne,getDimensions:()=>ae,getError:()=>xe,getMode:()=>le,getOptions:()=>se,getTheme:()=>pe,getTokens:()=>fe,setError:()=>be,setOptions:()=>re,triggerDrilldown:()=>me}),ee=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),O,r=(O=globalThis.DashboardExtensionAPI)!=null?O:ee,te=r.addDataSourcesListener,ne=r.getDataSources,oe=r.addOptionsListener,se=r.getOptions,re=r.setOptions,ie=r.addDimensionsListener,ae=r.getDimensions,de=r.addModeListener,le=r.getMode,ce=r.addThemeListener,pe=r.getTheme,ue=r.addTokensListener,fe=r.getTokens,he=r.addDrilldownListener,me=r.triggerDrilldown,ge=r.addErrorListener,xe=r.getError,be=r.setError,ve=r.clearError;var ye=/^\D+(\d+(?:\/\d+)+)/,R=/^(Ethernet|eth)\d/i;function C(e){let t=ye.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[s,a,c]=n;return n.length===2?{member:s,module:0,port:a,lane:null}:R.test(e)?{member:s,module:0,port:a,lane:c}:{member:s,module:a,port:c,lane:null}}var $e=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function j(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let t=C(e.interface),n=!!t&&(t.module!==0||R.test(e.interface)||$e.test(e.interface)),s=Number(e.speed)>=(n?1e10:1e9);return(n?"fibre":"copper")+(s?"":"-slow")}function F(e){return e.poe_state==="deny"?"deny":e.poe_state==="ok"&&Number(e.poe_w)>0?"on":null}var N=e=>e*30+Math.floor(e/6)*18,I=e=>Math.floor((e-1)/2),ze=e=>e%2===1?0:44;function B(e){let t=new Map,n=0;e.forEach((p,m)=>{let u=C(p.interface);if(!u){n+=1;return}t.has(u.member)||t.set(u.member,[]),t.get(u.member).push(D(M({},u),{index:m}))});let s=[],a=[],c=[],d=0,l=0;return[...t.keys()].sort((p,m)=>p-m).forEach(p=>{let m=new Map;t.get(p).forEach(o=>{let i=`${o.module}:${o.port}`;m.has(i)||m.set(i,{module:o.module,port:o.port,ports:[]}),m.get(i).ports.push(o)});let u=new Map;m.forEach(o=>{u.has(o.module)||u.set(o.module,[]),u.get(o.module).push(o)});let y=d+16;c.push({text:`Switch ${p}`,x:0,y:d+11});let x=0;[...u.keys()].sort((o,i)=>o-i).forEach(o=>{o!==0&&c.push({text:`Module ${o}`,x,y:d+11});let i=0;u.get(o).forEach(f=>{let b=x+N(I(f.port)),z=y+ze(f.port);i=Math.max(i,N(I(f.port))+24),f.ports.length===1&&f.ports[0].lane===null?s.push({index:f.ports[0].index,x:b,y:z,size:24}):f.ports.forEach(k=>{var P;let L=(((P=k.lane)!=null?P:1)-1)%4;s.push({index:k.index,x:b+L%2*13,y:z+Math.floor(L/2)*13,size:11})}),a.push({text:String(f.port),x:b+24/2,y:z+34})}),x+=i+54,l=Math.max(l,x-54)}),d+=110}),{items:s,labels:a,heads:c,skipped:n,width:l,height:Math.max(d-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var G={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},E={on:"#f5d90a",deny:"#dc4e41"},w=[.7,0,.16,.58,.45,.58,.34,1,.86,.4,.56,.4],Ee=[["copper","Copper"],["copper-slow","Copper, reduced speed"],["fibre","Fibre"],["fibre-slow","Fibre, reduced speed"],["admin","Admin down"],["down","Down"]],H="#ff3b30",U=e=>(Number(e.in_errs)||0)+(Number(e.out_errs)||0),K={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},g=document.createElement("div");g.className="viz-container";(document.getElementById("root")||document.body).appendChild(g);var h={data:null,rows:[],loading:!1,theme:"dark"};function we(e){var a;let t=((e==null?void 0:e.fields)||[]).map(c=>{var d;return(d=c.name)!=null?d:c}),n=(e==null?void 0:e.columns)||[],s=((a=n[0])==null?void 0:a.length)||0;return Array.from({length:s},(c,d)=>Object.fromEntries(t.map((l,p)=>[l,n[p][d]])))}function ke(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function Le(e){var s;let t=[e.interface,e.state||"down",ke(e.speed)];e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;if(n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),e.poe_state==="deny")t.push("PoE denied");else if(e.poe_state==="ok"&&e.poe_w!==""&&e.poe_w!=null){let a=Math.round(Number(e.poe_w)*10)/10;t.push(`PoE ${a} W${/^\d+$/.test((s=e.pd_class)!=null?s:"")?`, class ${e.pd_class}`:""}`)}return U(e)>0&&t.push(`Errors: ${Number(e.in_errs)||0} in, ${Number(e.out_errs)||0} out`),t.filter(Boolean).join(" \xB7 ")}function $(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function Q(e,t,n){let s=n*.7,a=e+n*.15,c=t+n*.15,d=[];for(let l=0;l<w.length;l+=2)d.push(`${(a+w[l]*s).toFixed(2)},${(c+w[l+1]*s).toFixed(2)}`);return d.join(" ")}function Pe(e){let t=K[h.theme]||K.dark,n=B(e),s=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${$(o.text)}</text>`).join(""),a=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${$(o.text)}</text>`).join(""),c=n.items.map(o=>{let i=e[o.index],f=F(i),b=f?`<polygon points="${Q(o.x,o.y,o.size)}" fill="${E[f]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`:"";return`<g class="viz-port" data-i="${o.index}"><title>${$(Le(i))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${G[j(i)]}" `+(U(i)>0?`stroke="${H}" stroke-width="2.5"`:`stroke="${t.outline}"`)+`/>${b}</g>`}).join(""),d=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",l=14,p=7,m=`<rect x="${-p}" y="${-p}" width="${n.width+2*p}" height="${n.height+2*p}" rx="6" fill="none" stroke="${t.outline}" stroke-width="1.5"/>`,u=o=>`<span class="viz-swatch" style="background:${o};border-color:${t.outline}"></span>`,y=o=>`<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${Q(0,0,10)}" fill="${o}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`,x=`<div class="viz-legend" style="color:${t.muted}">`+Ee.map(([o,i])=>`<span>${u(G[o])}${i}</span>`).join("")+`<span>${y(E.on)}PoE</span><span>${y(E.deny)}PoE denied</span><span><span class="viz-swatch" style="border:2px solid ${H}"></span>Errors</span></div>`;g.innerHTML=`<svg class="viz-svg" viewBox="${-l} ${-l} ${n.width+2*l} ${n.height+2*l}" preserveAspectRatio="xMidYMid meet" role="img">`+m+s+c+a+"</svg>"+x+d,g.classList.remove("viz-container--empty")}function W(e){g.innerHTML=`<div class="viz-message">${$(e)}</div>`,g.classList.add("viz-container--empty")}function V(){if(h.loading)return W("Loading ports...");if(h.rows=h.data?we(h.data):[],h.rows.length===0)return W("No ports to show for this switch");Pe(h.rows)}g.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=h.rows[Number(t.dataset.i)];n&&v.triggerDrilldown({action:"point.click",payload:{name:"interface",value:n.interface,"click.name":"interface","click.value":n.interface,"row.interface.value":n.interface},originalEvent:e})});v.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;h.loading=t,h.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,V()},{invokeImmediately:!0});v.addThemeListener(({theme:e})=>{h.theme=e,g.dataset.theme=e,V()},{invokeImmediately:!0});
