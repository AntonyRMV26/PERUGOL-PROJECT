from dataclasses import dataclass
from .servicios import Bloque, minutos


@dataclass
class Columna:
    titulo: str
    bloques: list
    url: str = ""


def filas_agenda(columnas):
    limites = sorted({h for c in columnas for b in c.bloques for h in (b.inicio, b.fin)})
    if not limites:
        return []
    indices = {hora: i for i, hora in enumerate(limites)}
    por_columna = []
    for columna in columnas:
        bloques = columna.bloques or [Bloque(limites[0], limites[-1], "cerrado")]
        if bloques[0].inicio > limites[0]:
            bloques = [Bloque(limites[0], bloques[0].inicio, "cerrado"), *bloques]
        if bloques[-1].fin < limites[-1]:
            bloques = [*bloques, Bloque(bloques[-1].fin, limites[-1], "cerrado")]
        por_columna.append({bloque.inicio: bloque for bloque in bloques})

    filas = []
    for inicio, fin in zip(limites, limites[1:]):
        celdas = []
        for columna, bloques in zip(columnas, por_columna):
            if inicio in bloques:
                bloque = bloques[inicio]
                celdas.append({
                    "columna": columna, "bloque": bloque,
                    "filas": indices[bloque.fin] - indices[inicio],
                })
        filas.append({"inicio": inicio, "fin": fin, "celdas": celdas})
    return filas


def duracion_disponible(bloques):
    return sum(minutos(b.fin) - minutos(b.inicio) for b in bloques if b.estado == "libre")
