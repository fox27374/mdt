var V=Object.defineProperty,Y=Object.defineProperties;var q=Object.getOwnPropertyDescriptors;var _=Object.getOwnPropertySymbols;var J=Object.prototype.hasOwnProperty,Z=Object.prototype.propertyIsEnumerable;var A=(e,t,n)=>t in e?V(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,M=(e,t)=>{for(var n in t||(t={}))J.call(t,n)&&A(e,n,t[n]);if(_)for(var n of _(t))Z.call(t,n)&&A(e,n,t[n]);return e},D=(e,t)=>Y(e,q(t));var T=Object.defineProperty,S=(e,t)=>{let n={};for(var s in e)T(n,s,{get:e[s],enumerable:!0});return t||T(n,Symbol.toStringTag,{value:"Module"}),n};var y=S({addDataSourcesListener:()=>te,addDimensionsListener:()=>ie,addDrilldownListener:()=>he,addErrorListener:()=>ge,addModeListener:()=>de,addOptionsListener:()=>oe,addThemeListener:()=>ce,addTokensListener:()=>ue,clearError:()=>ve,getDataSources:()=>ne,getDimensions:()=>ae,getError:()=>xe,getMode:()=>le,getOptions:()=>se,getTheme:()=>pe,getTokens:()=>fe,setError:()=>be,setOptions:()=>re,triggerDrilldown:()=>me}),ee=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),O,i=(O=globalThis.DashboardExtensionAPI)!=null?O:ee,te=i.addDataSourcesListener,ne=i.getDataSources,oe=i.addOptionsListener,se=i.getOptions,re=i.setOptions,ie=i.addDimensionsListener,ae=i.getDimensions,de=i.addModeListener,le=i.getMode,ce=i.addThemeListener,pe=i.getTheme,ue=i.addTokensListener,fe=i.getTokens,he=i.addDrilldownListener,me=i.triggerDrilldown,ge=i.addErrorListener,xe=i.getError,be=i.setError,ve=i.clearError;var ye=/^\D+(\d+(?:\/\d+)+)/,R=/^(Ethernet|eth)\d/i;function C(e){let t=ye.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[s,a,l]=n;return n.length===2?{member:s,module:0,port:a,lane:null}:R.test(e)?{member:s,module:0,port:a,lane:l}:{member:s,module:a,port:l,lane:null}}var $e=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function j(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let t=C(e.interface),n=!!t&&(t.module!==0||R.test(e.interface)||$e.test(e.interface)),s=Number(e.speed)>=(n?1e10:1e9);return(n?"fibre":"copper")+(s?"":"-slow")}function F(e){return e.poe_state==="deny"?"deny":e.poe_state==="ok"&&Number(e.poe_w)>0?"on":null}var N=e=>e*30+Math.floor(e/6)*18,I=e=>Math.floor((e-1)/2),ze=e=>e%2===1?0:44;function B(e){let t=new Map,n=0;e.forEach((u,f)=>{let c=C(u.interface);if(!c){n+=1;return}t.has(c.member)||t.set(c.member,[]),t.get(c.member).push(D(M({},c),{index:f}))});let s=[],a=[],l=[],d=0,p=0;return[...t.keys()].sort((u,f)=>u-f).forEach(u=>{let f=new Map;t.get(u).forEach(r=>{let h=`${r.module}:${r.port}`;f.has(h)||f.set(h,{module:r.module,port:r.port,ports:[]}),f.get(h).ports.push(r)});let c=new Map;f.forEach(r=>{c.has(r.module)||c.set(r.module,[]),c.get(r.module).push(r)});let E=d+16;l.push({text:`Switch ${u}`,x:0,y:d+11});let b=0;[...c.keys()].sort((r,h)=>r-h).forEach(r=>{r!==0&&l.push({text:`Module ${r}`,x:b,y:d+11});let h=0;c.get(r).forEach(o=>{let g=b+N(I(o.port)),v=E+ze(o.port);h=Math.max(h,N(I(o.port))+24),o.ports.length===1&&o.ports[0].lane===null?s.push({index:o.ports[0].index,x:g,y:v,size:24}):o.ports.forEach($=>{var P;let L=(((P=$.lane)!=null?P:1)-1)%4;s.push({index:$.index,x:g+L%2*13,y:v+Math.floor(L/2)*13,size:11})}),a.push({text:String(o.port),x:g+24/2,y:v+34})}),b+=h+54,p=Math.max(p,b-54)}),d+=110}),{items:s,labels:a,heads:l,skipped:n,width:p,height:Math.max(d-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var G={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},w={on:"#f5d90a",deny:"#dc4e41"},k=[.7,0,.16,.58,.45,.58,.34,1,.86,.4,.56,.4],Ee=[["copper","Copper"],["copper-slow","Copper, reduced speed"],["fibre","Fibre"],["fibre-slow","Fibre, reduced speed"],["admin","Admin down"],["down","Down"]],H="#ff3b30",X=e=>(Number(e.in_errs)||0)+(Number(e.out_errs)||0),K={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},x=document.createElement("div");x.className="viz-container";(document.getElementById("root")||document.body).appendChild(x);var m={data:null,rows:[],loading:!1,theme:"dark"};function we(e){var a;let t=((e==null?void 0:e.fields)||[]).map(l=>{var d;return(d=l.name)!=null?d:l}),n=(e==null?void 0:e.columns)||[],s=((a=n[0])==null?void 0:a.length)||0;return Array.from({length:s},(l,d)=>Object.fromEntries(t.map((p,u)=>[p,n[u][d]])))}function ke(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function Le(e){var s;let t=[e.interface,e.state||"down",ke(e.speed)];e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;if(n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),e.poe_state==="deny")t.push("PoE denied");else if(e.poe_state==="ok"&&e.poe_w!==""&&e.poe_w!=null){let a=Math.round(Number(e.poe_w)*10)/10;t.push(`PoE ${a} W${/^\d+$/.test((s=e.pd_class)!=null?s:"")?`, class ${e.pd_class}`:""}`)}return X(e)>0&&t.push(`Errors: ${Number(e.in_errs)||0} in, ${Number(e.out_errs)||0} out`),t.filter(Boolean).join(" \xB7 ")}function z(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function Q(e,t,n){let s=n*.7,a=e+n*.15,l=t+n*.15,d=[];for(let p=0;p<k.length;p+=2)d.push(`${(a+k[p]*s).toFixed(2)},${(l+k[p+1]*s).toFixed(2)}`);return d.join(" ")}function Pe(e){let t=K[m.theme]||K.dark,n=B(e),s=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${z(o.text)}</text>`).join(""),a=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${z(o.text)}</text>`).join(""),l=n.items.map(o=>{let g=e[o.index],v=F(g),$=v?`<polygon points="${Q(o.x,o.y,o.size)}" fill="${w[v]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`:"";return`<g class="viz-port" data-i="${o.index}"><title>${z(Le(g))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${G[j(g)]}" `+(X(g)>0?`stroke="${H}" stroke-width="2.5"`:`stroke="${t.outline}"`)+`/>${$}</g>`}).join(""),d=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",p=7,u=28,f=14,c=35,E=`<rect x="${-u}" y="${-p}" width="${n.width+2*u}" height="${n.height+2*p}" rx="6" fill="none" stroke="${t.outline}" stroke-width="1.5"/>`,b=o=>`<span class="viz-swatch" style="background:${o};border-color:${t.outline}"></span>`,r=o=>`<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${Q(0,0,10)}" fill="${o}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`,h=`<div class="viz-legend" style="color:${t.muted}">`+Ee.map(([o,g])=>`<span>${b(G[o])}${g}</span>`).join("")+`<span>${r(w.on)}PoE</span><span>${r(w.deny)}PoE denied</span><span><span class="viz-swatch" style="border:2px solid ${H}"></span>Errors</span></div>`;x.innerHTML=`<svg class="viz-svg" viewBox="${-c} ${-f} ${n.width+2*c} ${n.height+2*f}" preserveAspectRatio="xMidYMid meet" role="img">`+E+s+l+a+"</svg>"+h+d,x.classList.remove("viz-container--empty")}function W(e){x.innerHTML=`<div class="viz-message">${z(e)}</div>`,x.classList.add("viz-container--empty")}function U(){if(m.loading)return W("Loading ports...");if(m.rows=m.data?we(m.data):[],m.rows.length===0)return W("No ports to show for this switch");Pe(m.rows)}x.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=m.rows[Number(t.dataset.i)];n&&y.triggerDrilldown({action:"point.click",payload:{name:"interface",value:n.interface,"click.name":"interface","click.value":n.interface,"row.interface.value":n.interface},originalEvent:e})});y.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;m.loading=t,m.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,U()},{invokeImmediately:!0});y.addThemeListener(({theme:e})=>{m.theme=e,x.dataset.theme=e,U()},{invokeImmediately:!0});
