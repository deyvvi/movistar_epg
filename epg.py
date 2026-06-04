import json
import os
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from xml.dom import minidom

JSON_PATH = "channels_PE.json"
OUTPUT_XML = "PE.xml"

AHORA = int(time.time())
UN_DIA_SEGUNDOS = 86400
CANTIDAD_DIAS = 5
TAMANIO_LOTE = 25

def cargar_pids(ruta_json):
    if not os.path.exists(ruta_json):
        return []
    try:
        with open(ruta_json, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        return [canal['pid'] for canal in datos.get('userChannels', []) if 'pid' in canal]
    except Exception:
        return []

def dividir_en_lotes(lista, n):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]

def formatear_fecha_xmltv(timestamp):
    try:
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime('%Y%m%d%H%M%S +0000')
    except Exception:
        return ""

def consultar_api(pids_lote, inicio_ts, fin_ts):
    base_url = "https://contentapi-pe.cdn.telefonica.com/28/default/es-PE/schedules"
    params = {
        "ca_deviceTypes": "null|401",
        "ca_channelmaps": "142|null",
        "fields": "Pid,Title,Description,ChannelName,ChannelNumber,CallLetter,Start,End,EpgNetworkDvr,LiveChannelPid,LiveProgramPid,EpgSerieId,SeriesPid,SeriesId,SeasonPid,SeasonNumber,images.videoFrame,images.banner,LiveToVod,AgeRatingPid,forbiddenTechnology,IsSoDisabled",
        "includeRelations": "Genre",
        "orderBy": "START_TIME:a",
        "filteravailability": "false",
        "includeAttributes": "ca_cpvrDisable,ca_descriptors,ca_blackout_target,ca_blackout_areas",
        "starttime": inicio_ts,
        "endtime": fin_ts,
        "livechannelpids": ",".join(pids_lote),
        "offset": 0,
        "limit": 1000
    }
    url_con_parametros = f"{base_url}?{urllib.parse.urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url_con_parametros, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
    except Exception:
        pass
    return None

def generar_xmltv():
    pids = cargar_pids(JSON_PATH)
    if not pids:
        return
    
    root = ET.Element("tv", {
        "generator-info-name": "Generador-EPG-Python",
        "generator-info-url": "http://localhost"
    })
    
    canales_agregados = set()
    programas_agregados = set()
    lotes = list(dividir_en_lotes(pids, TAMANIO_LOTE))
    
    total_pasos = len(lotes) * CANTIDAD_DIAS
    paso_actual = 0
    
    for lote in lotes:
        for dia_idx in range(CANTIDAD_DIAS):
            inicio_consulta = AHORA + (dia_idx * UN_DIA_SEGUNDOS)
            fin_consulta = inicio_consulta + UN_DIA_SEGUNDOS
            
            datos_api = consultar_api(lote, inicio_consulta, fin_consulta)
            if datos_api and "Content" in datos_api:
                contenidos = datos_api["Content"]
                for item in contenidos:
                    channel_id = item.get("LiveChannelPid")
                    program_pid = item.get("Pid")
                    
                    if not channel_id or not program_pid:
                        continue
                    
                    if program_pid in programas_agregados:
                        continue
                    
                    if channel_id not in canales_agregados:
                        channel_elem = ET.SubElement(root, "channel", id=channel_id)
                        display_name = item.get("ChannelName") or item.get("CallLetter") or channel_id
                        name_elem = ET.SubElement(channel_elem, "display-name", lang="es")
                        name_elem.text = display_name
                        canales_agregados.add(channel_id)
                    
                    start_formatted = formatear_fecha_xmltv(item.get("Start"))
                    end_formatted = formatear_fecha_xmltv(item.get("End"))
                    if not start_formatted or not end_formatted:
                        continue
                        
                    prog_elem = ET.SubElement(root, "programme", {
                        "start": start_formatted,
                        "stop": end_formatted,
                        "channel": channel_id
                    })
                    
                    title_elem = ET.SubElement(prog_elem, "title", lang="es")
                    title_elem.text = item.get("Title") or "Sin título"
                    
                    desc_text = item.get("Description")
                    if desc_text:
                        desc_elem = ET.SubElement(prog_elem, "desc", lang="es")
                        desc_elem.text = desc_text
                    
                    images = item.get("Images", {})
                    video_frame = images.get("VideoFrame", [])
                    if video_frame and isinstance(video_frame, list):
                        img_url_original = video_frame[0].get("Url")
                        if img_url_original:
                            ET.SubElement(prog_elem, "icon", src=img_url_original)
                    
                    programas_agregados.add(program_pid)
            
            paso_actual += 1
            porcentaje = (paso_actual / total_pasos) * 100
            print(f"\rProgreso: {porcentaje:.1f}%", end="", flush=True)

    print()
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed_xml = minidom.parseString(xml_str)
    xml_bonito_bytes = parsed_xml.toprettyxml(indent="  ", encoding="utf-8")
    
    dir_output = os.path.dirname(OUTPUT_XML)
    if dir_output:
        os.makedirs(dir_output, exist_ok=True)
        
    with open(OUTPUT_XML, "wb") as f:
        f.write(xml_bonito_bytes)

if __name__ == "__main__":
    generar_xmltv()
