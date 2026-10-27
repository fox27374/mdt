var Y=Object.defineProperty,q=Object.defineProperties;var J=Object.getOwnPropertyDescriptors;var A=Object.getOwnPropertySymbols;var Z=Object.prototype.hasOwnProperty,ee=Object.prototype.propertyIsEnumerable;var M=(e,t,n)=>t in e?Y(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,D=(e,t)=>{for(var n in t||(t={}))Z.call(t,n)&&M(e,n,t[n]);if(A)for(var n of A(t))ee.call(t,n)&&M(e,n,t[n]);return e},S=(e,t)=>q(e,J(t));var T=Object.defineProperty,O=(e,t)=>{let n={};for(var s in e)T(n,s,{get:e[s],enumerable:!0});return t||T(n,Symbol.toStringTag,{value:"Module"}),n};var z=O({addDataSourcesListener:()=>ne,addDimensionsListener:()=>ae,addDrilldownListener:()=>me,addErrorListener:()=>xe,addModeListener:()=>le,addOptionsListener:()=>se,addThemeListener:()=>pe,addTokensListener:()=>fe,clearError:()=>ye,getDataSources:()=>oe,getDimensions:()=>de,getError:()=>be,getMode:()=>ce,getOptions:()=>re,getTheme:()=>ue,getTokens:()=>he,setError:()=>ve,setOptions:()=>ie,triggerDrilldown:()=>ge}),te=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),N,r=(N=globalThis.DashboardExtensionAPI)!=null?N:te,ne=r.addDataSourcesListener,oe=r.getDataSources,se=r.addOptionsListener,re=r.getOptions,ie=r.setOptions,ae=r.addDimensionsListener,de=r.getDimensions,le=r.addModeListener,ce=r.getMode,pe=r.addThemeListener,ue=r.getTheme,fe=r.addTokensListener,he=r.getTokens,me=r.addDrilldownListener,ge=r.triggerDrilldown,xe=r.addErrorListener,be=r.getError,ve=r.setError,ye=r.clearError;var $e=/^\D+(\d+(?:\/\d+)+)/,C=/^(Ethernet|eth)\d/i;function j(e){let t=$e.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[s,i,p]=n;return n.length===2?{member:s,module:0,port:i,lane:null}:C.test(e)?{member:s,module:0,port:i,lane:p}:{member:s,module:i,port:p,lane:null}}var ze=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function F(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let t=j(e.interface),n=!!t&&(t.module!==0||C.test(e.interface)||ze.test(e.interface)),s=Number(e.speed)>=(n?1e10:1e9);return(n?"fibre":"copper")+(s?"":"-slow")}function B(e){return e.poe_state==="deny"?"deny":e.poe_state==="ok"&&Number(e.poe_w)>0?"on":null}function Ee(e,t,n=!1){let s=String(t!=null?t:"").trim();return s?n?`Switch ${e} \xB7 ${s}`:s:`Switch ${e}`}var I=e=>e*30+Math.floor(e/6)*18,R=e=>Math.floor((e-1)/2),ke=e=>e%2===1?0:44;function G(e){let t=new Map,n=new Map,s=0;e.forEach((f,h)=>{var b;let d=j(f.interface);if(!d){s+=1;return}t.has(d.member)||t.set(d.member,[]),t.get(d.member).push(S(D({},d),{index:h})),!n.has(d.member)&&String((b=f.model)!=null?b:"").trim()&&n.set(d.member,f.model)});let i=[],p=[],u=[],c=0,g=0;return[...t.keys()].sort((f,h)=>f-h).forEach(f=>{let h=new Map;t.get(f).forEach(a=>{let o=`${a.module}:${a.port}`;h.has(o)||h.set(o,{module:a.module,port:a.port,ports:[]}),h.get(o).ports.push(a)});let d=new Map;h.forEach(a=>{d.has(a.module)||d.set(a.module,[]),d.get(a.module).push(a)});let b=c+16;u.push({text:Ee(f,n.get(f),t.size>1),x:0,y:c+11});let v=0;[...d.keys()].sort((a,o)=>a-o).forEach(a=>{let o=0;d.get(a).forEach(l=>{let y=v+I(R(l.port)),$=b+ke(l.port);o=Math.max(o,I(R(l.port))+24),l.ports.length===1&&l.ports[0].lane===null?i.push({index:l.ports[0].index,x:y,y:$,size:24}):l.ports.forEach(L=>{var _;let P=(((_=L.lane)!=null?_:1)-1)%4;i.push({index:L.index,x:y+P%2*13,y:$+Math.floor(P/2)*13,size:11})}),p.push({text:String(l.port),x:y+24/2,y:$+34})}),v+=o+54,g=Math.max(g,v-54)}),c+=110}),{items:i,labels:p,heads:u,skipped:s,width:g,height:Math.max(c-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var H={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},k={on:"#f5d90a",deny:"#dc4e41"},w=[.7,0,.16,.58,.45,.58,.34,1,.86,.4,.56,.4],we=[["copper","Copper"],["copper-slow","Copper, reduced speed"],["fibre","Fibre"],["fibre-slow","Fibre, reduced speed"],["admin","Admin down"],["down","Down"]],K="#ff3b30",U=e=>(Number(e.in_errs)||0)+(Number(e.out_errs)||0),Q={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},x=document.createElement("div");x.className="viz-container";(document.getElementById("root")||document.body).appendChild(x);var m={data:null,rows:[],loading:!1,theme:"dark"};function Le(e){var i;let t=((e==null?void 0:e.fields)||[]).map(p=>{var u;return(u=p.name)!=null?u:p}),n=(e==null?void 0:e.columns)||[],s=((i=n[0])==null?void 0:i.length)||0;return Array.from({length:s},(p,u)=>Object.fromEntries(t.map((c,g)=>[c,n[g][u]])))}function Pe(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function _e(e){var s;let t=[e.interface,e.state||"down",Pe(e.speed)];e.port_channel&&t.push(`Port-channel: ${e.port_channel}`),e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;if(n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),e.poe_state==="deny")t.push("PoE denied");else if(e.poe_state==="ok"&&e.poe_w!==""&&e.poe_w!=null){let i=Math.round(Number(e.poe_w)*10)/10;t.push(`PoE ${i} W${/^\d+$/.test((s=e.pd_class)!=null?s:"")?`, class ${e.pd_class}`:""}`)}return U(e)>0&&t.push(`Errors: ${Number(e.in_errs)||0} in, ${Number(e.out_errs)||0} out`),t.filter(Boolean).join(" \xB7 ")}function E(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function W(e,t,n){let s=n*.7,i=e+n*.15,p=t+n*.15,u=[];for(let c=0;c<w.length;c+=2)u.push(`${(i+w[c]*s).toFixed(2)},${(p+w[c+1]*s).toFixed(2)}`);return u.join(" ")}function Ae(e){let t=Q[m.theme]||Q.dark,n=G(e),s=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${E(o.text)}</text>`).join(""),i=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${E(o.text)}</text>`).join(""),p=n.items.map(o=>{let l=e[o.index],y=B(l),$=y?`<polygon points="${W(o.x,o.y,o.size)}" fill="${k[y]}" stroke="#1a1a1a" stroke-width="0.8" stroke-linejoin="round"/>`:"";return`<g class="viz-port" data-i="${o.index}"><title>${E(_e(l))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${H[F(l)]}" `+(U(l)>0?`stroke="${K}" stroke-width="2.5"`:`stroke="${t.outline}"`)+`/>${$}</g>`}).join(""),u=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",c=7,g=28,f=14,h=35,d=`<rect x="${-g}" y="${-c}" width="${n.width+2*g}" height="${n.height+2*c}" rx="6" fill="none" stroke="${t.outline}" stroke-width="1.5"/>`,b=o=>`<span class="viz-swatch" style="background:${o};border-color:${t.outline}"></span>`,v=o=>`<svg class="viz-legend-bolt" viewBox="0 0 10 10"><polygon points="${W(0,0,10)}" fill="${o}" stroke="#1a1a1a" stroke-width="0.5"/></svg>`,a=`<div class="viz-legend" style="color:${t.muted}">`+we.map(([o,l])=>`<span>${b(H[o])}${l}</span>`).join("")+`<span>${v(k.on)}PoE</span><span>${v(k.deny)}PoE denied</span><span><span class="viz-swatch" style="border:2px solid ${K}"></span>Errors</span></div>`;x.innerHTML=`<svg class="viz-svg" viewBox="${-h} ${-f} ${n.width+2*h} ${n.height+2*f}" preserveAspectRatio="xMidYMid meet" role="img">`+d+s+p+i+"</svg>"+a+u,x.classList.remove("viz-container--empty")}function X(e){x.innerHTML=`<div class="viz-message">${E(e)}</div>`,x.classList.add("viz-container--empty")}function V(){if(m.loading)return X("Loading ports...");if(m.rows=m.data?Le(m.data):[],m.rows.length===0)return X("No ports to show for this switch");Ae(m.rows)}x.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=m.rows[Number(t.dataset.i)];n&&z.triggerDrilldown({action:"point.click",payload:{name:"interface",value:n.interface,"click.name":"interface","click.value":n.interface,"row.interface.value":n.interface},originalEvent:e})});z.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;m.loading=t,m.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,V()},{invokeImmediately:!0});z.addThemeListener(({theme:e})=>{m.theme=e,x.dataset.theme=e,V()},{invokeImmediately:!0});
