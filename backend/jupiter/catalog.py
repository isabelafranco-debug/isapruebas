"""Regional representation and agronomic scope kept alongside model parameters."""
from .model import CROPS, FAO

REGIONAL_SOURCE = "https://ice.santacruz.gob.bo/uploads/SANTA_CRUZ_ESTADISTICO_2024_a8a96110b3.pdf"
PERIOD = "2022–2023 (preliminar), ICE 2024, p. 47, fuente INE"
PRODUCTION_KT = {"soy":3542,"sorghum":881,"maize":743,"wheat":198,"sunflower":180,
                 "cassava":116,"bean":95,"potato":73,"sugarcane":9757,"rice":516,"mandarin":121}
CONTEXT = {
    "sugarcane":dict(name="Caña de azúcar",family="Poaceae",
                    note="Cultivo plurianual con socas. Requiere plan de renovación y balance de varios cortes."),
    "rice":dict(name="Arroz con cáscara",family="Poaceae",
                note="Confirma secano o riego. El arroz inundado requiere balance de lámina y percolación específico."),
    "mandarin":dict(name="Mandarina",family="Rutaceae",
                    note="Huerto perenne. Requiere manejo por edad, portainjerto y cobertura entre hileras."),
}
NOTES = {
    "cassava":"Parámetros FAO de primer año, ciclo de 210 días. Confirma cosecha y cultivar de ciclo corto.",
    "potato":"Revisa aptitud térmica y altitud con un agrónomo de los valles cruceños.",
    "tomato":"Confirma tutorado, riego, sanidad y canal de venta para horticultura.",
    "cotton":"Valida cultivar, cosecha especializada y disponibilidad de desmote.",
    "cover":"Cobertura de mucuna orientativa. Planifica terminación y manejo del rastrojo.",
    "cowpea":"Leguminosa de grano o cobertura. Confirma uso, inoculación y mercado.",
}


def catalog():
    return [dict(code=code,name=crop["name"],family=crop["family"],
                 months=crop.get("window",[]),simulated=code in CROPS,
                 production_kt=PRODUCTION_KT.get(code),production_period=PERIOD,
                 production_source=REGIONAL_SOURCE,parameter_source=FAO,
                 note=crop.get("note") or NOTES.get(code,"Confirma cultivar, ventana local y destino de la cosecha."))
            for code,crop in {**CROPS,**CONTEXT}.items()]
