'use strict';
const $ = id => document.getElementById(id);
let places = [], graph = null, result = null, map = null, graphLayer, placeLayer, routeLayer, traceLayer;
let traceIndex = 0, timer = null, edgePage = 0, busy = false;
const mode = () => document.querySelector('input[name="mode"]:checked').value;
const source = () => $('source').value;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metres = n => n >= 1000 ? `${(n/1000).toFixed(2)} km` : `${Math.round(n)} m`;
const money = n => new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n);

function status(message, error=false) {
  $('status').textContent = message;
  $('status').classList.toggle('error',error);
}
async function api(path, body) {
  const response = await fetch(`/api/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request failed.');
  return data;
}
function setBusy(value) {
  busy = value;
  ['find-route','load','source','start','end','swap','import'].forEach(id => $(id).disabled = value);
  $('load').disabled=value || source()==='sample';
  ['base','per-km','included'].forEach(id => $(id).disabled=value);
  document.querySelectorAll('input[name="mode"]').forEach(el => el.disabled=value);
  $('find-route').innerHTML = value ? 'Working on the network…' : 'Find shortest route <span>→</span>';
}
function stopPlayback() {
  clearInterval(timer); timer=null; $('play-trace').textContent='Play ▷';
}
function clearResult() {
  stopPlayback(); result=null; traceIndex=0; $('result').hidden=true;
  $('visited-count').textContent='—';
  $('trace-body').innerHTML='<tr><td colspan="4" class="empty-cell">Find a route to follow Dijkstra’s algorithm.</td></tr>';
  $('trace-caption').textContent='Find a route to follow the algorithm, one settled vertex at a time.';
  ['next-trace','play-trace','reset-trace'].forEach(id => $(id).disabled=true);
  if (map) {routeLayer.clearLayers();traceLayer.clearLayers();}
  drawPlaces();
}
function initialiseMap() {
  if (typeof L === 'undefined') {
    $('map-fallback').hidden=false;
    return;
  }
  map=L.map('map',{zoomControl:false}).setView([28.6888,77.2102],15);
  L.control.zoom({position:'bottomright'}).addTo(map);
  let failures=0;
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
    maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  tiles.on('tileerror',()=>{if(++failures===3) status('Map tiles could not load. Check your internet connection; the graph and algorithm panels still work.',true);});
  graphLayer=L.layerGroup().addTo(map);placeLayer=L.layerGroup().addTo(map);
  routeLayer=L.layerGroup().addTo(map);traceLayer=L.layerGroup().addTo(map);
  drawPlaces();
}
function drawPlaces() {
  if (!map) return;
  placeLayer.clearLayers();
  places.forEach((p,i)=>{
    const isStart=result && p.id===result.start.id, isEnd=result && p.id===result.end.id;
    const label=isStart?'A':isEnd?'B':String(i+1).padStart(2,'0');
    const endpoint=isStart||isEnd;
    const icon=L.divIcon({className:`place-marker${endpoint?' endpoint':''}${isEnd?' finish':''}`,html:label,iconSize:endpoint?[32,32]:[26,26],iconAnchor:endpoint?[16,16]:[13,13]});
    const marker=L.marker([p.lat,p.lon],{icon,alt:p.name}).addTo(placeLayer);
    const content=document.createElement('div');
    const title=document.createElement('strong');title.textContent=p.name;content.append(title);
    const note=document.createElement('p');note.textContent=p.note;content.append(note);
    const use=document.createElement('button');use.textContent='Set as destination →';use.className='secondary';
    use.onclick=()=>{if(!busy){$('end').value=p.id;clearResult();status('Destination selected. Find a route when ready.');map.closePopup();}};
    content.append(use);marker.bindPopup(content);
  });
}
function renderGraph(data) {
  graph=data; edgePage=0;
  $('vertex-count').textContent=data.vertices.toLocaleString('en-IN');
  $('edge-count').textContent=data.edges.toLocaleString('en-IN');
  $('network-label').textContent=data.source==='sample'?'Sample teaching graph':'OpenStreetMap streets';
  $('network-meta').textContent=data.source==='sample'?'Invented edge weights. Not for navigation.':`Cached ${new Date(data.fetched_at).toLocaleDateString()} · ${mode()==='walk'?'walking':'motor-vehicle'} profile`;
  $('sample-watermark').hidden=data.source!=='sample';
  $('load').disabled=data.source==='sample';
  if(map){
    graphLayer.clearLayers();
    const seen=new Set();
    data.links.forEach(edge=>{
      const key=[edge.u,edge.v].sort().join(':');
      if(seen.has(key)) return; seen.add(key);
      L.polyline([data.nodes[edge.u],data.nodes[edge.v]],{color:'#80946d',weight:data.source==='sample'?2:1.5,opacity:.5,dashArray:data.source==='sample'?'5 5':undefined}).addTo(graphLayer);
    });
    Object.entries(data.nodes).forEach(([key,coord])=>L.circleMarker(coord,{radius:data.source==='sample'?5:2,weight:0,fillColor:'#647f54',fillOpacity:.65}).bindTooltip(`Vertex ${esc(key)}`).addTo(graphLayer));
    toggleGraph();
  }
  renderEdges();
}
function toggleGraph(){if(map){if($('show-graph').checked) graphLayer.addTo(map);else map.removeLayer(graphLayer);}}
async function fetchGraph(){
  clearResult();
  const data=await api('graph',{source:source(),mode:mode()});renderGraph(data);
}
async function loadStreets(refresh=false){
  if(busy)return;
  clearResult();setBusy(true);status('Downloading the OSM street network. This can take up to 90 seconds on the first run…');
  try{
    const data=await api('load',{mode:mode(),refresh});
    $('source').value='osm';renderGraph(data);
    status('Street network ready. Choose your destinations and find a route.');
  }catch(error){status(error.message,true);}
  finally{setBusy(false);}
}
function groupedEdges(edges){
  return edges.reduce((groups,edge)=>{
    const last=groups.at(-1);
    if(last && last.name===edge.name) last.distance+=edge.weight;
    else groups.push({name:edge.name,distance:edge.weight});
    return groups;
  },[]);
}
function renderRoute(data){
  result=data;traceIndex=0;stopPlayback();
  $('result').hidden=false;
  $('distance').textContent=metres(data.distance_m);
  $('duration').textContent=`${Math.ceil(data.duration_minutes)} min`;
  $('fare').textContent=data.mode==='walk'?'Free':`₹${money(data.fare)}`;
  $('fare-label').textContent=data.mode==='walk'?'walking fare':'project estimate';
  $('visited-count').textContent=data.settled_count.toLocaleString('en-IN');
  $('snap-note').textContent=data.source==='sample'?'Sample graph: illustrative distances, fares and connections. Not a street route.':`Street-to-street route. Access gaps: ${Math.round(data.start_snap_m)} m at start + ${Math.round(data.end_snap_m)} m at arrival (excluded from totals).`;
  const groups=groupedEdges(data.edges);
  $('directions').innerHTML=groups.length?groups.map(g=>`<li>${esc(g.name)} <small>${metres(g.distance)}</small></li>`).join(''):'<li>Both selections connect to the same vertex. No street travel is required.</li>';
  $('destination-note').textContent=data.end.note;
  if(map){
    routeLayer.clearLayers();traceLayer.clearLayers();
    if(data.geometry.length>1){
      L.polyline(data.geometry,{color:'#fffefa',weight:9,opacity:.95}).addTo(routeLayer);
      L.polyline(data.geometry,{color:'#234c3a',weight:5,opacity:1,dashArray:data.source==='sample'?'8 7':undefined}).addTo(routeLayer);
    }
    if(data.source==='osm'){
      [[[data.start.lat,data.start.lon],data.geometry[0]],[[data.end.lat,data.end.lon],data.geometry.at(-1)]].forEach(pair=>L.polyline(pair,{color:'#ad633e',weight:2,dashArray:'4 6'}).addTo(routeLayer));
    }
    drawPlaces();
    const bounds=L.latLngBounds([...data.geometry,[data.start.lat,data.start.lon],[data.end.lat,data.end.lon]]);
    map.fitBounds(bounds,{padding:[65,75],maxZoom:17});
  }
  renderTrace();
}
function renderTrace(){
  if(!result)return;
  const shown=result.steps.slice(0,traceIndex);
  $('trace-caption').textContent=`Step ${traceIndex} of ${result.steps.length} · ${traceIndex===result.steps.length?'Destination settled. The shortest path is final.':'Extract the smallest tentative distance, then relax its outgoing edges.'}`;
  // Keep rendering bounded for large graphs, while the full trace stays in export.
  const start=Math.max(0,shown.length-100);
  $('trace-body').innerHTML=shown.length?shown.slice(start).map((step,i)=>`<tr class="${i+start===shown.length-1?'current':''}"><td>${i+start+1}</td><td>${esc(step.node)}</td><td>${step.distance.toFixed(1)} m</td><td>${step.relaxations.length?step.relaxations.map(r=>`${esc(r.to)}: ${r.old===null?'∞':r.old.toFixed(1)} → ${r.new.toFixed(1)} m`).join(' · '):'—'}</td></tr>`).join(''):'<tr><td colspan="4" class="empty-cell">Initialise: d(start) = 0; all other distances = ∞. Press Next step.</td></tr>';
  $('next-trace').disabled=traceIndex>=result.steps.length;
  $('play-trace').disabled=traceIndex>=result.steps.length;
  $('reset-trace').disabled=false;
  if(map){
    traceLayer.clearLayers();
    shown.forEach(step=>L.circleMarker(graph.nodes[step.node],{radius:4,color:'#a86a38',weight:1,fillColor:'#d99a57',fillOpacity:.9}).addTo(traceLayer));
    const last=shown.at(-1);
    if(last)L.circleMarker(graph.nodes[last.node],{radius:8,color:'#a86a38',weight:2,fillOpacity:.2}).bindTooltip(`Settled ${esc(last.node)} · ${last.distance.toFixed(1)} m`).addTo(traceLayer);
  }
  const wrap=$('trace-body').closest('.table-wrap');wrap.scrollTop=wrap.scrollHeight;
}
function nextTrace(){if(result && traceIndex<result.steps.length){traceIndex++;renderTrace();}if(result && traceIndex>=result.steps.length)stopPlayback();}
function renderEdges(){
  if(!graph)return;
  const query=$('edge-search').value.toLowerCase();
  const edges=graph.links.filter(e=>`${e.u} ${e.v} ${e.name}`.toLowerCase().includes(query));
  const count=Math.max(1,Math.ceil(edges.length/50));edgePage=Math.max(0,Math.min(edgePage,count-1));
  $('edge-body').innerHTML=edges.slice(edgePage*50,(edgePage+1)*50).map(e=>`<tr><td>${esc(e.u)}</td><td>${esc(e.v)}</td><td>${e.weight.toFixed(1)}</td><td>${esc(e.name)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty-cell">No matching edges.</td></tr>';
  $('edge-caption').textContent=`${edges.length.toLocaleString()} directed edges${query?' matching your filter':''}. Opposite directions are separate edges. Full precision is used for routing.`;
  $('page-number').textContent=`Page ${edgePage+1} of ${count}`;
  $('prev-page').disabled=edgePage===0;$('next-page').disabled=edgePage===count-1;
}
function download(filename,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

async function init(){
  try{
    const response=await fetch('/api/config');if(!response.ok)throw new Error('Could not read app configuration.');
    const config=await response.json();places=config.destinations;
    for(const id of ['start','end']){
      $(id).innerHTML=places.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    }
    $('end').value='kamla';
    $('osm-query').textContent=config.query;
    $('overpass-link').href=`https://overpass-turbo.eu/?Q=${encodeURIComponent(config.query)}`;
    initialiseMap();
    $('route-form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;setBusy(true);clearResult();status('Running Dijkstra’s algorithm…');
      try{
        if(!graph && source()==='osm'){
          status('Downloading OSM streets before routing. The first download can take up to 90 seconds…');
          const network=await api('load',{mode:mode()});renderGraph(network);config.osm_ready=true;
        }
        const data=await api('route',{source:source(),mode:mode(),start:$('start').value,end:$('end').value,
          fare:{base:Number($('base').value),per_km:Number($('per-km').value),included_km:Number($('included').value)}});
        renderRoute(data);status(data.source==='sample'?'Sample route found. Classroom weights; not for navigation.':'Shortest street route found. Explore the algorithm’s trace below.');
      }catch(error){status(error.message,true);}
      finally{setBusy(false);}
    };
    $('swap').onclick=()=>{const start=$('start').value;$('start').value=$('end').value;$('end').value=start;clearResult();};
    ['start','end'].forEach(id=>$(id).onchange=()=>clearResult());
    document.querySelectorAll('input[name="mode"]').forEach(input=>input.onchange=async()=>{
      clearResult();setBusy(true);
      const walk=mode()==='walk';$('fare-details').hidden=walk;
      $('base').value=mode()==='auto'?30:20;$('per-km').value=mode()==='auto'?12:10;$('included').value=1;
      try{await fetchGraph();status('Transport mode changed. Find a route to update your result.');}catch(error){status(error.message,true);}
      finally{setBusy(false);}
    });
    $('fare-details').hidden=true;
    ['base','per-km','included'].forEach(id=>$(id).oninput=()=>clearResult());
    $('load').onclick=()=>loadStreets(!!graph && source()==='osm');
    $('source').onchange=async()=>{
      clearResult();graph=null;if(map)graphLayer.clearLayers();
      $('sample-watermark').hidden=source()!=='sample';
      $('vertex-count').textContent='—';$('edge-count').textContent='—';
      $('edge-body').innerHTML='';$('network-label').textContent=source()==='sample'?'Sample teaching graph':'OpenStreetMap streets';
      $('network-meta').textContent='';
      if(source()==='osm'&&!config.osm_ready){await loadStreets();return;}
      setBusy(true);
      try{await fetchGraph();status(source()==='sample'?'Sample graph ready: 12 vertices and invented classroom weights.':'OSM street network ready.');}
      catch(error){status(error.message,true);}
      finally{setBusy(false);}
    };
    $('import').onchange=async event=>{
      const file=event.target.files[0];if(!file)return;
      setBusy(true);clearResult();status('Reading your OSM street data…');
      try{
        if(file.size>19_000_000)throw new Error('Use an OSM extract smaller than 19 MB.');
        const payload=JSON.parse(await file.text());
        const data=await api('import',{payload,mode:mode()});
        $('source').value='osm';config.osm_ready=true;renderGraph(data);status('Imported and cached the OSM network. Ready to route.');
      }catch(error){status(error.message,true);}
      finally{setBusy(false);event.target.value='';}
    };
    $('show-graph').onchange=toggleGraph;
    $('fit').onclick=()=>{if(map)map.setView([28.6888,77.2102],15);};
    $('next-trace').onclick=nextTrace;
    $('reset-trace').onclick=()=>{stopPlayback();traceIndex=0;renderTrace();};
    $('play-trace').onclick=()=>{if(timer){stopPlayback();return;}$('play-trace').textContent='Pause Ⅱ';timer=setInterval(nextTrace,300);};
    $('edge-search').oninput=()=>{edgePage=0;renderEdges();};
    $('prev-page').onclick=()=>{edgePage--;renderEdges();};$('next-page').onclick=()=>{edgePage++;renderEdges();};
    $('export').onclick=()=>{if(result)download('north-campus-route.json',JSON.stringify({...result,notes:'Fare and time are illustrative estimates. Access gaps excluded. Sample source is not real street routing.'},null,2),'application/json');};
    $('edges-export').onclick=()=>{if(graph){const csvCell=s=>'"'+String(s).replace(/"/g,'""')+'"';download('north-campus-edges.csv','from,to,weight_metres,street,osm_way_id\n'+graph.links.map(e=>[e.u,e.v,e.weight,e.name,e.way_id??''].map(csvCell).join(',')).join('\n'),'text/csv');}};
    ['trace','edges','math'].forEach(tab=>$(tab+'-tab').onclick=()=>{
      ['trace','edges','math'].forEach(other=>{const active=other===tab;$(other+'-tab').classList.toggle('active',active);$(other+'-tab').setAttribute('aria-selected',String(active));$(other+'-panel').hidden=!active;});
    });
    ['about-button','data-help'].forEach(id=>$(id).onclick=()=>$('about').showModal());
    document.querySelector('.close-dialog').onclick=()=>$('about').close();
    $('about').onclick=event=>{if(event.target===$('about')){const r=$('about').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$('about').close();}};
    if(config.osm_ready){await fetchGraph();status('Cached OSM network loaded. Ready to route.');}
    else status('Ready to explore. Find a route to download OSM streets, or choose Sample graph for an offline demonstration.');
  }catch(error){status(`Could not initialise Routebook: ${error.message}`,true);}
}
init();
