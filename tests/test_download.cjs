// Network recovery is tested without an internet connection or browser install.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('static/app.js','utf8').replace(/init\(\);\s*$/,'');
function harness(fetch){
  const nodes=new Map();
  const document={getElementById(id){if(!nodes.has(id))nodes.set(id,{hidden:true,textContent:'',innerHTML:'',value:'',checked:true,closest(){return {scrollHeight:1,scrollTop:0};},classList:{toggle(){}}});return nodes.get(id);},querySelector(){return {value:'walk'};}};
  const context=vm.createContext({document,fetch,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval,clearInterval});
  vm.runInContext(script,context);
  vm.runInContext("networkConfig={query:'test query',endpoints:['https://first.example/api','https://second.example/api']}",context);
  return {context,nodes};
}
const ok=data=>({ok:true,json:async()=>data});
test('working Python download skips external browser requests',async()=>{
  const calls=[];
  const {context}=harness(async url=>{calls.push(url);return ok({vertices:2});});
  const result=await vm.runInContext('acquireNetwork()',context);
  assert.equal(result.vertices,2);assert.deepEqual(calls,['/api/load']);
});
test('Python failure and first browser failure recover via second endpoint and import',async()=>{
  const calls=[];
  const {context,nodes}=harness(async(url,options)=>{
    calls.push(url);
    if(url==='/api/load')return {ok:false,json:async()=>({error:'DNS blocked'})};
    if(url==='https://first.example/api')throw new TypeError('Failed to fetch');
    if(url==='https://second.example/api')return ok({elements:[{type:'node'}]});
    if(url==='/api/import'){
      assert.equal(JSON.parse(options.body).payload.elements[0].type,'node');
      return ok({vertices:2});
    }
    throw new Error('Unexpected URL');
  });
  const result=await vm.runInContext('acquireNetwork()',context);
  assert.equal(result.download_via,'browser');
  assert.equal(nodes.get('network-recovery').hidden,true);
  assert.deepEqual(calls,['/api/load','https://first.example/api','https://second.example/api','/api/import']);
});
test('total download failure exposes retry and offline recovery',async()=>{
  const {context,nodes}=harness(async()=>{throw new TypeError('Network unavailable');});
  await assert.rejects(vm.runInContext('acquireNetwork()',context),/OSM downloads failed/);
  assert.equal(nodes.get('network-recovery').hidden,false);
});
test('incomplete Overpass payload is not imported',async()=>{
  let imports=0;
  const {context}=harness(async url=>{
    if(url==='/api/import'){imports++;return ok({});}
    if(url==='/api/load')throw new Error('No Python connectivity');
    return ok({elements:[],remark:'runtime error: query timed out'});
  });
  await assert.rejects(vm.runInContext('acquireNetwork()',context),/incomplete response/);
  assert.equal(imports,0);
});
test('browser uses independent main OSM API with GET before Overpass',async()=>{
  const calls=[];
  const {context}=harness(async(url,options)=>{
    calls.push([url,options.method]);
    if(url==='/api/load')throw new Error('Python blocked');
    if(url==='https://api.openstreetmap.org/api/0.6/map.json?bbox=test')return ok({elements:[]});
    if(url==='/api/import')return ok({vertices:2});
    throw new Error('Unexpected Overpass request');
  });
  vm.runInContext("networkConfig.sources=[{url:'https://api.openstreetmap.org/api/0.6/map.json?bbox=test',name:'Main OSM API'}]",context);
  await vm.runInContext('acquireNetwork()',context);
  assert.deepEqual(calls,[['/api/load','POST'],['https://api.openstreetmap.org/api/0.6/map.json?bbox=test','GET'],['/api/import','POST']]);
});
test('cancel interrupts a download without starting browser retries',async()=>{
  let attempts=0;
  const {context,nodes}=harness(async(url,options)=>{
    attempts++;
    return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('cancelled'))));
  });
  const pending=vm.runInContext('acquireNetwork()',context);
  vm.runInContext('networkController.abort()',context);
  await assert.rejects(pending,/cancelled/);
  assert.equal(attempts,1);
  assert.equal(nodes.get('cancel-download').hidden,true);
});
function mapHarness(){
  const h=harness(async()=>ok({}));
  const lines=[];
  h.context.L={
    polyline(points){lines.push(points);return {addTo(){return this;}};},
    circleMarker(){return {bindTooltip(){return this;},addTo(){return this;}};},
    latLngBounds(points){return points;}
  };
  vm.runInContext(`
    map={invalidateSize(){},removeLayer(){},fitBounds(){}};
    graphLayer={clearLayers(){},addTo(){}};
    routeLayer={clearLayers(){}};traceLayer={clearLayers(){}};placeLayer={clearLayers(){}};
  `,h.context);
  return {...h,lines};
}
test('maths demo renders a diagram and never adds geographic map lines',()=>{
  const {context,nodes,lines}=mapHarness();
  context.input={source:'sample',coordinate_system:'diagram',vertices:2,edges:2,nodes:{A:[75,75],B:[245,75]},links:[{u:'A',v:'B',weight:400},{u:'B',v:'A',weight:400}]};
  vm.runInContext('renderGraph(input)',context);
  assert.equal(lines.length,0);
  assert.equal(nodes.get('map').hidden,true);
  assert.equal(nodes.get('schematic').hidden,false);
  assert.match(nodes.get('schematic-svg').innerHTML,/Abstract weighted graph/);
});
test('map draws mapped segments only and does not invent landmark connectors',()=>{
  const {context,lines}=mapHarness();
  const a=[28.69,77.21],corner=[28.69,77.215],b=[28.695,77.215];
  context.input={source:'osm',coordinate_system:'wgs84',vertices:3,edges:2,nodes:{1:a,2:corner,3:b},links:[
    {u:'1',v:'2',weight:500,name:'Road',geometry:[a,corner]},
    {u:'2',v:'3',weight:550,name:'Road',geometry:[corner,b]}],available_modes:['walk'],fetched_at:'2026-11-12'};
  vm.runInContext('renderGraph(input)',context);
  assert.deepEqual(lines,[[a,corner],[corner,b]]);
  lines.length=0;
  context.routeInput={source:'osm',coordinate_system:'wgs84',mode:'walk',distance_m:1050,duration_minutes:14,fare:0,settled_count:3,
    start:{id:'start',lat:28.689,lon:77.209},end:{id:'end',lat:28.696,lon:77.216,note:'test'},
    start_snap_m:150,end_snap_m:150,path:['1','2','3'],edges:context.input.links,
    geometry:[a,corner,b],segments:[[a,corner],[corner,b]],steps:[]};
  vm.runInContext('renderRoute(routeInput)',context);
  // Two strokes per segment (white casing, green route). No straight A→B line,
  // and no invented link from either off-road landmark pin to the network.
  assert.deepEqual(lines,[[a,corner],[a,corner],[corner,b],[corner,b]]);
});
test('transit result displays minute weights and settles virtual stop vertices',()=>{
  const {context,nodes}=mapHarness();
  const a=[28.69,77.21],b=[28.691,77.21];
  const links=[{u:'__origin__',v:'pre:stop:a',weight:0,name:'Walk',geometry:[a,a],transport:'walk',distance_m:0},
    {u:'pre:stop:a',v:'ride:stop:b',weight:4.5,name:'Bus test',geometry:[a,b],transport:'bus',distance_m:111},
    {u:'ride:stop:b',v:'__target__',weight:0,name:'Walk',geometry:[b,b],transport:'walk',distance_m:0}];
  context.routeInput={source:'cached',coordinate_system:'wgs84',mode:'bus',optimality:'estimated_time',cost_unit:'min',
    graph_vertices:4,graph_edges:3,distance_m:111,duration_minutes:4.5,fare:5,settled_count:4,
    access_distance_m:0,ride_distance_m:111,stop_access_gap_m:0,walking_alternative_minutes:10,
    start:{id:'start',lat:a[0],lon:a[1]},end:{id:'end',lat:b[0],lon:b[1],note:'test'},
    start_snap_m:0,end_snap_m:0,path:['__origin__','pre:stop:a','ride:stop:b','__target__'],edges:links,
    geometry:[a,b],segments:[[a,a],[a,b],[b,b]],
    trace_nodes:{'__origin__':a,'pre:stop:a':a,'ride:stop:b':b,'__target__':b},
    steps:[{node:'__origin__',distance:0,relaxations:[{to:'pre:stop:a',old:null,new:0}]}],
    route_graph:{source:'cached',coordinate_system:'wgs84',vertices:4,edges:3,weight_unit:'min',
      available_modes:['walk','bus'],fetched_at:'2026-11-12',nodes:{'__origin__':a,'pre:stop:a':a,'ride:stop:b':b,'__target__':b},links}};
  vm.runInContext('renderRoute(routeInput); nextTrace()',context);
  assert.equal(nodes.get('edge-weight-header').textContent,'WEIGHT (min)');
  assert.equal(nodes.get('trace-cost-header').textContent,'ESTIMATED MINUTES');
  assert.match(nodes.get('trace-body').innerHTML,/0\.0 min/);
  assert.match(nodes.get('route-criterion').textContent,/FASTEST BUS/);
});
