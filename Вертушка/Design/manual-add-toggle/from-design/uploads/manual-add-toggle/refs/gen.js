// Генератор standalone SVG винилов — порт VinylSpinner.tsx (Mobile/components).
// Пишет по файлу на вариант в ./svg/. Векторные, импортируются в Claude Design.
const fs = require('fs');
const path = require('path');

function hexToRgb(hex){const n=parseInt(hex.replace('#',''),16);return{r:(n>>16)&255,g:(n>>8)&255,b:n&255};}
function rgbToHex(r,g,b){return '#'+[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');}
function darken(hex,a){const{r,g,b}=hexToRgb(hex);return rgbToHex(r*(1-a),g*(1-a),b*(1-a));}
function saturate(hex,sa=0.1,br=0.08){let{r,g,b}=hexToRgb(hex);let rn=r/255,gn=g/255,bn=b/255;const max=Math.max(rn,gn,bn),min=Math.min(rn,gn,bn);let h=0,s=0;const l=(max+min)/2;if(max!==min){const d=max-min;s=l>0.5?d/(2-max-min):d/(max+min);if(max===rn)h=(gn-bn)/d+(gn<bn?6:0);else if(max===gn)h=(bn-rn)/d+2;else h=(rn-gn)/d+4;h/=6;}const sN=Math.min(1,s+sa),lN=Math.min(1,l+br);function h2r(p,q,t){if(t<0)t+=1;if(t>1)t-=1;if(t<1/6)return p+(q-p)*6*t;if(t<1/2)return q;if(t<2/3)return p+(q-p)*(2/3-t)*6;return p;}let nr,ng,nb;if(sN===0){nr=ng=nb=lN;}else{const q=lN<0.5?lN*(1+sN):lN+sN-lN*sN;const p=2*lN-q;nr=h2r(p,q,h+1/3);ng=h2r(p,q,h);nb=h2r(p,q,h-1/3);}return rgbToHex(nr*255,ng*255,nb*255);}

function buildVinyl(primary, secondary, type, size){
  const scale=size/220, cx=size/2, cy=size/2;
  const isTrans = type==='translucent';
  const colorBright=saturate(primary,0.12,0.1), colorMid=primary, colorDark=darken(primary,0.28), colorEdge=darken(primary,0.48);
  const edgeR=110*scale, labelR=38*scale, labelInnerR=5*scale;
  const grooveCount=26, grooves=Array.from({length:grooveCount},(_,i)=>44*scale+(i/(grooveCount-1))*60*scale);
  const grooveSW=isTrans?0.6:0.45, grooveOp=isTrans?0.34:0.22;
  const discFill=isTrans?0.85:1, uid=primary.replace('#','')+'_'+type;
  let overlay='';
  if(type==='marble' && secondary){
    overlay=`<g clip-path="url(#cl-${uid})">
      <path d="M${-110*scale+cx},${-30*scale+cy} C${-60*scale+cx},${-80*scale+cy} ${20*scale+cx},${-10*scale+cy} ${60*scale+cx},${40*scale+cy} C${90*scale+cx},${75*scale+cy} ${110*scale+cx},${30*scale+cy} ${110*scale+cx},${-10*scale+cy}" stroke="${secondary}" stroke-width="${14*scale}" stroke-opacity="0.45" fill="none" stroke-linecap="round"/>
      <path d="M${-80*scale+cx},${60*scale+cy} C${-30*scale+cx},${20*scale+cy} ${40*scale+cx},${80*scale+cy} ${90*scale+cx},${30*scale+cy}" stroke="${secondary}" stroke-width="${7*scale}" stroke-opacity="0.35" fill="none" stroke-linecap="round"/>
      <path d="M${-50*scale+cx},${-70*scale+cy} C${10*scale+cx},${-40*scale+cy} ${50*scale+cx},${10*scale+cy} ${20*scale+cx},${70*scale+cy}" stroke="${secondary}" stroke-width="${5*scale}" stroke-opacity="0.3" fill="none" stroke-linecap="round"/>
    </g>`;
  }
  if(type==='splatter' && secondary){
    const s=scale; const blobs=[[-55,-62,-45,-78,-30,-65,-35,-50],[40,-70,55,-60,48,-42,35,-50],[65,20,80,10,85,30,70,38],[-75,35,-60,25,-55,45,-70,52],[20,65,35,55,40,72,25,80],[-30,75,-15,68,-10,82,-28,88],[55,-25,68,-35,72,-15,60,-8],[-65,-10,-50,-20,-45,-5,-58,5]];
    let polys=blobs.map((p,i)=>`<polygon points="${p.map((v,j)=>(v*s+(j%2?cy:cx))).join(' ')}" fill="${secondary}" fill-opacity="${i%3===0?1:0.7}"/>`).join('');
    const drops=[[48,-50,3.5],[-40,-40,2],[70,-45,2],[-60,55,2],[30,-55,2],[-25,70,2],[80,40,3.5],[-80,-30,2],[55,60,2],[-45,-75,2],[15,82,2],[-70,10,3.5]];
    let circ=drops.map(([dx,dy,r])=>`<circle cx="${dx*s+cx}" cy="${dy*s+cy}" r="${r*s}" fill="${secondary}" fill-opacity="0.8"/>`).join('');
    overlay=`<g clip-path="url(#cl-${uid})">${polys}${circ}</g>`;
  }
  const groovePaths=grooves.map(gr=>`<circle cx="${cx}" cy="${cy}" r="${gr}" fill="none" stroke="${darken(primary,0.6)}" stroke-width="${grooveSW}"/>`).join('');
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="bg-${uid}" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="${colorBright}"/><stop offset="40%" stop-color="${colorMid}"/>
      <stop offset="78%" stop-color="${colorDark}"/><stop offset="100%" stop-color="${colorEdge}"/>
    </radialGradient>
    <clipPath id="cl-${uid}"><circle cx="${cx}" cy="${cy}" r="${edgeR}"/></clipPath>
  </defs>
  <circle cx="${cx}" cy="${cy}" r="${edgeR}" fill="url(#bg-${uid})" fill-opacity="${discFill}"/>
  ${overlay}
  <g opacity="${grooveOp}" clip-path="url(#cl-${uid})">${groovePaths}</g>
  <circle cx="${cx}" cy="${cy}" r="${edgeR-1}" fill="none" stroke="rgba(0,0,0,0.30)" stroke-width="${3*scale}"/>
  <circle cx="${cx}" cy="${cy}" r="${edgeR-3.5*scale}" fill="none" stroke="rgba(0,0,0,0.12)" stroke-width="${2*scale}"/>
  <circle cx="${cx}" cy="${cy}" r="${labelR}" fill="#1C1D3A"/>
  <text x="${cx}" y="${cy-12*scale}" text-anchor="middle" dominant-baseline="middle" font-size="${8*scale}" fill="#B8BCDB" font-family="'Rubik Mono One', monospace" letter-spacing="${1*scale}">Вертушка</text>
  <circle cx="${cx}" cy="${cy}" r="${labelInnerR}" fill="#000"/>
  <text x="${cx}" y="${cy+12*scale}" text-anchor="middle" dominant-baseline="middle" font-size="${5*scale}" fill="#5C6080" font-family="Inter, sans-serif" letter-spacing="${1.5*scale}">33⅓ RPM</text>
</svg>`;
}

const variants=[
  {f:'vinyl-red',    p:'#E53935', s:null,      t:'solid'},
  {f:'vinyl-blue',   p:'#1E88E5', s:null,      t:'solid'},
  {f:'vinyl-green',  p:'#43A047', s:null,      t:'solid'},
  {f:'vinyl-orange', p:'#FB8C00', s:null,      t:'solid'},
  {f:'vinyl-yellow', p:'#FDD835', s:null,      t:'solid'},
  {f:'vinyl-translucent-purple', p:'#7E57C2', s:null, t:'translucent'},
  {f:'vinyl-splatter', p:'#E53935', s:'#1A1A1A', t:'splatter'},
  {f:'vinyl-marble',   p:'#1A237E', s:'#FFFFFF', t:'marble'},
];
const outDir = path.join(__dirname, 'svg');
fs.mkdirSync(outDir, {recursive:true});
variants.forEach(v=>{
  fs.writeFileSync(path.join(outDir, v.f+'.svg'), buildVinyl(v.p, v.s, v.t, 256));
});
console.log('wrote', variants.length, 'svg files to', outDir);
