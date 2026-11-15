import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl/dist/maplibre-gl-csp.js';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-csp-worker.js?url';
import type {StyleSpecification, Map as LibreMap, Marker as LibreMarker} from 'maplibre-gl';
import { TerraDraw, TerraDrawPointMode, TerraDrawPolygonMode, TerraDrawSelectMode } from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';
import { LocateFixed, MapPin, Pentagon, Pencil, Trash2, Layers, Check } from 'lucide-react';
import type { Shape } from './types';
import type { FeatureCollection } from 'geojson';
import MapSearch, {type Place} from './MapSearch';
import {downloadMap, OFFLINE_MAP} from './offline';
import { nasaLayers, nasaTile, NasaControls, type NasaLayer } from './NasaLayers';
import 'maplibre-gl/dist/maplibre-gl.css';

maplibregl.setWorkerUrl(workerUrl);

const PILOT:[number,number] = [-63.272578418,-17.182537861];
const local:StyleSpecification={version:8,sources:{},layers:[{id:'solid',type:'background',paint:{'background-color':'#e4ecdf'}}]};
const remote = import.meta.env.VITE_MAP_STYLE || 'https://tiles.openfreemap.org/styles/liberty';
const regionalBounds:[number,number,number,number]=[-65.0,-20.7,-57.2,-13.2];
const regional:StyleSpecification={version:8,sources:{regional:{type:'geojson',data:'/regional/santa-cruz.geojson',
  attribution:'GeoBolivia / <a href="https://www.geoboundaries.org/">geoBoundaries</a> · límites simplificados'}},layers:[
  ...local.layers,
  {id:'province-fill',type:'fill',source:'regional',filter:['==',['get','kind'],'province'],paint:{'fill-color':'#b9d5a6','fill-opacity':.55}},
  {id:'province-border',type:'line',source:'regional',filter:['==',['get','kind'],'province'],paint:{'line-color':'#53846a','line-width':1.3}},
  {id:'province-name',type:'symbol',source:'regional',filter:['==',['get','kind'],'label'],layout:{'text-field':['get','name'],'text-size':13,'text-font':['Arial']},paint:{'text-color':'#1c4b39','text-halo-color':'#ecf3e6','text-halo-width':1.5}},
  {id:'municipality-name',type:'symbol',source:'regional',minzoom:8,filter:['==',['get','kind'],'municipality'],layout:{'text-field':['get','name'],'text-size':12,'text-font':['Arial'],'text-offset':[0,1]},paint:{'text-color':'#244534','text-halo-color':'#edf5e8','text-halo-width':1.3}},
  {id:'municipality-point',type:'circle',source:'regional',minzoom:8,filter:['==',['get','kind'],'municipality'],paint:{'circle-radius':3,'circle-color':'#477858'}}
]};
const roundPosition = (p:number[]) => p.map(v=>Number(v.toFixed(8)));
function roundGeometry(geometry:Exclude<Shape,{type:'MultiPolygon'}>):Exclude<Shape,{type:'MultiPolygon'}> {
  if(geometry.type==='Point')return {...geometry,coordinates:roundPosition(geometry.coordinates)};
  return {...geometry,coordinates:geometry.coordinates.map(ring=>ring.map(roundPosition))};
}
type Mode = 'point'|'polygon'|'select';

export default function PlotMap({initial,onShape,offline=false,exposure}:{initial:Shape|null; onShape:(shape:Shape|null,source:string)=>void;offline?:boolean;exposure?:FeatureCollection}) {
  const mount = useRef<HTMLDivElement>(null);
  const map = useRef<LibreMap|null>(null);
  const draw = useRef<TerraDraw|null>(null);
  const gpsMarker = useRef<LibreMarker|null>(null);
  const shape = useRef(initial);
  const callback = useRef(onShape);
  callback.current=onShape;
  const [base,setBase]=useState(true);
  const [useRegional,setRegional]=useState(offline||!!exposure);
  const [ready,setReady]=useState(false);
  const [mode,setMode]=useState<Mode>('select');
  const [message,setMessage]=useState('');
  const [locating,setLocating]=useState(false);
  const [download,setDownload]=useState<'idle'|'busy'|'ready'>('idle');
  const [nasa,setNasa]=useState<NasaLayer|''>(''),[nasaDate,setNasaDate]=useState(''),[nasaError,setNasaError]=useState(false);
  const [target,setTarget]=useState<{center:[number,number];label:string;accuracy?:number}|null>(null);
  const view=useRef<{center:[number,number];zoom:number}|null>(null);
  useEffect(()=>{
    const first = shape.current;
    const coords = first?.type==='Point' ? first.coordinates :
      first?.type==='Polygon' ? first.coordinates[0][0] : first?.coordinates[0][0][0];
    const existing=view.current;
    const instance = new maplibregl.Map({container:mount.current!,style:useRegional?regional:base?remote:local,
      center:existing?.center??(coords?[coords[0],coords[1]]:PILOT),zoom:existing?.zoom??(offline?6:14),attributionControl:{compact:true},
      ...(offline?{maxBounds:regionalBounds,minZoom:5,maxZoom:16}:{}),
      canvasContextAttributes:{antialias:true}});
    map.current=instance;
    instance.addControl(new maplibregl.NavigationControl({showCompass:true}),'top-right');
    instance.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-left');
    let changed=false;
    const useLocal = () => {
      if (!changed && base && !useRegional && !draw.current) {
        changed=true;
        setMessage('El mapa de fondo no respondió. Puedes dibujar sobre el fondo local.');
        setReady(false);
        setBase(false);
      }
    };
    const timeout=window.setTimeout(useLocal,7000);
    instance.on('error',event=>{if(!instance.isStyleLoaded()&&!("sourceId" in event))useLocal();});
    instance.once('load',()=>{
      clearTimeout(timeout);
      if (offline&&!existing)instance.fitBounds(regionalBounds,{padding:28,duration:0});
      if (!existing&&first && first.type!=='Point') {
        const bounds = new maplibregl.LngLatBounds();
        const polys = first.type==='Polygon'?[first.coordinates]:first.coordinates;
        polys.forEach(poly=>poly[0].forEach(p=>bounds.extend([p[0],p[1]])));
        instance.fitBounds(bounds,{padding:65,maxZoom:17,duration:0});
      }
      if(exposure){setReady(true);return;}
      const tools = new TerraDraw({
        adapter:new TerraDrawMapLibreGLAdapter({map:instance,coordinatePrecision:8}),
        modes:[
          new TerraDrawPointMode({styles:{pointColor:'#258261',pointWidth:11}}),
          new TerraDrawPolygonMode({styles:{fillColor:'#72ab56',fillOpacity:.34,outlineColor:'#1b674d',outlineWidth:3}}),
          new TerraDrawSelectMode({flags:{point:{feature:{draggable:true}},polygon:{feature:{draggable:true,coordinates:{draggable:true,midpoints:true,deletable:true}}}}}),
        ]});
      draw.current=tools;
      tools.start();
      tools.setMode('select');
      const install = (geo:Shape) => {
        const shapes = geo.type==='MultiPolygon' ? geo.coordinates.map(coordinates=>({type:'Polygon' as const,coordinates})) : [geo];
        tools.addFeatures(shapes.map(geometry=>({type:'Feature',geometry:roundGeometry(geometry),properties:{mode:geometry.type==='Point'?'point':'polygon'}})));
      };
      if(shape.current)install(shape.current);
      const saveSnapshot = () => {
        const complete = tools.getSnapshot().filter(f=>!f.properties.midPoint && ['Point','Polygon'].includes(f.geometry.type) && ['point','polygon'].includes(String(f.properties.mode)));
        const geos = complete.map(f=>f.geometry as Shape);
        if(!geos.length)return;
        const polys=geos.filter(g=>g.type==='Polygon');
        const geo:Shape = polys.length>1 ? {type:'MultiPolygon',coordinates:polys.map(p=>p.coordinates)} : geos.at(-1)!;
        shape.current=geo;
        callback.current(geo,'dibujo manual');
      };
      tools.on('finish',()=>{saveSnapshot();tools.setMode('select');setMode('select');});
      tools.on('change',(_ids,type)=>{if(type==='update'&&tools.getMode()==='select')saveSnapshot();});
      setReady(true);
    });
    return ()=>{
      clearTimeout(timeout);
      const center=instance.getCenter();view.current={center:[center.lng,center.lat],zoom:instance.getZoom()};
      draw.current?.stop();draw.current=null;
      gpsMarker.current?.remove();gpsMarker.current=null;
      instance.remove();map.current=null;
    };
  },[base,useRegional,offline]);

  useEffect(()=>{
    const instance=map.current;
    if(!ready||!instance||!exposure)return;
    const color:maplibregl.ExpressionSpecification=['case',['==',['get','value'],null],'#87998d',
      ['interpolate',['linear'],['get','value'],0,'#58a583',50,'#efc366',100,'#b75941']];
    const source=instance.getSource('field-exposure') as maplibregl.GeoJSONSource|undefined;
    if(source)source.setData(exposure);
    else{
      instance.addSource('field-exposure',{type:'geojson',data:exposure});
      instance.addLayer({id:'exposure-fill',type:'fill',source:'field-exposure',filter:['!=',['geometry-type'],'Point'],paint:{'fill-color':color,'fill-opacity':.7}});
      instance.addLayer({id:'exposure-point',type:'circle',source:'field-exposure',filter:['==',['geometry-type'],'Point'],paint:{'circle-color':color,'circle-radius':11,'circle-stroke-color':'white','circle-stroke-width':2}});
      instance.on('click','exposure-point',event=>{
        const feature=event.features?.[0];if(!feature||feature.geometry.type!=='Point')return;
        new maplibregl.Popup().setLngLat([feature.geometry.coordinates[0],feature.geometry.coordinates[1]])
          .setText(String(feature.properties?.description??'')).addTo(instance);
      });
    }
    if(!view.current&&exposure.features.length){
      const bounds=new maplibregl.LngLatBounds();
      exposure.features.filter(f=>f.geometry.type==='Point').forEach(f=>{if(f.geometry.type==='Point')bounds.extend([f.geometry.coordinates[0],f.geometry.coordinates[1]]);});
      if(!bounds.isEmpty())instance.fitBounds(bounds,{padding:65,maxZoom:12,duration:0});
    }
  },[ready,exposure]);

  useEffect(()=>{
    const instance=map.current;
    if(!ready||!instance||!nasa||offline)return;
    const source='nasa-context';
    const reportError=(event:{sourceId?:string})=>{if(event.sourceId===source)setNasaError(true);};
    setNasaError(false);
    instance.on('error',reportError);
    instance.addSource(source,{type:'raster',tiles:[nasaTile(nasa,nasaDate)],tileSize:256,maxzoom:nasaLayers[nasa].maxZoom,
      attribution:'<a href="https://www.earthdata.nasa.gov/data/tools/gibs">NASA Earthdata · GIBS</a>'});
    const insert=instance.getStyle().layers.find(x=>x.type==='symbol'||x.id.startsWith('td-'))?.id;
    instance.addLayer({id:source,type:'raster',source,paint:{'raster-opacity':.57}},insert);
    return ()=>{
      if(map.current!==instance)return;
      instance.off('error',reportError);
      if(instance.getLayer(source))instance.removeLayer(source);
      if(instance.getSource(source))instance.removeSource(source);
    };
  },[ready,nasa,nasaDate,offline]);

  function preview(center:[number,number], label:string, bounds?:Place['bounds'], accuracy?:number) {
    if(offline&&(center[0]<regionalBounds[0]||center[0]>regionalBounds[2]||center[1]<regionalBounds[1]||center[1]>regionalBounds[3])){
      setMessage('Estas coordenadas están fuera del área del mapa descargado.');return;
    }
    if(!map.current)return;
    gpsMarker.current?.remove();
    gpsMarker.current=new maplibregl.Marker({color:'#4c87bc'}).setLngLat(center).addTo(map.current);
    if(bounds)map.current.fitBounds(bounds,{padding:48,maxZoom:13});
    else map.current.flyTo({center,zoom:16});
    setTarget({center,label,accuracy});
    setMessage(label+'. Confirma el punto o dibuja tu terreno.');
  }

  async function saveRegional() {
    setDownload('busy');setMessage('');
    try{await downloadMap();setDownload('ready');setMessage('Mapa de Santa Cruz guardado en este dispositivo.');}
    catch(e){setDownload('idle');setMessage(e instanceof Error?e.message:'No se pudo descargar el mapa.');}
  }

  function choose(next:Mode) {
    if(!draw.current)return;
    if(next!=='select') {
      gpsMarker.current?.remove();setTarget(null);
      draw.current.clear();
      shape.current=null;
      callback.current(null,'dibujo manual');
    }
    draw.current.setMode(next);
    setMode(next);
    setMessage(next==='polygon'?'Marca los vértices y vuelve al primero para cerrar.':next==='point'?'Toca el mapa para ubicar el punto.':'Selecciona la figura para mover el punto o editar sus vértices.');
  }

  function locate() {
    if (!window.isSecureContext || !navigator.geolocation) {
      setMessage('El GPS necesita localhost o HTTPS. Puedes marcar el punto manualmente.');
      return;
    }
    setLocating(true);setMessage('');
    navigator.geolocation.getCurrentPosition(({coords})=>{
      const result={lat:coords.latitude,lng:coords.longitude,accuracy:coords.accuracy};
      setLocating(false);
      preview([result.lng,result.lat],'Ubicación GPS',undefined,result.accuracy);
    },err=>{
      setLocating(false);
      setMessage(err.code===1?'Permiso denegado. Habilita la ubicación en el navegador o marca el punto en el mapa.':
        err.code===3?'La búsqueda agotó el tiempo. Reintenta o marca el punto en el mapa.':'El dispositivo no pudo obtener la ubicación. Puedes marcar el punto en el mapa.');
    },{enableHighAccuracy:true,maximumAge:15000,timeout:10000});
  }

  function confirm() {
    if(!target||!draw.current)return;
    const point:Shape={type:'Point',coordinates:roundPosition(target.center)};
    draw.current.clear();
    draw.current.addFeatures([{type:'Feature',geometry:point,properties:{mode:'point'}}]);
    draw.current.setMode('select');setMode('select');
    shape.current=point;callback.current(point,target.accuracy!==undefined?'GPS confirmado':'coordenadas confirmadas');
    gpsMarker.current?.remove();setTarget(null);setMessage(offline?'Punto confirmado para consulta en este mapa.':'Punto confirmado. Guarda el lote para conservarlo.');
  }

  return <div className="map-card">
    {!exposure&&<MapSearch regional={offline||useRegional} onPlace={p=>preview(p.center,p.name,p.bounds)}
      onCoordinates={p=>preview(p,'Coordenadas ingresadas')}/>}
    {!offline&&!exposure&&<NasaControls layer={nasa} date={nasaDate} error={nasaError} onDate={setNasaDate}
      onLayer={value=>{setNasa(value);setNasaDate(value?nasaLayers[value].date:'');setNasaError(false);}}/>}
    <div className="map-stage">
      <div className="map-canvas" ref={mount}/>
      {!exposure&&<div className="map-tools" data-tour="map-tools">
        <button type="button" className="button map-btn" onClick={locate} disabled={locating}><LocateFixed size={17}/>{locating?'Buscando…':'Ir a mi ubicación'}</button>
        <button type="button" className={'button map-btn '+(mode==='polygon'?'pressed':'')} disabled={!ready} onClick={()=>choose('polygon')}><Pentagon size={16}/> Dibujar terreno</button>
        <button type="button" className={'button icon-btn '+(mode==='point'?'pressed':'')} aria-label="Marcar punto" title="Marcar punto" disabled={!ready} onClick={()=>choose('point')}><MapPin size={17}/></button>
        <button type="button" className="button icon-btn" aria-label="Editar figura" title="Editar figura" disabled={!ready} onClick={()=>choose('select')}><Pencil size={16}/></button>
        <button type="button" className="button icon-btn" aria-label="Borrar figura" title="Borrar figura" disabled={!ready} onClick={()=>{draw.current?.clear();shape.current=null;callback.current(null,'dibujo manual');}}><Trash2 size={16}/></button>
        {!useRegional&&<button type="button" className="button icon-btn" aria-label={base?'Usar fondo local':'Mostrar OpenFreeMap'} title={base?'Usar fondo local':'Mostrar OpenFreeMap'} onClick={()=>{setReady(false);setMode('select');setBase(!base);}}><Layers size={17}/></button>}
      </div>}
      {!base&&!useRegional&&<span className="map-attribution">Fondo local · Geometría del productor</span>}
    </div>
    {(message||target)&&<div className="map-message" aria-live="polite"><span>{message}{target?.accuracy!==undefined&&<> Precisión estimada ±{Math.round(target.accuracy)} m.</>}</span>
      {target&&<button className="button secondary" type="button" onClick={confirm} disabled={!ready}><Check size={16}/> Confirmar punto</button>}</div>}
    {!offline&&!exposure&&<div className="offline-tools" data-tour="offline">
      <button type="button" className="button secondary" aria-pressed={useRegional} onClick={()=>{setReady(false);setTarget(null);setRegional(!useRegional);}}>{useRegional?'Volver al mapa general':'Capa regional de Santa Cruz'}</button>
      <button type="button" className="button secondary" disabled={download==='busy'} onClick={()=>void saveRegional()}>{download==='busy'?'Descargando…':download==='ready'?'Volver a descargar':'Descargar mapa sin conexión'}</button>
      <a href={OFFLINE_MAP} target="_blank" rel="noreferrer">Abrir mapa sin conexión</a>
    </div>}
  </div>;
}
