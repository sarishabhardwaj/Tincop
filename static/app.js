'use strict';
const $ = id => document.getElementById(id);
let places = [], graph = null, result = null, map = null, graphLayer, placeLayer, routeLayer, traceLayer;
let traceIndex = 0, timer = null, edgePage = 0, busy = false;
let networkConfig = {query:'', endpoints:[]};
let networkController = null;
const mode = () => document.querySelector('input[name="mode"]:checked').value;
const source = () => $('source').value;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const metres = n => n >= 1000 ? `${(n/1000).toFixed(2)} km` : `${Math.round(n)} m`;
const money = n => new Intl.NumberFormat('en-IN',{maximumFractionDigits:2}).format(n);

function status(message, error=false) {
  $('status').textContent = message;
  $('status').classList.toggle('error',error);
}
async function api(path, body, signal) {
  const response = await fetch(`/api/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request failed.');
  return data;
}
function setBusy(value) {
  busy = value;
  ['find-route','load','source','start','end','swap','import'].forEach(id => $(id).disabled = value);
  $('load').disabled=value || source()!=='osm';
  $('bus-type').disabled=value;
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
  drawPlaces();renderSchematic();
}
function initialiseMap() {
  if (typeof L === 'undefined') {
    $('map-fallback').hidden=false;
    return;
  }
  map=L.map('map',{zoomControl:false,preferCanvas:true}).setView([28.6888,77.2102],15);
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
  if(graph?.coordinate_system==='diagram')return;
  places.forEach((p,i)=>{
    const isStart=result && p.id===result.start.id, isEnd=result && p.id===result.end.id;
    const label=graph?.source==='sample'?String.fromCharCode(65+i):isStart?'A':isEnd?'B':String(i+1).padStart(2,'0');
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
function updateMapView(){
  const schematic=graph?.coordinate_system==='diagram';
  $('schematic').hidden=!schematic;
  $('map').hidden=schematic;
  $('map-topbar').hidden=schematic;
  $('map-bottom').hidden=schematic;
  $('sample-watermark').hidden=true;
  $('map-fallback').hidden=schematic || !!map;
  if(!schematic && map)map.invalidateSize();
}
function renderSchematic(){
  if(graph?.coordinate_system!=='diagram')return;
  const routeEdges=new Set((result?.edges||[]).map(e=>[e.u,e.v].sort().join(':')));
  const visited=new Set((result?.steps||[]).slice(0,traceIndex).map(s=>s.node));
  const seen=new Set();
  let lines='';
  graph.links.forEach(edge=>{
    const key=[edge.u,edge.v].sort().join(':');if(seen.has(key))return;seen.add(key);
    const [x1,y1]=graph.nodes[edge.u],[x2,y2]=graph.nodes[edge.v];
    const selected=routeEdges.has(key);
    lines+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${selected?'#234c3a':'#b9c3aa'}" stroke-width="${selected?5:1.5}"/><text x="${(x1+x2)/2}" y="${(y1+y2)/2-7}" class="schematic-weight">${Math.round(edge.weight)}</text>`;
  });
  const vertices=Object.entries(graph.nodes).map(([key,[x,y]])=>`<g><title>Vertex ${esc(key)}</title><circle cx="${x}" cy="${y}" r="19" fill="${visited.has(key)?'#d99a57':'#fffefa'}" stroke="#234c3a" stroke-width="2"/><text x="${x}" y="${y+5}" text-anchor="middle" fill="#234c3a" font-size="14">${esc(key)}</text></g>`).join('');
  $('schematic-svg').innerHTML=`<svg viewBox="0 0 660 450" role="img" aria-label="Abstract weighted graph for Dijkstra, not a road map">${lines}${vertices}</svg>`;
}
function renderGraph(data) {
  graph=data; edgePage=0;
  $('vertex-count').textContent=data.vertices.toLocaleString('en-IN');
  $('edge-count').textContent=data.edges.toLocaleString('en-IN');
  $('network-label').textContent=data.source==='sample'?'Sample teaching graph':'OpenStreetMap network';
  $('network-meta').textContent=data.source==='sample'?'Abstract maths diagram. No geographic routes.':`Cached ${new Date(data.fetched_at).toLocaleDateString()} · ${mode()} · available: ${data.available_modes.join(', ')}`;
  updateMapView();renderSchematic();
  $('load').disabled=data.source!=='osm';
  if(map){
    graphLayer.clearLayers();
    if(data.coordinate_system==='diagram'){drawPlaces();renderEdges();return;}
    const seen=new Set();
    data.links.forEach(edge=>{
      const key=[edge.u,edge.v].sort().join(':');
      if(seen.has(key)) return; seen.add(key);
      // Never substitute a chord for missing geographic road geometry.
      if(!edge.geometry || edge.geometry.length<2)return;
      L.polyline(edge.geometry,{color:'#80946d',weight:1.5,opacity:.5}).addTo(graphLayer);
    });
    Object.entries(data.nodes).forEach(([key,coord])=>L.circleMarker(coord,{radius:data.source==='sample'?5:2,weight:0,fillColor:'#647f54',fillOpacity:.65}).bindTooltip(`Vertex ${esc(key)}`).addTo(graphLayer));
    toggleGraph();
  }
  drawPlaces();renderEdges();
}
function toggleGraph(){if(map){if($('show-graph').checked) graphLayer.addTo(map);else map.removeLayer(graphLayer);}}
async function fetchGraph(){
  clearResult();
  const data=await api('graph',{source:source(),mode:mode()});renderGraph(data);
}
async function acquireNetwork(refresh=false, transit=false){
  $('network-recovery').hidden=true;
  const outer=new AbortController();networkController=outer;$('cancel-download').hidden=false;
  const errors=[];
  try{
  try{const data=await api(transit?'load-transit':'load',{mode:mode(),refresh},outer.signal);networkConfig.osm_ready=true;return data;}
  catch(error){if(outer.signal.aborted)throw new Error('Download cancelled. Any cached streets are kept.');errors.push(error.message);}
  // Browser connectivity is independent of Python's sandbox, DNS and proxy.
  const providers=(transit?networkConfig.transit_sources:networkConfig.sources) || networkConfig.endpoints.map(url=>({url,query:networkConfig.query}));
  for(const [index,provider] of providers.entries()){
    const endpoint=provider.url;
    status(`Trying ${provider.name||'map source'} in your browser (${index+1}/${providers.length})…`);
    const controller=new AbortController();
    const cancel=()=>controller.abort();outer.signal.addEventListener('abort',cancel,{once:true});
    const timeout=setTimeout(()=>controller.abort(),25000);
    try{
      if(outer.signal.aborted)throw new Error('Download cancelled.');
      const response=await fetch(endpoint,{method:provider.query?'POST':'GET',body:provider.query?new URLSearchParams({data:provider.query}):undefined,signal:controller.signal});
      if(!response.ok)throw new Error(`Map source HTTP ${response.status}`);
      const payload=await response.json();
      if(payload.remark)throw new Error(`Overpass returned an incomplete response: ${payload.remark}`);
      if(!Array.isArray(payload.elements))throw new Error('Overpass did not return map data.');
      const data=await api('import',{payload,mode:mode(),merge:transit},outer.signal);
      networkConfig.osm_ready=true;
      data.download_via='browser';
      return data;
    }catch(error){if(outer.signal.aborted)throw new Error('Download cancelled. Any cached streets are kept.');errors.push(`${new URL(endpoint).hostname}: ${error.name==='AbortError'?'request timed out':error.message}`);}
    finally{clearTimeout(timeout);outer.signal.removeEventListener('abort',cancel);}
  }
  $('network-recovery').hidden=false;
  throw new Error('OSM downloads failed. Open Download OSM file in Data help and import the saved .osm or JSON file. The maths demo is a separate diagram, not road routing. Details: '+errors.join(' | '));
  }finally{networkController=null;$('cancel-download').hidden=true;}
}
async function prepareNetwork(refresh=false){
  let data=await acquireNetwork(refresh);
  // An unavailable transit query must not prevent walking streets from loading.
  renderGraph(data);
  if(mode()!=='walk' && !data.edges){
    status(`Walking streets are saved. Loading ${mode()} services separately…`);
    data=await acquireNetwork(false,true);
  }
  return data;
}
async function loadStreets(refresh=false){
  if(busy)return;
  clearResult();setBusy(true);status('Loading real OSM streets…');
  try{
    const data=await prepareNetwork(refresh);
    $('source').value='osm';renderGraph(data);
    status(data.edges?'Network ready. Choose your destinations and find a route.':`Data downloaded, but no connected ${mode()} services were found. Choose Walking or import a transit extract.`);
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
  $('snap-note').textContent=data.source==='sample'?'Abstract maths example only. No geographic route or real services.':`${data.mode==='walk'?'Street-to-street':'Stop-to-stop'} route. Landmark access gaps: ${Math.round(data.start_snap_m)} m at start + ${Math.round(data.end_snap_m)} m at arrival. These are not routed or drawn; excluded from totals.`;
  const groups=groupedEdges(data.edges);
  $('directions').innerHTML=groups.length?groups.map(g=>`<li>${esc(g.name)} <small>${metres(g.distance)}</small></li>`).join(''):`<li>Both selections connect to the same ${data.mode==='walk'?'vertex':'stop'}. No ride is included. Choose Walking for the local journey.</li>`;
  $('destination-note').textContent=data.end.note;
  renderSchematic();
  if(map && data.coordinate_system!=='diagram'){
    routeLayer.clearLayers();traceLayer.clearLayers();
    if(data.geometry.length>1){
      for(const segment of data.segments){
        L.polyline(segment,{color:'#102e59',weight:11,opacity:1}).addTo(routeLayer);
        L.polyline(segment,{color:'#2f85ff',weight:6,opacity:1}).addTo(routeLayer);
      }
    }
    if(data.coordinate_system==='wgs84'){
      [data.path[0],data.path.at(-1)].forEach((key,i)=>L.circleMarker(graph.nodes[key],{radius:7,color:'#fffefa',weight:2,fillColor:i?'#ad633e':'#234c3a',fillOpacity:1}).bindTooltip(i?'Route ends on the mapped network':'Route starts on the mapped network').addTo(routeLayer));
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
  renderSchematic();
  if(map && result.coordinate_system!=='diagram'){
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
    const config=await response.json();places=config.destinations;networkConfig=config;
    for(const id of ['start','end']){
      $(id).innerHTML=places.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    }
    $('end').value='kamla';
    $('osm-query').textContent=config.query;
    $('overpass-link').href=`https://overpass-turbo.eu/?Q=${encodeURIComponent(config.query)}`;
    $('osm-download-link').href=config.export_url;
    $('transit-query').textContent=config.transit_query;
    initialiseMap();
    $('route-form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;setBusy(true);clearResult();status('Running Dijkstra’s algorithm…');
      try{
        if(!graph && source()==='osm'){
          status('Loading real OSM streets before routing…');
          const network=await prepareNetwork();renderGraph(network);config.osm_ready=true;
        }else if(source()==='osm' && mode()!=='walk' && !graph.edges){
          status(`Loading ${mode()} service data separately. Walking streets remain cached…`);
          renderGraph(await acquireNetwork(false,true));
        }
        const data=await api('route',{source:source(),mode:mode(),start:$('start').value,end:$('end').value,
          fare:{bus_type:$('bus-type').value}});
        renderRoute(data);status(data.source==='sample'?'Sample route found. Classroom graph; not actual transit services.':'Shortest route in the loaded graph found. Explore the algorithm’s trace below.');
      }catch(error){status(error.message,true);}
      finally{setBusy(false);}
    };
    $('swap').onclick=()=>{const start=$('start').value;$('start').value=$('end').value;$('end').value=start;clearResult();};
    ['start','end'].forEach(id=>$(id).onchange=()=>clearResult());
    document.querySelectorAll('input[name="mode"]').forEach(input=>input.onchange=async()=>{
      clearResult();setBusy(true);
      const walk=mode()==='walk';$('fare-details').hidden=walk;
      $('bus-options').hidden=mode()!=='bus';
      try{await fetchGraph();status(graph.edges?'Transport mode changed. Find a route to update your result.':`No connected ${mode()} services in this extract. Refresh OSM data, import transit JSON, or choose Walking.`,!graph.edges);}catch(error){status(error.message,true);}
      finally{setBusy(false);}
    });
    $('fare-details').hidden=mode()==='walk';$('bus-options').hidden=mode()!=='bus';
    $('bus-type').onchange=()=>clearResult();
    $('load').onclick=()=>loadStreets(!!graph && source()==='osm');
    $('retry-osm').onclick=()=>loadStreets(true);
    $('cancel-download').onclick=()=>networkController?.abort();
    $('offline-demo').onclick=()=>{if(!busy){$('source').value='sample';$('network-recovery').hidden=true;$('source').dispatchEvent(new Event('change'));}};
    $('source').onchange=async()=>{
      clearResult();graph=null;if(map)graphLayer.clearLayers();
      updateMapView();
      $('vertex-count').textContent='—';$('edge-count').textContent='—';
      $('edge-body').innerHTML='';$('network-label').textContent=source()==='sample'?'Sample teaching graph':'OpenStreetMap streets';
      $('network-meta').textContent='';
      if(source()==='osm'&&!config.osm_ready){await loadStreets();return;}
      setBusy(true);
      try{await fetchGraph();status(source()==='sample'?'Maths diagram ready: invented classroom weights. For actual road routes, select OSM network.':'OSM street network ready.');}
      catch(error){status(error.message,true);}
      finally{setBusy(false);}
    };
    $('import').onchange=async event=>{
      const file=event.target.files[0];if(!file)return;
      setBusy(true);clearResult();status('Reading your OSM street data…');
      try{
        if(file.size>19_000_000)throw new Error('Use an OSM extract smaller than 19 MB.');
        const text=(await file.text()).replace(/^\uFEFF/,'');
        const content=text.trimStart().startsWith('<')?{raw:text}:{payload:JSON.parse(text)};
        const data=await api('import',{...content,mode:mode()});
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
    else status('Load OSM streets for road routing. The offline maths diagram has no geographic routes.');
  }catch(error){status(`Could not initialise Routebook: ${error.message}`,true);}
}
init();
