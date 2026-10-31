var nt=Object.defineProperty,et=Object.defineProperties;var rt=Object.getOwnPropertyDescriptors;var P=Object.getOwnPropertySymbols;var ot=Object.prototype.hasOwnProperty,it=Object.prototype.propertyIsEnumerable;var z=(t,n,e)=>n in t?nt(t,n,{enumerable:!0,configurable:!0,writable:!0,value:e}):t[n]=e,H=(t,n)=>{for(var e in n||(n={}))ot.call(n,e)&&z(t,e,n[e]);if(P)for(var e of P(n))it.call(n,e)&&z(t,e,n[e]);return t},j=(t,n)=>et(t,rt(n));var F=Object.defineProperty,I=(t,n)=>{let e={};for(var i in t)F(e,i,{get:t[i],enumerable:!0});return n||F(e,Symbol.toStringTag,{value:"Module"}),e};var D=I({addDataSourcesListener:()=>st,addDimensionsListener:()=>ft,addDrilldownListener:()=>wt,addErrorListener:()=>vt,addModeListener:()=>ut,addOptionsListener:()=>lt,addThemeListener:()=>mt,addTokensListener:()=>xt,clearError:()=>Lt,getDataSources:()=>dt,getDimensions:()=>ht,getError:()=>Et,getMode:()=>gt,getOptions:()=>ct,getTheme:()=>bt,getTokens:()=>$t,setError:()=>St,setOptions:()=>pt,triggerDrilldown:()=>yt}),at=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),R,p=(R=globalThis.DashboardExtensionAPI)!=null?R:at,st=p.addDataSourcesListener,dt=p.getDataSources,lt=p.addOptionsListener,ct=p.getOptions,pt=p.setOptions,ft=p.addDimensionsListener,ht=p.getDimensions,ut=p.addModeListener,gt=p.getMode,mt=p.addThemeListener,bt=p.getTheme,xt=p.addTokensListener,$t=p.getTokens,wt=p.addDrilldownListener,yt=p.triggerDrilldown,vt=p.addErrorListener,Et=p.getError,St=p.setError,Lt=p.clearError;var N=t=>t==null||t===""?NaN:Number(t);function kt(t,n,e,i){let o=null;for(let a of e)if(!(a<t-60)){if(o!==null&&a-o>300)return{end:Math.min(o+60,n),reason:"last"};if(a>=n)break;o=a}return Number.isFinite(n)?{end:n,reason:"next"}:o===null?{end:t,reason:"last"}:{end:Math.min(o+60,i),reason:"last"}}function B(t,n){let e=[],i=[],o=NaN,a=NaN;for(let r of t){o>0||(o=N(r.info_min_time)),Number.isFinite(a)||(a=N(r.info_max_time));let h=N(r.t);Number.isFinite(h)&&(r.kind==="assoc"?e.push(j(H({},r),{t:h})):r.kind==="seen"&&i.push(h))}if(e.sort((r,h)=>r.t-h.t),i.sort((r,h)=>r-h),e.length===0)return{empty:!0,from:NaN,to:NaN,lanes:[],stays:[],gaps:[]};let l=Math.min(e[0].t,i.length?i[0]:1/0),d=o>0?o:l,u=Number.isFinite(a)?a:n,g=[];e.forEach((r,h)=>{let w=h+1<e.length?e[h+1].t:1/0;if(r.t>u)return;let{end:s,reason:f}=kt(r.t,w,i,n),x=r.t>=d;!x&&s<=d||g.push({ap:r.ap,band:r.band,roam:r.roam,runLatency:N(r.run_latency),category:r.category,bssid:r.bssid,start:r.t,end:s,endReason:f,inRange:x,barStart:Math.max(r.t,d),barEnd:Math.min(s,u)})});let L=new Map,k=[];[...g].sort((r,h)=>r.barStart-h.barStart).forEach(r=>{L.has(r.ap)||(L.set(r.ap,k.length),k.push(r.ap))}),g.forEach(r=>{r.lane=L.get(r.ap)});let M=[];for(let r=1;r<i.length;r++){if(i[r]-i[r-1]<=300)continue;let h=Math.max(i[r-1]+60,d),w=Math.min(i[r],u);w>h&&M.push({start:h,end:w})}return{empty:!1,from:d,to:u,lanes:k,stays:g,gaps:M}}var Mt={Join:"join",Good:"good",Slow:"slow",Bad:"bad"};function G(t){var n;return(n=Mt[t])!=null?n:"bad"}var Dt=[60,300,600,900,1800,3600,7200,10800,21600,43200,86400];function W(t,n,e=8){var l;let i=n-t;if(!(i>0))return[];let o=(l=Dt.find(d=>i/d<=e))!=null?l:86400*Math.ceil(i/(86400*e)),a=[];for(let d=Math.ceil(t/o)*o;d<=n;d+=o)a.push(d);return a}(function(){var t=document.createElement("style");t.setAttribute("data-viz",""),t.textContent=`.rt-container {
  position: relative;
  width: 100%;
  box-sizing: border-box;
  font-size: 12px;
}
.rt-body svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
}
.rt-body .rt-bar,
.rt-body .rt-tick,
.rt-body .rt-gap {
  transition: none;
}
.rt-body .rt-hover {
  stroke: currentColor;
  stroke-width: 1.5;
}
.rt-gap {
  fill-opacity: 0.16;
}
.rt-hit {
  fill: transparent;
}
.rt-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 4px 16px;
  margin-top: 6px;
}
.rt-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.rt-swatch {
  display: inline-block;
  width: 12px;
  height: 9px;
  border-radius: 2px;
}
.rt-tick-swatch {
  width: 3px;
  height: 11px;
}
.rt-message {
  padding: 24px 8px;
  text-align: center;
}
.rt-tip {
  position: absolute;
  left: 0;
  top: 0;
  pointer-events: none;
  padding: 6px 9px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.45;
  white-space: nowrap;
  border: 1px solid;
  z-index: 2;
}
.rt-tip[hidden] {
  display: none;
}
.rt-tip b {
  font-weight: 600;
}
.rt-container[data-theme=dark] .rt-tip {
  background: #14181d;
  color: #dfe3e8;
  border-color: #4a535d;
}
.rt-container[data-theme=light] .rt-tip {
  background: #ffffff;
  color: #1f2933;
  border-color: #aab3bc;
}
`,document.head.appendChild(t)})();var A={"2.4 GHz":"#4c9a92","5 GHz":"#4a72b8","6 GHz":"#8a6bb5"},X={join:"#9aa3ad",good:"#2fa34f",slow:"#dfb000",bad:"#e5493f"},q={dark:{text:"#dfe3e8",muted:"#8a929b",axis:"#5b6670",bg:"#1b1f24",lane:"#2c333b",gap:"#8a929b"},light:{text:"#1f2933",muted:"#5f6b76",axis:"#b8c0c8",bg:"#ffffff",lane:"#e6eaee",gap:"#5f6b76"}},y=118,_=14,O=4,$=24,K=12,Ot=22,V=8,S=document.createElement("div");S.className="rt-container";var b=document.createElement("div");b.className="rt-body";var m=document.createElement("div");m.className="rt-tip";m.hidden=!0;S.append(b,m);(document.getElementById("root")||document.body).appendChild(S);var c={data:null,loading:!1,theme:"dark",model:null,hover:null,width:0,showDate:!1},Q=()=>q[c.theme]||q.dark;function Tt(t){var o;let n=((t==null?void 0:t.fields)||[]).map(a=>{var l;return(l=a.name)!=null?l:a}),e=(t==null?void 0:t.columns)||[],i=((o=e[0])==null?void 0:o.length)||0;return Array.from({length:i},(a,l)=>Object.fromEntries(n.map((d,u)=>[d,e[u][l]])))}function E(t){return String(t!=null?t:"").replace(/[&<>"']/g,n=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[n])}var T=t=>String(t).padStart(2,"0");function v(t){let n=new Date(t*1e3),e=`${T(n.getHours())}:${T(n.getMinutes())}`;return c.showDate?`${T(n.getMonth()+1)}-${T(n.getDate())} ${e}`:e}function _t(t){return t<60?`${Math.round(t)} s`:t<3600?`${Math.floor(t/60)} min`:`${Math.floor(t/3600)} h ${Math.floor(t%3600/60)} min`}var At=t=>t==="none"?"First join":t||"-";function Ct(t){let n=c.model,e=t[0],i=Number(t.slice(1));if(e==="g"){let g=n.gaps[i];return`<b>Not seen ${v(g.start)} \u2013 ${v(g.end)}</b><br>(${Math.round((g.end-g.start)/60)} min)`}let o=n.stays[i],a=`Roam: ${E(At(o.roam))}<br>Roam time: ${Number.isFinite(o.runLatency)?Math.round(o.runLatency)+" ms":"-"}<br>BSSID: ${E(o.bssid||"-")}`,l=`<b>${E(o.ap)}</b><br>Band: ${E(o.band||"-")}`;if(e==="t")return`${l}<br>Roamed ${v(o.start)}<br>${a}`;let d=`${v(o.end)}${o.endReason==="last"?" (last seen)":""}`,u=o.inRange?"":"<br>(started before this range)";return`${l}<br>From ${v(o.start)}${u}<br>To ${d}<br>Duration: ${_t(o.end-o.start)}<br>${a}`}function Y(t,n){t&&b.querySelectorAll(`[data-h="${t}"]:not(.rt-hit)`).forEach(e=>e.classList.toggle("rt-hover",n))}function Pt(t,n){let e=S.getBoundingClientRect(),i=m.offsetWidth,o=m.offsetHeight,a=14,l=t-e.left+a,d=n-e.top+a;l+i>e.width&&(l=t-e.left-i-a),d+o>e.height&&(d=n-e.top-o-a),m.style.left=`${Math.max(0,l)}px`,m.style.top=`${Math.max(0,d)}px`}function U(t,n,e){t!==c.hover&&(Y(c.hover,!1),c.hover=t,Y(t,!0),m.hidden=!t,t&&(m.innerHTML=Ct(t))),t&&Pt(n,e)}b.addEventListener("pointermove",t=>{var e,i;let n=(i=(e=t.target).closest)==null?void 0:i.call(e,"[data-h]");U(n?n.dataset.h:null,t.clientX,t.clientY)});b.addEventListener("pointerleave",()=>U(null));function J(t){c.hover=null,m.hidden=!0,b.innerHTML=`<div class="rt-message" style="color:${Q().muted}">${E(t)}</div>`}function zt(t){let n=Q(),e=Math.max(320,b.clientWidth||1200);c.width=b.clientWidth,c.showDate=t.to-t.from>86400;let i=e-y-_,o=t.to-t.from,a=s=>(y+(s-t.from)/o*i).toFixed(2),l=t.lanes.length*$,d=O+l+Ot,u=s=>O+s*$,g=t.lanes.map((s,f)=>(f%2?`<rect x="${y}" y="${u(f)}" width="${i}" height="${$}" fill="${n.lane}" fill-opacity="0.4"/>`:"")+`<text x="${y-8}" y="${u(f)+$/2+4}" text-anchor="end" font-size="11" fill="${n.text}">${E(s)}</text>`).join(""),L=t.gaps.map((s,f)=>`<rect class="rt-gap" data-h="g${f}" x="${a(s.start)}" y="${O}" width="${(a(s.end)-a(s.start)).toFixed(2)}" height="${l}" fill="${n.gap}"/>`).join(""),k=t.stays.map((s,f)=>{if(!(s.barEnd>s.barStart))return"";let x=Math.max(1.5,Number(a(s.barEnd))-Number(a(s.barStart)));return`<rect data-h="s${f}" x="${a(s.barStart)}" y="${u(s.lane)+($-K)/2}" width="${x.toFixed(2)}" height="${K}" rx="2" fill="${A[s.band]||n.muted}"/>`}).join(""),M=t.stays.map((s,f)=>{if(!s.inRange)return"";let x=Number(a(s.start)),Z=`<rect class="rt-tick" data-h="t${f}" x="${(x-1.5).toFixed(2)}" y="${u(s.lane)+2}" width="3" height="${$-4}" fill="${X[G(s.category)]}" stroke="${n.bg}" stroke-width="1"/>`,tt=`<rect class="rt-hit" data-h="t${f}" x="${(x-V).toFixed(2)}" y="${u(s.lane)}" width="${V*2}" height="${$}"/>`;return Z+tt}).join(""),r=O+l,h=`<line x1="${y}" y1="${r}" x2="${e-_}" y2="${r}" stroke="${n.axis}"/>`+W(t.from,t.to).map(s=>{let f=Number(a(s)),x=f<y+24?"start":f>e-_-24?"end":"middle";return`<line x1="${f}" y1="${r}" x2="${f}" y2="${r+4}" stroke="${n.axis}"/><text x="${f}" y="${r+16}" text-anchor="${x}" font-size="10" fill="${n.muted}">${v(s)}</text>`}).join(""),w=Ht(n);b.innerHTML=`<svg viewBox="0 0 ${e} ${d}" role="img" style="color:${n.text}">${L}${g}${k}${M}${h}</svg>${w}`}function Ht(t){let n=Object.keys(A).map(o=>`<span><i class="rt-swatch" style="background:${A[o]}"></i>${o}</span>`).join(""),e=[["good","Good (under 100 ms)"],["slow","Slow (100\u2013500 ms)"],["bad","Bad (over 500 ms)"],["join","First join"]].map(([o,a])=>`<span><i class="rt-swatch rt-tick-swatch" style="background:${X[o]}"></i>${a}</span>`).join(""),i=`<span><i class="rt-swatch" style="background:${t.gap};opacity:0.3"></i>Offline (not seen over ${300/60} min)</span>`;return`<div class="rt-legend" style="color:${t.muted}"><div style="display:flex;gap:16px;flex-wrap:wrap">${n}</div><div style="display:flex;gap:16px;flex-wrap:wrap">${e}${i}</div></div>`}function C(){if(c.loading)return J("Loading roaming...");let t=c.data?Tt(c.data):[];c.model=B(t,Date.now()/1e3);let n=c.model;if(n.empty||n.lanes.length===0||!(n.to>n.from))return J("No roaming data in this range");c.hover=null,m.hidden=!0,zt(n)}D.addDataSourcesListener(({dataSources:t,loading:n})=>{var e;c.loading=n,c.data=((e=t==null?void 0:t.primary)==null?void 0:e.data)||null,C()},{invokeImmediately:!0});D.addThemeListener(({theme:t})=>{c.theme=t,S.dataset.theme=t,C()},{invokeImmediately:!0});window.ResizeObserver&&new ResizeObserver(()=>{c.model&&b.clientWidth!==c.width&&C()}).observe(S);
