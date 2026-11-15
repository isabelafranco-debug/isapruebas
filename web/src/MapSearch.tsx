import { useEffect, useState, type FormEvent } from 'react';
import { Search } from 'lucide-react';

export type Place = {id:string; name:string; kind:string; regional:boolean; aliases?:string;
  center:[number,number]; bounds:[number,number,number,number]};

let index:Promise<Place[]>|undefined;
export function places() {
  index ??= fetch('/regional/places.json').then(res=>{
    if(!res.ok)throw new Error('El catálogo de ubicaciones no está disponible.');
    return res.json() as Promise<Place[]>;
  }).catch(error=>{index=undefined;throw error;});
  return index;
}

const normalize=(value:string)=>value.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase().trim();

export default function MapSearch({regional,onPlace,onCoordinates}:{regional:boolean;
  onPlace:(place:Place)=>void;onCoordinates:(position:[number,number])=>void}) {
  const [mode,setMode]=useState<'place'|'coords'>('place');
  const [query,setQuery]=useState(''),[data,setData]=useState<Place[]>([]),[error,setError]=useState('');
  const [latitude,setLatitude]=useState(''),[longitude,setLongitude]=useState('');
  useEffect(()=>{let live=true;void places().then(list=>{if(live)setData(list);}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};},[]);
  const term=normalize(query);
  const matches=term.length<2?[]:data.filter(p=>(!regional||p.regional)&&
    normalize(p.name+' '+p.kind+' '+(p.aliases??'')).includes(term)).sort((a,b)=>
    Number(normalize(b.name)===term)-Number(normalize(a.name)===term)).slice(0,8);
  function coordinates(e:FormEvent) {
    e.preventDefault();e.stopPropagation();
    const lat=Number(latitude.trim().replace(',','.')),lon=Number(longitude.trim().replace(',','.'));
    if(!latitude.trim()||!longitude.trim()||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>89.9||Math.abs(lon)>180){
      setError('Revisa la latitud y longitud en grados decimales.');return;
    }
    setError('');onCoordinates([lon,lat]);
  }
  return <div className="map-search" data-tour="map-search">
    <div className="segments" role="group" aria-label="Buscar ubicación">
      <button type="button" aria-pressed={mode==='place'} onClick={()=>{setMode('place');setError('');}}><Search size={16}/> Lugar</button>
      <button type="button" data-tour="coordinates" aria-pressed={mode==='coords'} onClick={()=>{setMode('coords');setError('');}}>Coordenadas</button>
    </div>
    {mode==='place'?<div className="place-search">
      <label>Provincia, municipio o departamento<input type="search" value={query} onChange={e=>setQuery(e.target.value)}
        onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();if(matches[0]){onPlace(matches[0]);setQuery('');}}}} placeholder="Ej. Warnes o Chiquitos" autoComplete="off"/></label>
      {term.length>=2&&<ul className="place-results" aria-label="Ubicaciones encontradas">{matches.length?matches.map(p=><li key={p.id}><button type="button" onClick={()=>{onPlace(p);setQuery('');}}>{p.name} <small>{p.kind}{p.regional?' · Santa Cruz':''}</small></button></li>):<li role="status">Sin resultados para esta búsqueda.</li>}</ul>}
    </div>:<div className="coordinates-search">
      <label>Latitud<input inputMode="decimal" placeholder="-17.182538" value={latitude} onChange={e=>setLatitude(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')coordinates(e);}}/></label>
      <label>Longitud<input inputMode="decimal" placeholder="-63.272578" value={longitude} onChange={e=>setLongitude(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')coordinates(e);}}/></label>
      <button type="button" className="button secondary" onClick={coordinates}>Ubicar</button>
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}
  </div>;
}
