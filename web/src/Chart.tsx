import { useEffect, useRef, useState } from 'react';
import type { Result } from './types';

const months = 'Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic'.split(' ');

export function Plot({data, layout, label}:{data:object[]; layout:object; label:string}) {
  const root = useRef<HTMLDivElement>(null);
  const [failed,setFailed] = useState(false);
  useEffect(()=>{
    let active = true;
    let cleanup = ()=>{};
    const el = root.current!;
    setFailed(false);
    void import('plotly.js-basic-dist-min').then(async ({default:Plotly})=>{
      if (!active) return;
      await Plotly.react(el,data,{paper_bgcolor:'transparent',plot_bgcolor:'transparent',autosize:true,
        margin:{l:47,r:43,t:10,b:34},font:{family:'DM Sans Variable, sans-serif',color:'#527065',size:11},
        ...layout},{displayModeBar:false,responsive:true,displaylogo:false});
      if (!active) return;
      const watcher = new ResizeObserver(()=>Plotly.Plots.resize(el));
      watcher.observe(el);
      cleanup=()=>{watcher.disconnect();Plotly.purge(el);};
    }).catch(()=>{if(active)setFailed(true);});
    return ()=>{active=false;cleanup();};
  },[data,layout]);
  return <><div className="plot" ref={root} role="img" aria-label={label}/>{failed&&<p className="notice">El gráfico no se pudo cargar. Consulta los valores en la tabla.</p>}</>;
}

export function ClimateChart({monthly}:{monthly:Result['monthly']}) {
  return <Plot label="Lluvia acumulada mensual y temperatura media mensual"
    data={[
      {type:'bar',x:months,y:monthly.map(m=>m.rain),name:'Lluvia',marker:{color:'#c6dfa9'},hovertemplate:'%{x} · %{y:.1f} mm<extra></extra>'},
      {type:'scatter',mode:'lines+markers',x:months,y:monthly.map(m=>m.temp),yaxis:'y2',name:'Temperatura',line:{color:'#246750',width:3,shape:'spline'},marker:{size:5},hovertemplate:'%{x} · %{y:.1f} °C<extra></extra>'}
    ]} layout={{showlegend:false,bargap:.4,xaxis:{fixedrange:true},yaxis:{rangemode:'tozero',fixedrange:true,gridcolor:'#eef2eb',ticksuffix:' mm'},
      yaxis2:{overlaying:'y',side:'right',fixedrange:true,showgrid:false,ticksuffix:' °C'}}}/>;
}
