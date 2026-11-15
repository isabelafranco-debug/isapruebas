const root='https://gibs.earthdata.nasa.gov';

export const nasaLayers={
  ndvi:{name:'Vegetación · NDVI MODIS Terra',id:'MODIS_Terra_L3_NDVI_Monthly',maxZoom:7,date:'2025-11-01',
    legend:'MODIS_L3_NDVI',time:'month',
    detail:'Compuesto mensual de 1 km. Menor verdor también puede reflejar cosecha, suelo descubierto, nubes o cambio de uso.'},
  smap:{name:'Humedad radicular · SMAP L4',id:'SMAP_L4_Analyzed_Root_Zone_Soil_Moisture',maxZoom:6,date:'2024-11-15',
    legend:'SMAP_Analyzed_Soil_Moisture',time:'day',
    detail:'Estimación de humedad radicular de 9 km a las 12 UTC. Combina observaciones y un modelo.'},
  rain:{name:'Precipitación · GPM IMERG',id:'IMERG_Precipitation_Rate',maxZoom:6,date:'2025-11-15',
    legend:'GPM_Precipitation_Rate',time:'day',
    detail:'Tasa media de precipitación del día, en mm/h, a escala regional.'},
  temperature:{name:'Temperatura de superficie · MODIS Terra',id:'MODIS_Terra_Land_Surface_Temp_Day',maxZoom:7,date:'2025-11-15',
    legend:'MODIS_Land_Surface_Temp',time:'day',
    detail:'Temperatura diurna de la superficie a 1 km. Revisa nubes y cobertura. La temperatura del aire se consulta en el análisis climático.'},
  biomass:{name:'Biomasa aérea · GEDI L4B',id:'GEDI_ISS_L4B_Aboveground_Biomass_Density_Mean_201904-202303',maxZoom:7,date:'2019-04-18',
    legend:'GEDI_MU_Color_Index',time:'static',
    detail:'Densidad de biomasa aérea leñosa, producto agregado 2019–2023 a 1 km. Describe el contexto de vegetación leñosa del entorno.'},
  elevation:{name:'Relieve · SRTM',id:'SRTM_Color_Index',maxZoom:12,date:'default',
    legend:'SRTM_Color_Index',time:'static',
    detail:'Modelo de elevación, observación de febrero de 2000 y soporte de hasta 30 m. El relieve orienta la revisión de drenaje y microclimas.'},
};

export type NasaLayer=keyof typeof nasaLayers;
export function nasaTile(layer:NasaLayer,date:string){
  const item=nasaLayers[layer];
  const time=item.time==='static'?item.date:layer==='ndvi'?date.slice(0,7)+'-01':date;
  return `${root}/wmts/epsg3857/best/${item.id}/default/${time}/GoogleMapsCompatible_Level${item.maxZoom}/{z}/{y}/{x}.png`;
}

export function NasaControls({layer,date,onLayer,onDate,error}:{layer:NasaLayer|'';date:string;
  onLayer:(layer:NasaLayer|'')=>void;onDate:(date:string)=>void;error:boolean}){
  const selected=layer?nasaLayers[layer]:null;
  return <details className="nasa-controls" data-tour="nasa"><summary>Capas NASA por fecha</summary>
    <div className="two-col form-gap"><label>Variable<select aria-label="Variable NASA" value={layer} onChange={e=>onLayer(e.target.value as NasaLayer|'')}>
      <option value="">Sin superposición</option>{Object.entries(nasaLayers).map(([id,entry])=><option key={id} value={id}>{entry.name}</option>)}</select></label>
      {selected&&selected.time!=='static'&&<label>{layer==='ndvi'?'Mes de observación':'Fecha de observación'}<input type={layer==='ndvi'?'month':'date'} value={layer==='ndvi'?date.slice(0,7):date}
        onChange={e=>{if(e.target.value)onDate(layer==='ndvi'?e.target.value+'-01':e.target.value);}}/></label>}</div>
    {selected&&selected.time!=='static'&&<div className="button-row"><button type="button" className="button secondary small" onClick={()=>shiftDate(-1)}>← {selected.time==='month'?'Mes':'Día'} anterior</button>
      <button type="button" className="button secondary small" onClick={()=>shiftDate(1)}>{selected.time==='month'?'Mes':'Día'} siguiente →</button></div>}
    {selected&&<p className="muted">{selected.detail} Capa visual de contexto. Requiere internet y puede tener píxeles o fechas sin cobertura. <a href={`${root}/legends/${selected.legend}_H.svg`} target="_blank" rel="noreferrer">Ver escala de colores</a></p>}
    {error&&<p className="notice" role="status">La capa no respondió para toda esta vista o fecha. Prueba otra fecha.</p>}
  </details>;

  function shiftDate(direction:number){
    const current=new Date(date+'T12:00:00Z');
    if(selected?.time==='month')current.setUTCMonth(current.getUTCMonth()+direction);
    else current.setUTCDate(current.getUTCDate()+direction);
    onDate(current.toISOString().slice(0,10));
  }
}
