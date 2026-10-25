var N=Object.defineProperty,H=Object.defineProperties;var j=Object.getOwnPropertyDescriptors;var k=Object.getOwnPropertySymbols;var B=Object.prototype.hasOwnProperty,Q=Object.prototype.propertyIsEnumerable;var P=(e,t,n)=>t in e?N(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,$=(e,t)=>{for(var n in t||(t={}))B.call(t,n)&&P(e,n,t[n]);if(k)for(var n of k(t))Q.call(t,n)&&P(e,n,t[n]);return e},A=(e,t)=>H(e,j(t));var D=Object.defineProperty,M=(e,t)=>{let n={};for(var i in e)D(n,i,{get:e[i],enumerable:!0});return t||D(n,Symbol.toStringTag,{value:"Module"}),n};var x=M({addDataSourcesListener:()=>K,addDimensionsListener:()=>Y,addDrilldownListener:()=>re,addErrorListener:()=>ie,addModeListener:()=>J,addOptionsListener:()=>U,addThemeListener:()=>ee,addTokensListener:()=>ne,clearError:()=>ce,getDataSources:()=>W,getDimensions:()=>q,getError:()=>ae,getMode:()=>Z,getOptions:()=>V,getTheme:()=>te,getTokens:()=>oe,setError:()=>de,setOptions:()=>X,triggerDrilldown:()=>se}),F=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),S,r=(S=globalThis.DashboardExtensionAPI)!=null?S:F,K=r.addDataSourcesListener,W=r.getDataSources,U=r.addOptionsListener,V=r.getOptions,X=r.setOptions,Y=r.addDimensionsListener,q=r.getDimensions,J=r.addModeListener,Z=r.getMode,ee=r.addThemeListener,te=r.getTheme,ne=r.addTokensListener,oe=r.getTokens,re=r.addDrilldownListener,se=r.triggerDrilldown,ie=r.addErrorListener,ae=r.getError,de=r.setError,ce=r.clearError;var le=/^\D+(\d+(?:\/\d+)+)/,pe=/^(Ethernet|eth)\d/i;function ue(e){let t=le.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[i,c,a]=n;return n.length===2?{member:i,module:0,port:c,lane:null}:pe.test(e)?{member:i,module:0,port:c,lane:a}:{member:i,module:c,port:a,lane:null}}var T=e=>e*30+Math.floor(e/6)*18,O=e=>Math.floor((e-1)/2),me=e=>e%2===1?0:44;function _(e){let t=new Map,n=0;e.forEach((o,l)=>{let p=ue(o.interface);if(!p){n+=1;return}t.has(p.member)||t.set(p.member,[]),t.get(p.member).push(A($({},p),{index:l}))});let i=[],c=[],a=[],d=0,m=0;return[...t.keys()].sort((o,l)=>o-l).forEach(o=>{let l=new Map;t.get(o).forEach(s=>{let h=`${s.module}:${s.port}`;l.has(h)||l.set(h,{module:s.module,port:s.port,ports:[]}),l.get(h).ports.push(s)});let p=new Map;l.forEach(s=>{p.has(s.module)||p.set(s.module,[]),p.get(s.module).push(s)});let G=d+16;a.push({text:`Switch ${o}`,x:0,y:d+11});let v=0;[...p.keys()].sort((s,h)=>s-h).forEach(s=>{s!==0&&a.push({text:`Module ${s}`,x:v,y:d+11});let h=0;p.get(s).forEach(f=>{let L=v+T(O(f.port)),y=G+me(f.port);h=Math.max(h,T(O(f.port))+24),f.ports.length===1&&f.ports[0].lane===null?i.push({index:f.ports[0].index,x:L,y,size:24}):f.ports.forEach(E=>{var w;let z=(((w=E.lane)!=null?w:1)-1)%4;i.push({index:E.index,x:L+z%2*13,y:y+Math.floor(z/2)*13,size:11})}),c.push({text:String(f.port),x:L+24/2,y:y+34})}),v+=h+54,m=Math.max(m,v-54)}),d+=110}),{items:i,labels:c,heads:a,skipped:n,width:m,height:Math.max(d-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var I={dark:{up:"#53a051",down:"#30363d",admin:"#8a929b",text:"#dfe3e8",muted:"#8a929b"},light:{up:"#53a051",down:"#5b6670",admin:"#8a929b",text:"#1f2933",muted:"#5f6b76"}},g=document.createElement("div");g.className="viz-container";(document.getElementById("root")||document.body).appendChild(g);var u={data:null,rows:[],loading:!1,theme:"dark"};function he(e){var c;let t=((e==null?void 0:e.fields)||[]).map(a=>{var d;return(d=a.name)!=null?d:a}),n=(e==null?void 0:e.columns)||[],i=((c=n[0])==null?void 0:c.length)||0;return Array.from({length:i},(a,d)=>Object.fromEntries(t.map((m,o)=>[m,n[o][d]])))}function fe(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function ge(e,t){return e.state==="up"?t.up:e.state==="admin down"?t.admin:t.down}function xe(e){let t=[e.interface,e.state||"down",fe(e.speed)];e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;return n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),t.filter(Boolean).join(" \xB7 ")}function b(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function ve(e){let t=I[u.theme]||I.dark,n=_(e),i=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${b(o.text)}</text>`).join(""),c=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${b(o.text)}</text>`).join(""),a=n.items.map(o=>{let l=e[o.index];return`<g class="viz-port" data-i="${o.index}"><title>${b(xe(l))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${ge(l,t)}"/></g>`}).join(""),d=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",m=4;g.innerHTML=`<svg class="viz-svg" viewBox="${-m} ${-m} ${n.width+2*m} ${n.height+2*m}" preserveAspectRatio="xMidYMid meet" role="img">`+i+a+c+"</svg>"+d,g.classList.remove("viz-container--empty")}function C(e){g.innerHTML=`<div class="viz-message">${b(e)}</div>`,g.classList.add("viz-container--empty")}function R(){if(u.loading)return C("Loading ports...");if(u.rows=u.data?he(u.data):[],u.rows.length===0)return C("No ports to show for this switch");ve(u.rows)}g.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=u.rows[Number(t.dataset.i)];n&&x.triggerDrilldown({action:"click",payload:{value:n.interface,data:{"click.value":n.interface,"row.interface.value":n.interface}},originalEvent:e})});x.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;u.loading=t,u.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,R()},{invokeImmediately:!0});x.addThemeListener(({theme:e})=>{u.theme=e,g.dataset.theme=e,R()},{invokeImmediately:!0});
