var j=Object.defineProperty,F=Object.defineProperties;var K=Object.getOwnPropertyDescriptors;var w=Object.getOwnPropertySymbols;var Q=Object.prototype.hasOwnProperty,W=Object.prototype.propertyIsEnumerable;var P=(e,t,n)=>t in e?j(e,t,{enumerable:!0,configurable:!0,writable:!0,value:n}):e[t]=n,$=(e,t)=>{for(var n in t||(t={}))Q.call(t,n)&&P(e,n,t[n]);if(w)for(var n of w(t))W.call(t,n)&&P(e,n,t[n]);return e},A=(e,t)=>F(e,K(t));var D=Object.defineProperty,M=(e,t)=>{let n={};for(var s in e)D(n,s,{get:e[s],enumerable:!0});return t||D(n,Symbol.toStringTag,{value:"Module"}),n};var x=M({addDataSourcesListener:()=>V,addDimensionsListener:()=>Z,addDrilldownListener:()=>ae,addErrorListener:()=>de,addModeListener:()=>te,addOptionsListener:()=>Y,addThemeListener:()=>oe,addTokensListener:()=>se,clearError:()=>ue,getDataSources:()=>X,getDimensions:()=>ee,getError:()=>le,getMode:()=>ne,getOptions:()=>q,getTheme:()=>re,getTokens:()=>ie,setError:()=>pe,setOptions:()=>J,triggerDrilldown:()=>ce}),U=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),T,r=(T=globalThis.DashboardExtensionAPI)!=null?T:U,V=r.addDataSourcesListener,X=r.getDataSources,Y=r.addOptionsListener,q=r.getOptions,J=r.setOptions,Z=r.addDimensionsListener,ee=r.getDimensions,te=r.addModeListener,ne=r.getMode,oe=r.addThemeListener,re=r.getTheme,se=r.addTokensListener,ie=r.getTokens,ae=r.addDrilldownListener,ce=r.triggerDrilldown,de=r.addErrorListener,le=r.getError,pe=r.setError,ue=r.clearError;var me=/^\D+(\d+(?:\/\d+)+)/,_=/^(Ethernet|eth)\d/i;function I(e){let t=me.exec(e!=null?e:"");if(!t)return null;let n=t[1].split("/").map(Number);if(n.length>3)return null;let[s,d,a]=n;return n.length===2?{member:s,module:0,port:d,lane:null}:_.test(e)?{member:s,module:0,port:d,lane:a}:{member:s,module:d,port:a,lane:null}}var fe=/^(TwentyFive|Forty|Fifty|Hundred|FourHundred)/i;function R(e){if(e.state==="admin down")return"admin";if(e.state!=="up")return"down";let t=I(e.interface),n=!!t&&(t.module!==0||_.test(e.interface)||fe.test(e.interface)),s=Number(e.speed)>=(n?1e10:1e9);return(n?"fibre":"copper")+(s?"":"-slow")}var S=e=>e*30+Math.floor(e/6)*18,O=e=>Math.floor((e-1)/2),he=e=>e%2===1?0:44;function C(e){let t=new Map,n=0;e.forEach((o,l)=>{let p=I(o.interface);if(!p){n+=1;return}t.has(p.member)||t.set(p.member,[]),t.get(p.member).push(A($({},p),{index:l}))});let s=[],d=[],a=[],c=0,m=0;return[...t.keys()].sort((o,l)=>o-l).forEach(o=>{let l=new Map;t.get(o).forEach(i=>{let f=`${i.module}:${i.port}`;l.has(f)||l.set(f,{module:i.module,port:i.port,ports:[]}),l.get(f).ports.push(i)});let p=new Map;l.forEach(i=>{p.has(i.module)||p.set(i.module,[]),p.get(i.module).push(i)});let B=c+16;a.push({text:`Switch ${o}`,x:0,y:c+11});let v=0;[...p.keys()].sort((i,f)=>i-f).forEach(i=>{i!==0&&a.push({text:`Module ${i}`,x:v,y:c+11});let f=0;p.get(i).forEach(h=>{let y=v+S(O(h.port)),L=B+he(h.port);f=Math.max(f,S(O(h.port))+24),h.ports.length===1&&h.ports[0].lane===null?s.push({index:h.ports[0].index,x:y,y:L,size:24}):h.ports.forEach(E=>{var k;let z=(((k=E.lane)!=null?k:1)-1)%4;s.push({index:E.index,x:y+z%2*13,y:L+Math.floor(z/2)*13,size:11})}),d.push({text:String(h.port),x:y+24/2,y:L+34})}),v+=f+54,m=Math.max(m,v-54)}),c+=110}),{items:s,labels:d,heads:a,skipped:n,width:m,height:Math.max(c-10,0)}}(function(){var e=document.createElement("style");e.setAttribute("data-viz",""),e.textContent=`.viz-container {
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
`,document.head.appendChild(e)})();var ge={copper:"#7ed321","copper-slow":"#0b7a32",fibre:"#7b9cf0","fibre-slow":"#3157d5",admin:"#a6a6a6",down:"#000000"},N={dark:{outline:"#5b6670",text:"#dfe3e8",muted:"#8a929b"},light:{outline:"#3c444d",text:"#1f2933",muted:"#5f6b76"}},g=document.createElement("div");g.className="viz-container";(document.getElementById("root")||document.body).appendChild(g);var u={data:null,rows:[],loading:!1,theme:"dark"};function xe(e){var d;let t=((e==null?void 0:e.fields)||[]).map(a=>{var c;return(c=a.name)!=null?c:a}),n=(e==null?void 0:e.columns)||[],s=((d=n[0])==null?void 0:d.length)||0;return Array.from({length:s},(a,c)=>Object.fromEntries(t.map((m,o)=>[m,n[o][c]])))}function ve(e){let t=Number(e);return t>0?t>=1e9?`${Math.round(t/1e9*10)/10} Gb/s`:`${Math.round(t/1e6)} Mb/s`:""}function be(e){let t=[e.interface,e.state||"down",ve(e.speed)];e.neighbour&&t.push(`CDP: ${e.neighbour}`);let n=Number(e.macs)||0;return n>5?t.push(`${n} MACs`):n>0&&t.push(`MACs: ${e.mac_list}`),t.filter(Boolean).join(" \xB7 ")}function b(e){return String(e!=null?e:"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t])}function ye(e){let t=N[u.theme]||N.dark,n=C(e),s=n.heads.map(o=>`<text x="${o.x}" y="${o.y}" font-size="10" fill="${t.muted}">${b(o.text)}</text>`).join(""),d=n.labels.map(o=>`<text x="${o.x}" y="${o.y}" text-anchor="middle" font-size="9" fill="${t.text}">${b(o.text)}</text>`).join(""),a=n.items.map(o=>{let l=e[o.index];return`<g class="viz-port" data-i="${o.index}"><title>${b(be(l))}</title><rect x="${o.x}" y="${o.y}" width="${o.size}" height="${o.size}" rx="3" fill="${ge[R(l)]}" stroke="${t.outline}"/></g>`}).join(""),c=n.skipped?`<div class="viz-note" style="color:${t.muted}">${n.skipped} port(s) with no slot in the faceplate are in the Interfaces table.</div>`:"",m=4;g.innerHTML=`<svg class="viz-svg" viewBox="${-m} ${-m} ${n.width+2*m} ${n.height+2*m}" preserveAspectRatio="xMidYMid meet" role="img">`+s+a+d+"</svg>"+c,g.classList.remove("viz-container--empty")}function G(e){g.innerHTML=`<div class="viz-message">${b(e)}</div>`,g.classList.add("viz-container--empty")}function H(){if(u.loading)return G("Loading ports...");if(u.rows=u.data?xe(u.data):[],u.rows.length===0)return G("No ports to show for this switch");ye(u.rows)}g.addEventListener("click",e=>{let t=e.target.closest(".viz-port");if(!t)return;let n=u.rows[Number(t.dataset.i)];n&&x.triggerDrilldown({action:"point.click",payload:{name:"interface",value:n.interface,"click.name":"interface","click.value":n.interface,"row.interface.value":n.interface},originalEvent:e})});x.addDataSourcesListener(({dataSources:e,loading:t})=>{var n;u.loading=t,u.data=((n=e==null?void 0:e.primary)==null?void 0:n.data)||null,H()},{invokeImmediately:!0});x.addThemeListener(({theme:e})=>{u.theme=e,g.dataset.theme=e,H()},{invokeImmediately:!0});
