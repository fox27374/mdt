var ot=Object.defineProperty,rt=Object.defineProperties;var it=Object.getOwnPropertyDescriptors;var j=Object.getOwnPropertySymbols;var at=Object.prototype.hasOwnProperty,st=Object.prototype.propertyIsEnumerable;var H=(t,n,e)=>n in t?ot(t,n,{enumerable:!0,configurable:!0,writable:!0,value:e}):t[n]=e,I=(t,n)=>{for(var e in n||(n={}))at.call(n,e)&&H(t,e,n[e]);if(j)for(var e of j(n))st.call(n,e)&&H(t,e,n[e]);return t},R=(t,n)=>rt(t,it(n));var F=Object.defineProperty,G=(t,n)=>{let e={};for(var s in t)F(e,s,{get:t[s],enumerable:!0});return n||F(e,Symbol.toStringTag,{value:"Module"}),e};var O=G({addDataSourcesListener:()=>lt,addDimensionsListener:()=>ut,addDrilldownListener:()=>vt,addErrorListener:()=>Et,addModeListener:()=>mt,addOptionsListener:()=>pt,addThemeListener:()=>xt,addTokensListener:()=>wt,clearError:()=>Mt,getDataSources:()=>ct,getDimensions:()=>gt,getError:()=>St,getMode:()=>bt,getOptions:()=>ft,getTheme:()=>$t,getTokens:()=>yt,setError:()=>kt,setOptions:()=>ht,triggerDrilldown:()=>Lt}),dt=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),B,h=(B=globalThis.DashboardExtensionAPI)!=null?B:dt,lt=h.addDataSourcesListener,ct=h.getDataSources,pt=h.addOptionsListener,ft=h.getOptions,ht=h.setOptions,ut=h.addDimensionsListener,gt=h.getDimensions,mt=h.addModeListener,bt=h.getMode,xt=h.addThemeListener,$t=h.getTheme,wt=h.addTokensListener,yt=h.getTokens,vt=h.addDrilldownListener,Lt=h.triggerDrilldown,Et=h.addErrorListener,St=h.getError,kt=h.setError,Mt=h.clearError;var T=t=>t==null||t===""?NaN:Number(t);function Dt(t,n,e,s){let r=null;for(let i of e)if(!(i<t-60)){if(r!==null&&i-r>300)return{end:Math.min(r+60,n),reason:"last"};if(i>=n)break;r=i}return Number.isFinite(n)?{end:n,reason:"next"}:r===null?{end:t,reason:"last"}:{end:Math.min(r+60,s),reason:"last"}}function W(t,n){let e=[],s=[],r=NaN,i=NaN;for(let o of t){r>0||(r=T(o.info_min_time)),Number.isFinite(i)||(i=T(o.info_max_time));let d=T(o.t);Number.isFinite(d)&&(o.kind==="assoc"?e.push(R(I({},o),{t:d})):o.kind==="seen"&&s.push(d))}if(e.sort((o,d)=>o.t-d.t),s.sort((o,d)=>o-d),e.length===0)return{empty:!0,from:NaN,to:NaN,lanes:[],stays:[],gaps:[]};let p=Math.min(e[0].t,s.length?s[0]:1/0),u=r>0?r:p,c=Number.isFinite(i)?i:n,g=[];e.forEach((o,d)=>{let m=d+1<e.length?e[d+1].t:1/0;if(o.t>c)return;let{end:D,reason:a}=Dt(o.t,m,s,n),f=o.t>=u;!f&&D<=u||g.push({ap:o.ap,band:o.band,roam:o.roam,runLatency:T(o.run_latency),category:o.category,bssid:o.bssid,start:o.t,end:D,endReason:a,inRange:f,barStart:Math.max(o.t,u),barEnd:Math.min(D,c)})});let S=new Map,k=[];[...g].sort((o,d)=>o.barStart-d.barStart).forEach(o=>{S.has(o.ap)||(S.set(o.ap,k.length),k.push(o.ap))}),g.forEach(o=>{o.lane=S.get(o.ap)});let M=[];for(let o=1;o<g.length;o++){let d=g[o-1],m=g[o];d.endReason==="next"&&d.lane!==m.lane&&m.inRange&&M.push({t:m.start,fromLane:d.lane,toLane:m.lane})}let N=[];for(let o=1;o<s.length;o++){if(s[o]-s[o-1]<=300)continue;let d=Math.max(s[o-1]+60,u),m=Math.min(s[o],c);m>d&&N.push({start:d,end:m})}return{empty:!1,from:u,to:c,lanes:k,stays:g,gaps:N,moves:M}}var Nt={Join:"join",Good:"good",Slow:"slow",Bad:"bad"};function U(t){var n;return(n=Nt[t])!=null?n:"bad"}var Ot=[60,300,600,900,1800,3600,7200,10800,21600,43200,86400];function Y(t,n,e=8,s=0){var u;let r=n-t;if(!(r>0))return[];let i=(u=Ot.find(c=>r/c<=e))!=null?u:86400*Math.ceil(r/(86400*e)),p=[];for(let c=Math.ceil((t+s)/i)*i-s;c<=n;c+=i)p.push(c);return p}(function(){var t=document.createElement("style");t.setAttribute("data-viz",""),t.textContent=`.rt-container {
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
.rt-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
`,document.head.appendChild(t)})();var P={"2.4 GHz":"#4c9a92","5 GHz":"#4a72b8","6 GHz":"#8a6bb5"},Q={join:"#9aa3ad",good:"#2fa34f",slow:"#dfb000",bad:"#e5493f"},q={dark:{text:"#dfe3e8",muted:"#8a929b",axis:"#5b6670",bg:"#1b1f24",lane:"#2c333b",gap:"#8a929b"},light:{text:"#1f2933",muted:"#5f6b76",axis:"#b8c0c8",bg:"#ffffff",lane:"#e6eaee",gap:"#5f6b76"}},w=118,A=14,_=4,$=24,K=12,_t=22,V=8,E=document.createElement("div");E.className="rt-container";var x=document.createElement("div");x.className="rt-body";var b=document.createElement("div");b.className="rt-tip";b.hidden=!0;E.append(x,b);(document.getElementById("root")||document.body).appendChild(E);var l={data:null,loading:!1,theme:"dark",model:null,hover:null,width:0,showDate:!1,tzOff:0},Z=()=>q[l.theme]||q.dark;function Ct(t){var r;let n=((t==null?void 0:t.fields)||[]).map(i=>{var p;return(p=i.name)!=null?p:i}),e=(t==null?void 0:t.columns)||[],s=((r=e[0])==null?void 0:r.length)||0;return Array.from({length:s},(i,p)=>Object.fromEntries(n.map((u,c)=>[u,e[c][p]])))}function L(t){return String(t!=null?t:"").replace(/[&<>"']/g,n=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[n])}var C=t=>String(t).padStart(2,"0"),At=t=>/^[+-]\d{4}$/.test(t||"")?(t[0]==="-"?-1:1)*(Number(t.slice(1,3))*3600+Number(t.slice(3))*60):0;function v(t){let n=new Date((t+l.tzOff)*1e3),e=`${C(n.getUTCHours())}:${C(n.getUTCMinutes())}`;return l.showDate?`${C(n.getUTCMonth()+1)}-${C(n.getUTCDate())} ${e}`:e}function Pt(t){return t<60?`${Math.round(t)} s`:t<3600?`${Math.floor(t/60)} min`:`${Math.floor(t/3600)} h ${Math.floor(t%3600/60)} min`}var zt=t=>t==="none"?"First join":t||"-";function jt(t){let n=l.model,e=t[0],s=Number(t.slice(1));if(e==="g"){let g=n.gaps[s];return`<b>Not seen ${v(g.start)} \u2013 ${v(g.end)}</b><br>(${Math.round((g.end-g.start)/60)} min)`}let r=n.stays[s],i=`${L(zt(r.roam))} \xB7 ${Number.isFinite(r.runLatency)?Math.round(r.runLatency)+" ms":"-"} \xB7 BSSID ${L(r.bssid||"-")}`,p=`<b>${L(r.ap)}</b> \xB7 ${L(r.band||"-")}`;if(e==="t")return`${p}<br>Roamed ${v(r.start)}<br>${i}`;let u=`${v(r.start)}${r.inRange?"":" (before range)"}`,c=`${v(r.end)}${r.endReason==="last"?" (last seen)":""}`;return`${p}<br>${u} \u2013 ${c} (${Pt(r.end-r.start)})<br>${i}`}function J(t,n){t&&x.querySelectorAll(`[data-h="${t}"]:not(.rt-hit)`).forEach(e=>e.classList.toggle("rt-hover",n))}function Ht(t,n){let e=E.getBoundingClientRect(),s=b.offsetWidth,r=b.offsetHeight,i=14,p=t-e.left+i;p+s>e.width&&(p=t-e.left-s-i);let u=Math.min(Math.max(0,n-e.top-r/2),Math.max(0,e.height-r));b.style.left=`${Math.max(0,p)}px`,b.style.top=`${u}px`}function tt(t,n,e){t!==l.hover&&(J(l.hover,!1),l.hover=t,J(t,!0),b.hidden=!t,t&&(b.innerHTML=jt(t))),t&&Ht(n,e)}x.addEventListener("pointermove",t=>{var e,s;let n=(s=(e=t.target).closest)==null?void 0:s.call(e,"[data-h]");tt(n?n.dataset.h:null,t.clientX,t.clientY)});x.addEventListener("pointerleave",()=>tt(null));function X(t){l.hover=null,b.hidden=!0,x.innerHTML=`<div class="rt-message" style="color:${Z().muted}">${L(t)}</div>`}function It(t){let n=Z(),e=Math.max(320,x.clientWidth||1200);l.width=x.clientWidth,l.showDate=t.to-t.from>86400;let s=e-w-A,r=t.to-t.from,i=a=>(w+(a-t.from)/r*s).toFixed(2),p=t.lanes.length*$,u=_+p+_t,c=a=>_+a*$,g=t.lanes.map((a,f)=>(f%2?`<rect x="${w}" y="${c(f)}" width="${s}" height="${$}" fill="${n.lane}" fill-opacity="0.4"/>`:"")+`<text x="${w-8}" y="${c(f)+$/2+4}" text-anchor="end" font-size="11" fill="${n.text}">${L(a)}</text>`).join(""),S=t.gaps.map((a,f)=>`<rect class="rt-gap" data-h="g${f}" x="${i(a.start)}" y="${_}" width="${(i(a.end)-i(a.start)).toFixed(2)}" height="${p}" fill="${n.gap}"/>`).join(""),k=t.stays.map((a,f)=>{if(!(a.barEnd>a.barStart))return"";let y=Math.max(1.5,Number(i(a.barEnd))-Number(i(a.barStart)));return`<rect data-h="s${f}" x="${i(a.barStart)}" y="${c(a.lane)+($-K)/2}" width="${y.toFixed(2)}" height="${K}" rx="2" fill="${P[a.band]||n.muted}"/>`}).join(""),M=a=>c(a)+$/2,N=(t.moves||[]).map(a=>`<line x1="${i(a.t)}" y1="${M(a.fromLane)}" x2="${i(a.t)}" y2="${M(a.toLane)}" stroke="${n.muted}" stroke-width="1.5" pointer-events="none"/>`).join(""),o=t.stays.map((a,f)=>{if(!a.inRange)return"";let y=Number(i(a.start)),nt=`<rect class="rt-tick" data-h="t${f}" x="${(y-1.5).toFixed(2)}" y="${c(a.lane)+2}" width="3" height="${$-4}" fill="${Q[U(a.category)]}" stroke="${n.bg}" stroke-width="1"/>`,et=`<rect class="rt-hit" data-h="t${f}" x="${(y-V).toFixed(2)}" y="${c(a.lane)}" width="${V*2}" height="${$}"/>`;return nt+et}).join(""),d=_+p,m=`<line x1="${w}" y1="${d}" x2="${e-A}" y2="${d}" stroke="${n.axis}"/>`+Y(t.from,t.to,8,l.tzOff).map(a=>{let f=Number(i(a)),y=f<w+24?"start":f>e-A-24?"end":"middle";return`<line x1="${f}" y1="${d}" x2="${f}" y2="${d+4}" stroke="${n.axis}"/><text x="${f}" y="${d+16}" text-anchor="${y}" font-size="10" fill="${n.muted}">${v(a)}</text>`}).join(""),D=Rt(n);x.innerHTML=`<svg viewBox="0 0 ${e} ${u}" role="img" style="color:${n.text}">${S}${g}${k}${N}${o}${m}</svg>${D}`}function Rt(t){let n=Object.keys(P).map(r=>`<span><i class="rt-swatch" style="background:${P[r]}"></i>${r}</span>`).join(""),e=[["good","Good (under 100 ms)"],["slow","Slow (100\u2013500 ms)"],["bad","Bad (over 500 ms)"],["join","First join"]].map(([r,i])=>`<span><i class="rt-swatch rt-tick-swatch" style="background:${Q[r]}"></i>${i}</span>`).join(""),s=`<span><i class="rt-swatch" style="background:${t.gap};opacity:0.3"></i>Offline (not seen over ${300/60} min)</span>`;return`<div class="rt-legend" style="color:${t.muted};padding:0 ${A}px 0 ${w}px"><div style="display:flex;gap:16px;flex-wrap:wrap">${n}</div><div style="display:flex;gap:16px;flex-wrap:wrap">${e}${s}</div></div>`}function z(){var e;if(l.loading)return X("Loading roaming...");let t=l.data?Ct(l.data):[];l.tzOff=At((e=t[0])==null?void 0:e.tz_offset),l.model=W(t,Date.now()/1e3);let n=l.model;if(n.empty||n.lanes.length===0||!(n.to>n.from))return X("No roaming data in this range");l.hover=null,b.hidden=!0,It(n)}O.addDataSourcesListener(({dataSources:t,loading:n})=>{var e;l.loading=n,l.data=((e=t==null?void 0:t.primary)==null?void 0:e.data)||null,z()},{invokeImmediately:!0});O.addThemeListener(({theme:t})=>{l.theme=t,E.dataset.theme=t,z()},{invokeImmediately:!0});window.ResizeObserver&&new ResizeObserver(()=>{l.model&&x.clientWidth!==l.width&&z()}).observe(E);
