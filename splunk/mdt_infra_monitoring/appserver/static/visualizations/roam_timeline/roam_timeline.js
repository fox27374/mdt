var nt=Object.defineProperty,et=Object.defineProperties;var ot=Object.getOwnPropertyDescriptors;var P=Object.getOwnPropertySymbols;var rt=Object.prototype.hasOwnProperty,it=Object.prototype.propertyIsEnumerable;var z=(t,n,e)=>n in t?nt(t,n,{enumerable:!0,configurable:!0,writable:!0,value:e}):t[n]=e,H=(t,n)=>{for(var e in n||(n={}))rt.call(n,e)&&z(t,e,n[e]);if(P)for(var e of P(n))it.call(n,e)&&z(t,e,n[e]);return t},j=(t,n)=>et(t,ot(n));var I=Object.defineProperty,F=(t,n)=>{let e={};for(var i in t)I(e,i,{get:t[i],enumerable:!0});return n||I(e,Symbol.toStringTag,{value:"Module"}),e};var D=F({addDataSourcesListener:()=>st,addDimensionsListener:()=>ft,addDrilldownListener:()=>wt,addErrorListener:()=>vt,addModeListener:()=>ut,addOptionsListener:()=>lt,addThemeListener:()=>mt,addTokensListener:()=>xt,clearError:()=>Lt,getDataSources:()=>dt,getDimensions:()=>ht,getError:()=>Et,getMode:()=>gt,getOptions:()=>ct,getTheme:()=>bt,getTokens:()=>$t,setError:()=>St,setOptions:()=>pt,triggerDrilldown:()=>yt}),at=new Proxy({},{get(){throw new Error("DashboardExtensionAPI is not available. Make sure to run this code inside a Splunk Dashboard Extension iframe.")}}),R,p=(R=globalThis.DashboardExtensionAPI)!=null?R:at,st=p.addDataSourcesListener,dt=p.getDataSources,lt=p.addOptionsListener,ct=p.getOptions,pt=p.setOptions,ft=p.addDimensionsListener,ht=p.getDimensions,ut=p.addModeListener,gt=p.getMode,mt=p.addThemeListener,bt=p.getTheme,xt=p.addTokensListener,$t=p.getTokens,wt=p.addDrilldownListener,yt=p.triggerDrilldown,vt=p.addErrorListener,Et=p.getError,St=p.setError,Lt=p.clearError;var N=t=>t==null||t===""?NaN:Number(t);function kt(t,n,e,i){let r=null;for(let a of e)if(!(a<t-60)){if(r!==null&&a-r>300)return{end:Math.min(r+60,n),reason:"last"};if(a>=n)break;r=a}return Number.isFinite(n)?{end:n,reason:"next"}:r===null?{end:t,reason:"last"}:{end:Math.min(r+60,i),reason:"last"}}function G(t,n){let e=[],i=[],r=NaN,a=NaN;for(let o of t){r>0||(r=N(o.info_min_time)),Number.isFinite(a)||(a=N(o.info_max_time));let h=N(o.t);Number.isFinite(h)&&(o.kind==="assoc"?e.push(j(H({},o),{t:h})):o.kind==="seen"&&i.push(h))}if(e.sort((o,h)=>o.t-h.t),i.sort((o,h)=>o-h),e.length===0)return{empty:!0,from:NaN,to:NaN,lanes:[],stays:[],gaps:[]};let l=Math.min(e[0].t,i.length?i[0]:1/0),u=r>0?r:l,c=Number.isFinite(a)?a:n,g=[];e.forEach((o,h)=>{let w=h+1<e.length?e[h+1].t:1/0;if(o.t>c)return;let{end:s,reason:f}=kt(o.t,w,i,n),x=o.t>=u;!x&&s<=u||g.push({ap:o.ap,band:o.band,roam:o.roam,runLatency:N(o.run_latency),category:o.category,bssid:o.bssid,start:o.t,end:s,endReason:f,inRange:x,barStart:Math.max(o.t,u),barEnd:Math.min(s,c)})});let L=new Map,k=[];[...g].sort((o,h)=>o.barStart-h.barStart).forEach(o=>{L.has(o.ap)||(L.set(o.ap,k.length),k.push(o.ap))}),g.forEach(o=>{o.lane=L.get(o.ap)});let M=[];for(let o=1;o<i.length;o++){if(i[o]-i[o-1]<=300)continue;let h=Math.max(i[o-1]+60,u),w=Math.min(i[o],c);w>h&&M.push({start:h,end:w})}return{empty:!1,from:u,to:c,lanes:k,stays:g,gaps:M}}var Mt={Join:"join",Good:"good",Slow:"slow",Bad:"bad"};function B(t){var n;return(n=Mt[t])!=null?n:"bad"}var Dt=[60,300,600,900,1800,3600,7200,10800,21600,43200,86400];function W(t,n,e=8,i=0){var u;let r=n-t;if(!(r>0))return[];let a=(u=Dt.find(c=>r/c<=e))!=null?u:86400*Math.ceil(r/(86400*e)),l=[];for(let c=Math.ceil((t+i)/a)*a-i;c<=n;c+=a)l.push(c);return l}(function(){var t=document.createElement("style");t.setAttribute("data-viz",""),t.textContent=`.rt-container {
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
`,document.head.appendChild(t)})();var C={"2.4 GHz":"#4c9a92","5 GHz":"#4a72b8","6 GHz":"#8a6bb5"},J={join:"#9aa3ad",good:"#2fa34f",slow:"#dfb000",bad:"#e5493f"},U={dark:{text:"#dfe3e8",muted:"#8a929b",axis:"#5b6670",bg:"#1b1f24",lane:"#2c333b",gap:"#8a929b"},light:{text:"#1f2933",muted:"#5f6b76",axis:"#b8c0c8",bg:"#ffffff",lane:"#e6eaee",gap:"#5f6b76"}},y=118,_=14,O=4,$=24,Y=12,Ot=22,q=8,S=document.createElement("div");S.className="rt-container";var b=document.createElement("div");b.className="rt-body";var m=document.createElement("div");m.className="rt-tip";m.hidden=!0;S.append(b,m);(document.getElementById("root")||document.body).appendChild(S);var d={data:null,loading:!1,theme:"dark",model:null,hover:null,width:0,showDate:!1,tzOff:0},X=()=>U[d.theme]||U.dark;function Tt(t){var r;let n=((t==null?void 0:t.fields)||[]).map(a=>{var l;return(l=a.name)!=null?l:a}),e=(t==null?void 0:t.columns)||[],i=((r=e[0])==null?void 0:r.length)||0;return Array.from({length:i},(a,l)=>Object.fromEntries(n.map((u,c)=>[u,e[c][l]])))}function E(t){return String(t!=null?t:"").replace(/[&<>"']/g,n=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[n])}var T=t=>String(t).padStart(2,"0"),_t=t=>/^[+-]\d{4}$/.test(t||"")?(t[0]==="-"?-1:1)*(Number(t.slice(1,3))*3600+Number(t.slice(3))*60):0;function v(t){let n=new Date((t+d.tzOff)*1e3),e=`${T(n.getUTCHours())}:${T(n.getUTCMinutes())}`;return d.showDate?`${T(n.getUTCMonth()+1)}-${T(n.getUTCDate())} ${e}`:e}function Ct(t){return t<60?`${Math.round(t)} s`:t<3600?`${Math.floor(t/60)} min`:`${Math.floor(t/3600)} h ${Math.floor(t%3600/60)} min`}var At=t=>t==="none"?"First join":t||"-";function Pt(t){let n=d.model,e=t[0],i=Number(t.slice(1));if(e==="g"){let g=n.gaps[i];return`<b>Not seen ${v(g.start)} \u2013 ${v(g.end)}</b><br>(${Math.round((g.end-g.start)/60)} min)`}let r=n.stays[i],a=`${E(At(r.roam))} \xB7 ${Number.isFinite(r.runLatency)?Math.round(r.runLatency)+" ms":"-"} \xB7 BSSID ${E(r.bssid||"-")}`,l=`<b>${E(r.ap)}</b> \xB7 ${E(r.band||"-")}`;if(e==="t")return`${l}<br>Roamed ${v(r.start)}<br>${a}`;let u=`${v(r.start)}${r.inRange?"":" (before range)"}`,c=`${v(r.end)}${r.endReason==="last"?" (last seen)":""}`;return`${l}<br>${u} \u2013 ${c} (${Ct(r.end-r.start)})<br>${a}`}function K(t,n){t&&b.querySelectorAll(`[data-h="${t}"]:not(.rt-hit)`).forEach(e=>e.classList.toggle("rt-hover",n))}function zt(t,n){let e=S.getBoundingClientRect(),i=m.offsetWidth,r=m.offsetHeight,a=14,l=t-e.left+a;l+i>e.width&&(l=t-e.left-i-a);let u=Math.min(Math.max(0,n-e.top-r/2),Math.max(0,e.height-r));m.style.left=`${Math.max(0,l)}px`,m.style.top=`${u}px`}function Q(t,n,e){t!==d.hover&&(K(d.hover,!1),d.hover=t,K(t,!0),m.hidden=!t,t&&(m.innerHTML=Pt(t))),t&&zt(n,e)}b.addEventListener("pointermove",t=>{var e,i;let n=(i=(e=t.target).closest)==null?void 0:i.call(e,"[data-h]");Q(n?n.dataset.h:null,t.clientX,t.clientY)});b.addEventListener("pointerleave",()=>Q(null));function V(t){d.hover=null,m.hidden=!0,b.innerHTML=`<div class="rt-message" style="color:${X().muted}">${E(t)}</div>`}function Ht(t){let n=X(),e=Math.max(320,b.clientWidth||1200);d.width=b.clientWidth,d.showDate=t.to-t.from>86400;let i=e-y-_,r=t.to-t.from,a=s=>(y+(s-t.from)/r*i).toFixed(2),l=t.lanes.length*$,u=O+l+Ot,c=s=>O+s*$,g=t.lanes.map((s,f)=>(f%2?`<rect x="${y}" y="${c(f)}" width="${i}" height="${$}" fill="${n.lane}" fill-opacity="0.4"/>`:"")+`<text x="${y-8}" y="${c(f)+$/2+4}" text-anchor="end" font-size="11" fill="${n.text}">${E(s)}</text>`).join(""),L=t.gaps.map((s,f)=>`<rect class="rt-gap" data-h="g${f}" x="${a(s.start)}" y="${O}" width="${(a(s.end)-a(s.start)).toFixed(2)}" height="${l}" fill="${n.gap}"/>`).join(""),k=t.stays.map((s,f)=>{if(!(s.barEnd>s.barStart))return"";let x=Math.max(1.5,Number(a(s.barEnd))-Number(a(s.barStart)));return`<rect data-h="s${f}" x="${a(s.barStart)}" y="${c(s.lane)+($-Y)/2}" width="${x.toFixed(2)}" height="${Y}" rx="2" fill="${C[s.band]||n.muted}"/>`}).join(""),M=t.stays.map((s,f)=>{if(!s.inRange)return"";let x=Number(a(s.start)),Z=`<rect class="rt-tick" data-h="t${f}" x="${(x-1.5).toFixed(2)}" y="${c(s.lane)+2}" width="3" height="${$-4}" fill="${J[B(s.category)]}" stroke="${n.bg}" stroke-width="1"/>`,tt=`<rect class="rt-hit" data-h="t${f}" x="${(x-q).toFixed(2)}" y="${c(s.lane)}" width="${q*2}" height="${$}"/>`;return Z+tt}).join(""),o=O+l,h=`<line x1="${y}" y1="${o}" x2="${e-_}" y2="${o}" stroke="${n.axis}"/>`+W(t.from,t.to,8,d.tzOff).map(s=>{let f=Number(a(s)),x=f<y+24?"start":f>e-_-24?"end":"middle";return`<line x1="${f}" y1="${o}" x2="${f}" y2="${o+4}" stroke="${n.axis}"/><text x="${f}" y="${o+16}" text-anchor="${x}" font-size="10" fill="${n.muted}">${v(s)}</text>`}).join(""),w=jt(n);b.innerHTML=`<svg viewBox="0 0 ${e} ${u}" role="img" style="color:${n.text}">${L}${g}${k}${M}${h}</svg>${w}`}function jt(t){let n=Object.keys(C).map(r=>`<span><i class="rt-swatch" style="background:${C[r]}"></i>${r}</span>`).join(""),e=[["good","Good (under 100 ms)"],["slow","Slow (100\u2013500 ms)"],["bad","Bad (over 500 ms)"],["join","First join"]].map(([r,a])=>`<span><i class="rt-swatch rt-tick-swatch" style="background:${J[r]}"></i>${a}</span>`).join(""),i=`<span><i class="rt-swatch" style="background:${t.gap};opacity:0.3"></i>Offline (not seen over ${300/60} min)</span>`;return`<div class="rt-legend" style="color:${t.muted}"><div style="display:flex;gap:16px;flex-wrap:wrap">${n}</div><div style="display:flex;gap:16px;flex-wrap:wrap">${e}${i}</div></div>`}function A(){var e;if(d.loading)return V("Loading roaming...");let t=d.data?Tt(d.data):[];d.tzOff=_t((e=t[0])==null?void 0:e.tz_offset),d.model=G(t,Date.now()/1e3);let n=d.model;if(n.empty||n.lanes.length===0||!(n.to>n.from))return V("No roaming data in this range");d.hover=null,m.hidden=!0,Ht(n)}D.addDataSourcesListener(({dataSources:t,loading:n})=>{var e;d.loading=n,d.data=((e=t==null?void 0:t.primary)==null?void 0:e.data)||null,A()},{invokeImmediately:!0});D.addThemeListener(({theme:t})=>{d.theme=t,S.dataset.theme=t,A()},{invokeImmediately:!0});window.ResizeObserver&&new ResizeObserver(()=>{d.model&&b.clientWidth!==d.width&&A()}).observe(S);
