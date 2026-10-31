var nt=Object.defineProperty,et=Object.defineProperties;var rt=Object.getOwnPropertyDescriptors;var P=Object.getOwnPropertySymbols;var ot=Object.prototype.hasOwnProperty,it=Object.prototype.propertyIsEnumerable;var z=(t,n,e)=>n in t?nt(t,n,{enumerable:!0,configurable:!0,writable:!0,value:e}):t[n]=e,H=(t,n)=>{for(var e in n||(n={}))ot.call(n,e)&&z(t,e,n[e]);if(P)for(var e of P(n))it.call(n,e)&&z(t,e,n[e]);return t},j=(t,n)=>et(t,rt(n));var F=Object.defineProperty,I=(t,n)=>{let e={};for(var a in t)F(e,a,{get:t[a],enumerable:!0});return n||F(e,Symbol.toStringTag,{value:"Module"}),e};var D=I({addDataSourcesListener:()=>st,addDimensionsListener:()=>ft,addDrilldownListener:()=>wt,addErrorListener:()=>vt,addModeListener:()=>ut,addOptionsListener:()=>lt,addThemeListener:()=>mt,addTokensListener:()=>xt,clearError:()=>Lt,getDataSources:()=>dt,getDimensions:()=>ht,getError:()=>Et,getMode:()=>gt,getOptions:()=>ct,getTheme:()=>bt,getTokens:()=>$t,setError:()=>St,setOptions:()=>pt,triggerDrilldown:()=>yt}),at=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),R,p=(R=globalThis.DashboardExtensionAPI)!=null?R:at,st=p.addDataSourcesListener,dt=p.getDataSources,lt=p.addOptionsListener,ct=p.getOptions,pt=p.setOptions,ft=p.addDimensionsListener,ht=p.getDimensions,ut=p.addModeListener,gt=p.getMode,mt=p.addThemeListener,bt=p.getTheme,xt=p.addTokensListener,$t=p.getTokens,wt=p.addDrilldownListener,yt=p.triggerDrilldown,vt=p.addErrorListener,Et=p.getError,St=p.setError,Lt=p.clearError;var N=t=>t==null||t===""?NaN:Number(t);function kt(t,n,e,a){let o=null;for(let i of e)if(!(i<t-60)){if(o!==null&&i-o>300)return{end:Math.min(o+60,n),reason:"last"};if(i>=n)break;o=i}return Number.isFinite(n)?{end:n,reason:"next"}:o===null?{end:t,reason:"last"}:{end:Math.min(o+60,a),reason:"last"}}function B(t,n){let e=[],a=[],o=NaN,i=NaN;for(let r of t){o>0||(o=N(r.info_min_time)),Number.isFinite(i)||(i=N(r.info_max_time));let u=N(r.t);Number.isFinite(u)&&(r.kind==="assoc"?e.push(j(H({},r),{t:u})):r.kind==="seen"&&a.push(u))}if(e.sort((r,u)=>r.t-u.t),a.sort((r,u)=>r-u),e.length===0)return{empty:!0,from:NaN,to:NaN,lanes:[],stays:[],gaps:[]};let l=Math.min(e[0].t,a.length?a[0]:1/0),f=o>0?o:l,c=Number.isFinite(i)?i:n,g=[];e.forEach((r,u)=>{let w=u+1<e.length?e[u+1].t:1/0;if(r.t>c)return;let{end:s,reason:h}=kt(r.t,w,a,n),x=r.t>=f;!x&&s<=f||g.push({ap:r.ap,band:r.band,roam:r.roam,runLatency:N(r.run_latency),category:r.category,bssid:r.bssid,start:r.t,end:s,endReason:h,inRange:x,barStart:Math.max(r.t,f),barEnd:Math.min(s,c)})});let L=new Map,k=[];[...g].sort((r,u)=>r.barStart-u.barStart).forEach(r=>{L.has(r.ap)||(L.set(r.ap,k.length),k.push(r.ap))}),g.forEach(r=>{r.lane=L.get(r.ap)});let M=[];for(let r=1;r<a.length;r++){if(a[r]-a[r-1]<=300)continue;let u=Math.max(a[r-1]+60,f),w=Math.min(a[r],c);w>u&&M.push({start:u,end:w})}return{empty:!1,from:f,to:c,lanes:k,stays:g,gaps:M}}var Mt={Join:"join",Good:"good",Slow:"slow",Bad:"bad"};function G(t){var n;return(n=Mt[t])!=null?n:"bad"}var Dt=[60,300,600,900,1800,3600,7200,10800,21600,43200,86400];function W(t,n,e=8,a=0){var f;let o=n-t;if(!(o>0))return[];let i=(f=Dt.find(c=>o/c<=e))!=null?f:86400*Math.ceil(o/(86400*e)),l=[];for(let c=Math.ceil((t+a)/i)*i-a;c<=n;c+=i)l.push(c);return l}(function(){var t=document.createElement("style");t.setAttribute("data-viz",""),t.textContent=`.rt-container {
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
`,document.head.appendChild(t)})();var C={"2.4 GHz":"#4c9a92","5 GHz":"#4a72b8","6 GHz":"#8a6bb5"},J={join:"#9aa3ad",good:"#2fa34f",slow:"#dfb000",bad:"#e5493f"},U={dark:{text:"#dfe3e8",muted:"#8a929b",axis:"#5b6670",bg:"#1b1f24",lane:"#2c333b",gap:"#8a929b"},light:{text:"#1f2933",muted:"#5f6b76",axis:"#b8c0c8",bg:"#ffffff",lane:"#e6eaee",gap:"#5f6b76"}},y=118,_=14,O=4,$=24,q=12,Ot=22,K=8,S=document.createElement("div");S.className="rt-container";var b=document.createElement("div");b.className="rt-body";var m=document.createElement("div");m.className="rt-tip";m.hidden=!0;S.append(b,m);(document.getElementById("root")||document.body).appendChild(S);var d={data:null,loading:!1,theme:"dark",model:null,hover:null,width:0,showDate:!1,tzOff:0},X=()=>U[d.theme]||U.dark;function Tt(t){var o;let n=((t==null?void 0:t.fields)||[]).map(i=>{var l;return(l=i.name)!=null?l:i}),e=(t==null?void 0:t.columns)||[],a=((o=e[0])==null?void 0:o.length)||0;return Array.from({length:a},(i,l)=>Object.fromEntries(n.map((f,c)=>[f,e[c][l]])))}function E(t){return String(t!=null?t:"").replace(/[&<>"']/g,n=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[n])}var T=t=>String(t).padStart(2,"0"),_t=t=>/^[+-]\d{4}$/.test(t||"")?(t[0]==="-"?-1:1)*(Number(t.slice(1,3))*3600+Number(t.slice(3))*60):0;function v(t){let n=new Date((t+d.tzOff)*1e3),e=`${T(n.getUTCHours())}:${T(n.getUTCMinutes())}`;return d.showDate?`${T(n.getUTCMonth()+1)}-${T(n.getUTCDate())} ${e}`:e}function Ct(t){return t<60?`${Math.round(t)} s`:t<3600?`${Math.floor(t/60)} min`:`${Math.floor(t/3600)} h ${Math.floor(t%3600/60)} min`}var At=t=>t==="none"?"First join":t||"-";function Pt(t){let n=d.model,e=t[0],a=Number(t.slice(1));if(e==="g"){let g=n.gaps[a];return`<b>Not seen ${v(g.start)} \u2013 ${v(g.end)}</b><br>(${Math.round((g.end-g.start)/60)} min)`}let o=n.stays[a],i=`Roam: ${E(At(o.roam))}<br>Roam time: ${Number.isFinite(o.runLatency)?Math.round(o.runLatency)+" ms":"-"}<br>BSSID: ${E(o.bssid||"-")}`,l=`<b>${E(o.ap)}</b><br>Band: ${E(o.band||"-")}`;if(e==="t")return`${l}<br>Roamed ${v(o.start)}<br>${i}`;let f=`${v(o.end)}${o.endReason==="last"?" (last seen)":""}`,c=o.inRange?"":"<br>(started before this range)";return`${l}<br>From ${v(o.start)}${c}<br>To ${f}<br>Duration: ${Ct(o.end-o.start)}<br>${i}`}function V(t,n){t&&b.querySelectorAll(`[data-h="${t}"]:not(.rt-hit)`).forEach(e=>e.classList.toggle("rt-hover",n))}function zt(t,n){let e=S.getBoundingClientRect(),a=m.offsetWidth,o=m.offsetHeight,i=14,l=t-e.left+i,f=n-e.top+i;l+a>e.width&&(l=t-e.left-a-i),f+o>e.height&&(f=n-e.top-o-i),m.style.left=`${Math.max(0,l)}px`,m.style.top=`${Math.max(0,f)}px`}function Q(t,n,e){t!==d.hover&&(V(d.hover,!1),d.hover=t,V(t,!0),m.hidden=!t,t&&(m.innerHTML=Pt(t))),t&&zt(n,e)}b.addEventListener("pointermove",t=>{var e,a;let n=(a=(e=t.target).closest)==null?void 0:a.call(e,"[data-h]");Q(n?n.dataset.h:null,t.clientX,t.clientY)});b.addEventListener("pointerleave",()=>Q(null));function Y(t){d.hover=null,m.hidden=!0,b.innerHTML=`<div class="rt-message" style="color:${X().muted}">${E(t)}</div>`}function Ht(t){let n=X(),e=Math.max(320,b.clientWidth||1200);d.width=b.clientWidth,d.showDate=t.to-t.from>86400;let a=e-y-_,o=t.to-t.from,i=s=>(y+(s-t.from)/o*a).toFixed(2),l=t.lanes.length*$,f=O+l+Ot,c=s=>O+s*$,g=t.lanes.map((s,h)=>(h%2?`<rect x="${y}" y="${c(h)}" width="${a}" height="${$}" fill="${n.lane}" fill-opacity="0.4"/>`:"")+`<text x="${y-8}" y="${c(h)+$/2+4}" text-anchor="end" font-size="11" fill="${n.text}">${E(s)}</text>`).join(""),L=t.gaps.map((s,h)=>`<rect class="rt-gap" data-h="g${h}" x="${i(s.start)}" y="${O}" width="${(i(s.end)-i(s.start)).toFixed(2)}" height="${l}" fill="${n.gap}"/>`).join(""),k=t.stays.map((s,h)=>{if(!(s.barEnd>s.barStart))return"";let x=Math.max(1.5,Number(i(s.barEnd))-Number(i(s.barStart)));return`<rect data-h="s${h}" x="${i(s.barStart)}" y="${c(s.lane)+($-q)/2}" width="${x.toFixed(2)}" height="${q}" rx="2" fill="${C[s.band]||n.muted}"/>`}).join(""),M=t.stays.map((s,h)=>{if(!s.inRange)return"";let x=Number(i(s.start)),Z=`<rect class="rt-tick" data-h="t${h}" x="${(x-1.5).toFixed(2)}" y="${c(s.lane)+2}" width="3" height="${$-4}" fill="${J[G(s.category)]}" stroke="${n.bg}" stroke-width="1"/>`,tt=`<rect class="rt-hit" data-h="t${h}" x="${(x-K).toFixed(2)}" y="${c(s.lane)}" width="${K*2}" height="${$}"/>`;return Z+tt}).join(""),r=O+l,u=`<line x1="${y}" y1="${r}" x2="${e-_}" y2="${r}" stroke="${n.axis}"/>`+W(t.from,t.to,8,d.tzOff).map(s=>{let h=Number(i(s)),x=h<y+24?"start":h>e-_-24?"end":"middle";return`<line x1="${h}" y1="${r}" x2="${h}" y2="${r+4}" stroke="${n.axis}"/><text x="${h}" y="${r+16}" text-anchor="${x}" font-size="10" fill="${n.muted}">${v(s)}</text>`}).join(""),w=jt(n);b.innerHTML=`<svg viewBox="0 0 ${e} ${f}" role="img" style="color:${n.text}">${L}${g}${k}${M}${u}</svg>${w}`}function jt(t){let n=Object.keys(C).map(o=>`<span><i class="rt-swatch" style="background:${C[o]}"></i>${o}</span>`).join(""),e=[["good","Good (under 100 ms)"],["slow","Slow (100\u2013500 ms)"],["bad","Bad (over 500 ms)"],["join","First join"]].map(([o,i])=>`<span><i class="rt-swatch rt-tick-swatch" style="background:${J[o]}"></i>${i}</span>`).join(""),a=`<span><i class="rt-swatch" style="background:${t.gap};opacity:0.3"></i>Offline (not seen over ${300/60} min)</span>`;return`<div class="rt-legend" style="color:${t.muted}"><div style="display:flex;gap:16px;flex-wrap:wrap">${n}</div><div style="display:flex;gap:16px;flex-wrap:wrap">${e}${a}</div></div>`}function A(){var e;if(d.loading)return Y("Loading roaming...");let t=d.data?Tt(d.data):[];d.tzOff=_t((e=t[0])==null?void 0:e.tz_offset),d.model=B(t,Date.now()/1e3);let n=d.model;if(n.empty||n.lanes.length===0||!(n.to>n.from))return Y("No roaming data in this range");d.hover=null,m.hidden=!0,Ht(n)}D.addDataSourcesListener(({dataSources:t,loading:n})=>{var e;d.loading=n,d.data=((e=t==null?void 0:t.primary)==null?void 0:e.data)||null,A()},{invokeImmediately:!0});D.addThemeListener(({theme:t})=>{d.theme=t,S.dataset.theme=t,A()},{invokeImmediately:!0});window.ResizeObserver&&new ResizeObserver(()=>{d.model&&b.clientWidth!==d.width&&A()}).observe(S);
